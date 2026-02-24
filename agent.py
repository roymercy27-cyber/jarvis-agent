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
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.4, # Balanced for personality and accuracy
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. ROBUST MEMORY LOADING ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        # Extract the actual memory strings from Mem0 results
        memories = [r['memory'] for r in results]
        memory_str = "\n".join(memories)
        logging.info(f"Loaded memories for {user_name}")
        # We add this as a system-level context so Friday knows who you are
        initial_ctx.add_message(
            role="assistant", 
            content=f"System Context: User is {user_name}. Past facts: {memory_str}"
        )

    mcp_server = MCPServerSse(params={"url": os.environ.get("N8N_MCP_SERVER_URL")}, name="SSE MCP Server")
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
    )

    session = AgentSession()

    # --- 2. THE FIX: REAL-TIME AUTO-SAVE ---
    # This event triggers every time you finish speaking. 
    # It ensures the memory is saved even if the app crashes.
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        logging.info(f"Friday is committing to memory: {msg.content}")
        # Run the save in the background so it doesn't lag the voice
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(instructions=SESSION_INSTRUCTION)

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
