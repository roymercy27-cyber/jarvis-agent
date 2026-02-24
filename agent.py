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

# Updated identity to force tool usage
STRICT_INSTRUCTION = AGENT_INSTRUCTION + "\n\nCRITICAL: Always use the 'search_web' tool for any real-time data, stock prices, or news. Never guess. If you need a tool, call it immediately without asking for permission first."

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        super().__init__(
            instructions=STRICT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.4 # Lower temperature = higher accuracy & better tool calls
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # Load past context
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        mem_str = " ".join([r['memory'] for r in results])
        initial_ctx.add_message(role="assistant", content=f"System: User is {user_name}. Relevant past info: {mem_str}")

    mcp_server = MCPServerSse(params={"url": os.environ.get("N8N_MCP_SERVER_URL")}, name="SSE MCP Server")
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
    )

    session = AgentSession()

    # --- MOBILE FIX 1: REAL-TIME SAVING ---
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        # We don't wait for the call to end. We save as we go.
        logging.info(f"Auto-saving sentence for {user_name}...")
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

