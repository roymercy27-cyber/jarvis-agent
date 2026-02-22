import os
import json
import logging
import asyncio
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email
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
                temperature=0.7,
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # --- SPEED FIX: CONNECT FIRST ---
    # This ensures you join the Sandbox instantly.
    await ctx.connect()
    logging.info("Jarvis joined the room.")

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Saving Ivan's context...")
        messages_formatted = []
        for item in chat_ctx.items:
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if memory_str and memory_str in content_str:
                continue
            if item.role in ['user', 'assistant']:
                messages_formatted.append({"role": item.role, "content": content_str.strip()})
        
        await mem0.add(messages_formatted, user_id="Ivan")

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # Load data in background
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = json.dumps(results) if results else ""

    if results:
        initial_ctx.add_message(
            role="assistant",
            content=f"User: {user_name}. Relevant context: {memory_str}."
        )

    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, 
        agent_kwargs={"chat_ctx": initial_ctx},
        mcp_servers=[mcp_server]
    )

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(instructions=SESSION_INSTRUCTION)
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        num_idle_processes=1  # Fixed to 1 to prevent Code -9 OOM error
    ))
