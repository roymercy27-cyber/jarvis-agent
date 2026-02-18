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

# Prewarm keeps the VAD model in RAM so it doesn't have to load from disk later
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
    vad = ctx.proc.userdata["vad"]

    session = AgentSession(
        vad=vad,
        preemptive_generation=True, # Starts thinking before you finish speaking
    )

    # Optimization: Start the session logic BEFORE the room connection is fully established
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )

    # SPEED TRICK: Run connection and the first reply greeting in PARALLEL
    # This removes the "wait for connect" -> "wait for sleep" -> "talk" sequence.
    await asyncio.gather(
        ctx.connect(),
        session.generate_reply(instructions=SESSION_INSTRUCTION)
    )

    while ctx.room.connection_state == "connected":
        await asyncio.sleep(1)

if __name__ == "__main__":
    agents.cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm 
    ))
