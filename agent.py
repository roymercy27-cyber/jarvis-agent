import asyncio
import os
import json
import logging
import subprocess
from dotenv import load_dotenv

from livekit import agents
# REVERTED: Changed RoomOptions back to RoomInputOptions
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION 
import tools 
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

@agents.function_tool(description="Runs Python code to solve math, process data, or debug logic.")
def run_python_script(code: str):
    try:
        result = subprocess.run(['python3', '-c', code], capture_output=True, text=True, timeout=15)
        return f"Output: {result.stdout}\nErrors: {result.stderr}"
    except Exception as e:
        return f"Execution Failed: {str(e)}"

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.4,
                # Keeps the interruption protection
                turn_detection=google.beta.realtime.VADOptions(
                    threshold=0.8, 
                    prefix_padding_ms=300,
                    silence_duration_ms=600
                )
            ),
            tools=[tools.get_weather, tools.search_web, tools.send_email, 
                   tools.mobile_whatsapp, tools.mobile_discord, run_python_script],
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
    if results:
        memories = [{"memory": r["memory"]} for r in results]
        initial_ctx.add_message(role="assistant", content=f"User Context: {json.dumps(memories)}")

    # --- 2. RESILIENT MCP SETUP ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    agent = None
    if mcp_url:
        try:
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="SSE MCP Server")
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
                ), timeout=10
            )
        except Exception as e:
            logging.error(f"MCP failed: {e}")

    if not agent:
        agent = Assistant(chat_ctx=initial_ctx)

    session = AgentSession()

    # --- 3. REAL-TIME MEMORY LOGGING ---
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        logging.info(f"Saving User Memory: {msg.content}")
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    @session.on("agent_speech_committed")
    def on_agent_speech(msg: llm.ChatMessage):
        logging.info("Saving Agent response to Mem0")
        asyncio.create_task(mem0.add(f"Jarvis said: {msg.content}", user_id=user_name))

    # --- 4. START SESSION ---
    await session.start(
        room=ctx.room,
        agent=agent,
        # REVERTED: Using RoomInputOptions to match your library version
        room_input_options=RoomInputOptions(
            video_enabled=True,
        )
    )

    logging.info("Jarvis Active.")
    await session.generate_reply() 

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
