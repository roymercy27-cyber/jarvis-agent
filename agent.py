from dotenv import load_dotenv
import asyncio

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, WorkerOptions, JobProcess
from livekit.plugins import (
    noise_cancellation,
    silero,  # Added for prewarming VAD
)
from livekit.plugins import google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_current_time

load_dotenv()

# PREWARM: This loads models into RAM before the job starts for "Instant Join"
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
            tools=[
                get_weather,
                search_web,
                send_email,
                get_current_time
            ],
        )

async def entrypoint(ctx: agents.JobContext):
    # USE PREWARMED VAD: Avoids loading delay during connection
    vad = ctx.proc.userdata["vad"]

    session = AgentSession(
        preemptive_generation=True, # Start thinking while user is talking
        min_endpointing_delay=0.05, # Respond in < 100ms after user stops
        vad=vad
    )

    # CONNECT IMMEDIATELY: Connect to room before starting heavy session logic
    await ctx.connect()

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # PROACTIVE GREETING: Jarvis speaks first so you don't have to nudge
    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

if __name__ == "__main__":
    # WORKER OPTIONS: Configured for speed
    agents.cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm # Link the prewarm function here
    ))
