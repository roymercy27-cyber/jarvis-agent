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

# MODEL FIX: 'gemini-2.0-flash-exp' is deprecated for the Live API.
# Use 'gemini-2.0-flash' or 'gemini-2.0-flash-live' depending on your region.
SELECTED_MODEL = "gemini-2.0-flash" 

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

    # Added stabilization delay for Railway connectivity
    await asyncio.sleep(2) 

    # SAFETY CHECK: Only try to speak if the session actually connected
    if session.is_running:
        await session.say(SESSION_INSTRUCTION, allow_interruptions=True)
    else:
        print("ERROR: Session failed to start. Check API Key permissions.")

    while ctx.room.connection_state == "connected":
        await asyncio.sleep(1)

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
