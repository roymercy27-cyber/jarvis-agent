import asyncio
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION 
# KEEP THIS IMPORT STYLE - It is why the first code works
from tools import get_weather, search_web, send_email, mobile_whatsapp, mobile_discord, get_system_report, calculate_math
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
            # Functions listed directly (no tools. prefix)
            tools=[get_weather, search_web, send_email, mobile_whatsapp, mobile_discord, get_system_report, calculate_math],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # 1. MEMORY LOADING
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        memories = [{"memory": r["memory"]} for r in results]
        initial_ctx.add_message(role="assistant", content=f"User facts: {json.dumps(memories)}")

    # 2. RESILIENT MCP (n8n)
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    agent = None
    if mcp_url:
        try:
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="SSE MCP Server")
            # This timeout is good - keep it!
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
                ), timeout=10
            )
        except Exception as e:
            logging.error(f"MCP Fallback: {e}")

    if not agent:
        agent = Assistant(chat_ctx=initial_ctx)

    session = AgentSession()

    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    # 3. START
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply() 

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
