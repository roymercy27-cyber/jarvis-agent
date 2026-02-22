import asyncio 
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import (
    AgentSession, 
    Agent, 
    RoomInputOptions, 
    ChatContext, 
    llm, 
    WorkerOptions, # Added for faster startup
    JobProcess      # Added for prewarming
)
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

# Prewarm function: Runs when the worker starts, NOT when a user joins.
# Use this to load heavy plugins or models before the call starts.
def prewarm(proc: JobProcess):
    logging.info("Prewarming worker: Loading heavy assets...")
    # If you had heavy local models (like Silero VAD), you'd load them here.

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        DIRECT_ACTION_INSTRUCTION = f"""
        {AGENT_INSTRUCTION}
        # DIRECT ACTION PROTOCOL
        1. CALL TOOLS IMMEDIATELY. No "One moment" chatter.
        2. Speak like a classy butler.
        """
        
        super().__init__(
            instructions=DIRECT_ACTION_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.7,
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # FAST JOIN: Connect to the room immediately upon job assignment
    logging.info(f"Agent starting for room: {ctx.room.name}")
    await ctx.connect()

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        # ... (keep your existing shutdown logic here)
        pass

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    
    # Load memories
    results = await mem0.get_all(user_id='Ivan')
    initial_ctx = ChatContext()
    memory_str = json.dumps(results) if results else ''
    
    if results:
        initial_ctx.add_message(
            role="assistant",
            content=f"User: Ivan. Memories: {memory_str}. Use tools immediately."
        )

    # Initialize MCP and Agent
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

    # Start the voice session
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
        instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan and provide time/weather updates immediately.",
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    # OPTIMIZED CLI: Added prewarm and idle processes for instant Sandbox joining
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            num_idle_processes=3  # Keeps 3 agents "hot" and ready to join instantly
        )
    )
