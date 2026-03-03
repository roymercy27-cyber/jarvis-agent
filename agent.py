import asyncio 
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION
# Note: SESSION_INSTRUCTION is removed from imports to prevent Railway crash
from tools import get_weather, search_web, send_email, get_system_report, calculate_math
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.4, 
            ),
            tools=[
                get_weather,
                search_web,
                send_email,
                get_system_report,
                calculate_math
            ],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # CRITICAL: Connect to the room first
    await ctx.connect()
    logging.info(f"Connected to room: {ctx.room.name}")

    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. MEMORY LOADING ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ''

    if results:
        memories = [
            {"memory": result["memory"], "updated_at": result["updated_at"]}
            for result in results
        ]
        memory_str = json.dumps(memories)
        initial_ctx.add_message(
            role="assistant",
            content=f"System Context: User is {user_name}. Past facts: {memory_str}"
        )

    # --- 2. MCP / n8n SETUP ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    mcp_server = MCPServerSse(
        params={"url": mcp_url},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    # Create agent with MCP integration
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, 
        agent_kwargs={"chat_ctx": initial_ctx},
        mcp_servers=[mcp_server]
    )

    session = AgentSession()

    # --- 3. SHUTDOWN LOGIC ---
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context...")
        messages_formatted = []
        for item in chat_ctx.items:
            if not isinstance(item, llm.ChatMessage) or item.role not in ['user', 'assistant']:
                continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if memory_str and memory_str in content_str:
                continue
            messages_formatted.append({"role": item.role, "content": content_str.strip()})
        
        if messages_formatted:
            try:
                await asyncio.shield(mem0.add(messages_formatted, user_id=user_name))
            except Exception as e:
                logging.error(f"Mem0 save failed: {e}")
        await asyncio.sleep(1)

    # --- 4. START SESSION ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Initial Greeting Logic (No external variable needed)
    await session.generate_reply(
        instructions="Briefly greet Ivan as his classy butler. Provide a quick update on the current time and weather immediately."
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
