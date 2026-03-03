import asyncio
import os
import json
import logging
from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from livekit.plugins.turn_detector.multilingual import MultilingualModel # NEW: Better Turn Detection
from prompts import AGENT_INSTRUCTION 
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        # HUMAN-LIKE UPGRADE: Tone instructions for "The Real Jarvis"
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "PERSONALITY OVERRIDE: You are JARVIS. Your tone is calm, sophisticated, and British. "
            "Speak with clinical confidence. Avoid robotic list-making. Use smooth transitions like "
            "'Right away, Ivan' or 'I've looked into that for you.' "
            "NEVER stop mid-sentence. If you are performing a task, acknowledge it first."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.55, # Increased slightly for more natural variation
                # tool_choice="auto" is implied
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord, run_python_script],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. SESSION CONFIG (Fixing Cut-offs) ---
    session = AgentSession(
        stt=google.STT(), # Ensure high-quality transcription
        llm=google.beta.realtime.RealtimeModel(),
        tts=google.TTS(),
        # Use MultilingualModel to prevent "Mhmm" from cutting Jarvis off
        turn_detection=MultilingualModel(), 
    )

    # --- 2. MCP & N8N GMAIL FIX ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    try:
        if mcp_url:
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="Jarvis-Mail-Link")
            # Increased timeout and strict tool integration
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, 
                    agent_kwargs={"chat_ctx": ChatContext()}, 
                    mcp_servers=[mcp_server]
                ), timeout=25.0 
            )
        else:
            agent = Assistant()
    except Exception as e:
        logging.error(f"Handshake failed: {e}")
        agent = Assistant()

    # --- 3. SESSION START & CONTINUITY ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(video_enabled=True),
    )

    # Force Jarvis to finish speaking even if the user makes noise
    # This prevents the "random stop" issue.
    @session.on("agent_started_speaking")
    def _lock_speech():
        logging.info("Jarvis is holding the floor.")

    logging.info("Jarvis is online and stabilized.")
    await session.generate_reply() 

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
