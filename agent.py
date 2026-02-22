import asyncio
import os
import json
import logging
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
        # Tightened protocol for Jarvis personality
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.6, # Lower for better tool precision
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # CRITICAL: Connect first to satisfy Railway/Sandbox health checks
    await ctx.connect()
    logging.info("Jarvis online and connected.")

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Archiving Ivan's session...")
        messages = []
        for item in chat_ctx.items:
            if not hasattr(item, 'content') or item.role not in ['user', 'assistant']:
                continue
            content = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if memory_str and memory_str in content: continue
            messages.append({"role": item.role, "content": content.strip()})
        
        if messages:
            try:
                await mem0.add(messages, user_id="Ivan")
            except Exception as e:
                logging.error(f"Mem0 Error: {e}")

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # Load Context
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    mem_data = json.dumps(results) if results else ""

    if results:
        initial_ctx.add_message(
            role="assistant", 
            content=f"Ivan's Profile: {mem_data}. Use tools immediately for data."
        )

    # Initialize MCP (Optional, with error handling)
    try:
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
    except Exception as e:
        logging.warning(f"MCP failed, falling back to local tools: {e}")
        agent = Assistant(chat_ctx=initial_ctx)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Trigger opening line
    await session.generate_reply(instructions=SESSION_INSTRUCTION)
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, mem_data))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        num_idle_processes=1 # Set to 1 for Railway memory safety
    ))
