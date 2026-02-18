import asyncio
import os
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, room_io, JobContext, JobProcess
from livekit.plugins.noise_cancellation import BVC
from livekit.plugins.google import beta
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

# MODEL FIX: This is the most stable name for the Live/Realtime API currently
SELECTED_MODEL = "gemini-2.0-flash-live-preview-04-09" 

def prewarm(proc: JobProcess):
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load()

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=beta.realtime.RealtimeModel(
                model=SELECTED_MODEL, 
                voice="Charon",
                temperature=0.6,
            ),
            tools=[get_weather, search_web, send_email, get_time],
        )

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"--- Protocol Initiated: {ctx.room.name} ---")
    
    from livekit.plugins import silero
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    session = AgentSession(
        llm=beta.realtime.RealtimeModel(
            model=SELECTED_MODEL,
            voice="Charon",
            modalities=["audio"]
        ),
        vad=vad,
        preemptive_generation=True
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(noise_cancellation=BVC())
        )
    )

    # Handshake delay for mobile/Railway connectivity
    await asyncio.sleep(2) 

    # FIXED: Replaced the 'is_running' attribute error with a standard say()
    # If the session fails, the try/except will catch it without crashing the whole process
    try:
        await session.say(SESSION_INSTRUCTION, allow_interruptions=True)
    except Exception as e:
        print(f"Greeting failed: {e}")

    while ctx.room.connection_state == "connected":
        await asyncio.sleep(1)

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
