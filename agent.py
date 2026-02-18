import asyncio
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, room_io, JobProcess, WorkerOptions
from livekit.plugins import (
    noise_cancellation,
    google,
    silero,
)
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email

load_dotenv()

# --- OPTIMIZATION: PREWARM THE VAD ---
# This loads the AI model into memory once when the script starts,
# instead of loading it every time a new person joins.
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.8,
            ),
            tools=[get_weather, search_web, send_email],
        )

async def entrypoint(ctx: agents.JobContext):
    # Retrieve the already-loaded VAD from memory
    vad = ctx.proc.userdata["vad"]

    session = AgentSession(
        vad=vad,
        preemptive_generation=True,
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )

    # Parallelize the connection and the first reply
    await ctx.connect()
    
    # Reduced sleep: 0.5s is usually enough once VAD is pre-loaded
    await asyncio.sleep(0.5)

    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    while ctx.room.connection_state == "connected":
        await asyncio.sleep(1)

if __name__ == "__main__":
    # Updated to include prewarm_fnc
    agents.cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm 
    ))
