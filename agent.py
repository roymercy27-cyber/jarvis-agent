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
import os
import json
import logging

load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        DIRECT_ACTION_INSTRUCTION = f"""
        {AGENT_INSTRUCTION}
        # DIRECT ACTION PROTOCOL
        1. When asked for info, CALL THE TOOL IMMEDIATELY.
        2. No "Let me check" chatter. Just give the answer.
        3. Speak like a classy butler.
        """
        super().__init__(
            instructions=DIRECT_ACTION_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(voice="Charon", temperature=0.7),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # Connect to room first to avoid "worker timeout"
    await ctx.connect()
    
    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # Load Memories
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = json.dumps(results) if results else ''
    if results:
        initial_ctx.add_message(
            role="assistant",
            content=f"User: {user_name}. Memories: {memory_str}. Use tools immediately."
        )

    # SAFETY FIX: MCP Server Integration
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    agent = Assistant(chat_ctx=initial_ctx) # Default agent

    if mcp_url:
        try:
            mcp_server = MCPServerSse(
                params={"url": mcp_url},
                cache_tools_list=True,
                name="SSE MCP Server"
            )
            # Try to integrate MCP tools
            agent = await MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant, 
                agent_kwargs={"chat_ctx": initial_ctx},
                mcp_servers=[mcp_server]
            )
            logging.info("MCP Tools integrated successfully.")
        except Exception as e:
            logging.error(f"MCP failed, starting with local tools only: {e}")

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Initial greeting
    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nBriefly greet Ivan and give him time/weather immediately.",
    )

    async def shutdown_hook():
        # Shutdown logic simplified for safety
        logging.info("Shutting down...")

    ctx.add_shutdown_callback(shutdown_hook)

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
