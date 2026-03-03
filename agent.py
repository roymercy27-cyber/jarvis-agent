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
                # Added VAD protection to ensure he finishes sending emails
                turn_detection=google.beta.realtime.VADOptions(
                    threshold=0.8,
                    prefix_padding_ms=300,
                    silence_duration_ms=600
                )
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

    # --- 2. RESILIENT MCP (n8n) INTEGRATION ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    agent = None
    
    if mcp_url:
        try:
            logging.info(f"Connecting to MCP at {mcp_url}...")
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="SSE MCP Server")
            # Added a 15-second timeout so Jarvis joins even if n8n is slow
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, 
                    agent_kwargs={"chat_ctx": initial_ctx}, 
                    mcp_servers=[mcp_server]
                ), timeout=15
            )
        except Exception as e:
            logging.error(f"n8n/MCP Connection failed: {e}. Falling back to local tools.")
    
    # Fallback to standard agent if n8n fails
    if not agent:
        agent = Assistant(chat_ctx=initial_ctx)

    session = AgentSession()

    # --- 3. REAL-TIME MEMORY LOGGING ---
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        logging.info(f"Jarvis logging user memory: {msg.content}")
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    @session.on("agent_speech_committed")
    def on_agent_speech(msg: llm.ChatMessage):
        logging.info("Jarvis logging own response to memory.")
        asyncio.create_task(mem0.add(f"Jarvis said: {msg.content}", user_id=user_name))

    # --- 4. SESSION START ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            # noise_cancellation=noise_cancellation.BVC(), # Keep disabled if cloud crashes persist
        ),
    )

    logging.info("Jarvis joined. Generating greeting...")
    await session.generate_reply() 

    # --- 5. SHUTDOWN LOGGING (REDUNDANCY) ---
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient):
        logging.info("Shutting down, ensuring final memories are saved...")
        await asyncio.sleep(1)

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
