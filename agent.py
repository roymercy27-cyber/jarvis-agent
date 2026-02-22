import asyncio 
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import (
    AgentSession, 
    Agent, 
    RoomInputOptions, 
    ChatContext, 
    llm, 
    WorkerOptions,
    JobProcess
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

# Prewarm helps the container stay "hot"
def prewarm(proc: JobProcess):
    logging.info("Prewarming: Worker is standing by...")

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        super().__init__(
            instructions=f"{AGENT_INSTRUCTION}\n# PROTOCOL: Call tools immediately. Speak like a classy butler.",
            llm=google.beta.realtime.RealtimeModel(voice="Charon", temperature=0.7),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # STEP 1: Connect to room immediately
    await ctx.connect()
    logging.info(f"Connected to room: {ctx.room.name}")

    # STEP 2: Wait for YOU to join (this makes the join feel instant once you're there)
    participant = await ctx.wait_for_participant()
    logging.info(f"Starting session for participant: {participant.identity}")

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    
    # Quick Memory Load
    results = await mem0.get_all(user_id='Ivan')
    initial_ctx = ChatContext()
    if results:
        initial_ctx.add_message(role="assistant", content=f"User: Ivan. Memories: {json.dumps(results)}")

    # Initialize MCP
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

    # STEP 3: Bind and Start
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )

    # Immediate Greet
    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan. Give him the time and weather now.",
    )

if __name__ == "__main__":
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            num_idle_processes=3 # CRITICAL: Keeps 3 agents "Warm" so they join in < 1 second.
        )
    )
