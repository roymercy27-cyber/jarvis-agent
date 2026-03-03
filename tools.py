import asyncio
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
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
    logging.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. MEMORY LOADING ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ""
    if results:
        memories = [{"memory": r["memory"], "updated_at": r["updated_at"]} for r in results]
        memory_str = json.dumps(memories)
        logging.info(f"Loaded memories for {user_name}")
        initial_ctx.add_message(
            role="assistant", 
            content=f"System Context: User is {user_name}. Past facts: {memory_str}"
        )

    # --- 2. RESILIENT MCP (n8n) SETUP ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    agent = None
    
    if mcp_url:
        try:
            logging.info(f"Connecting to MCP at {mcp_url}...")
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="SSE MCP Server")
            # CRITICAL FIX: Timeout prevents Jarvis from "blinking" forever if n8n is slow
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, 
                    agent_kwargs={"chat_ctx": initial_ctx}, 
                    mcp_servers=[mcp_server]
                ), timeout=10
            )
        except Exception as e:
            logging.error(f"MCP Connection failed or timed out: {e}. Joining room without n8n.")
    
    # Fallback to standard agent if n8n fails or times out
    if not agent:
        agent = Assistant(chat_ctx=initial_ctx)

    session = AgentSession()

    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        logging.info(f"Jarvis logging memory: {msg.content}")
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    # --- 3. SESSION START ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    logging.info("Jarvis joined. Generating greeting...")
    await session.generate_reply() 

    # --- 4. SHUTDOWN LOGGING ---
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving context...")
        # ... (rest of your existing shutdown logic)
        await asyncio.sleep(1)

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
