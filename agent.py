import asyncio
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import google # REMOVED noise_cancellation

from prompts import AGENT_INSTRUCTION 
from tools import get_weather, search_web, send_email, mobile_whatsapp, mobile_discord
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
            tools=[get_weather, search_web, send_email, mobile_whatsapp, mobile_discord],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ""
    if results:
        memories = [{"memory": r["memory"], "updated_at": r["updated_at"]} for r in results]
        memory_str = json.dumps(memories)
        initial_ctx.add_message(
            role="assistant", 
            content=f"System Context: User is {user_name}. Past facts: {memory_str}"
        )

    mcp_server = MCPServerSse(params={"url": os.environ.get("N8N_MCP_SERVER_URL")}, name="SSE MCP Server")
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
    )

    session = AgentSession()

    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(video_enabled=True), # REMOVED noise_cancellation.BVC()
    )

    await session.generate_reply() 

if __name__ == "__main__":
    # num_idle_processes=0 saves a huge amount of RAM on Render
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
