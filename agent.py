from dotenv import load_dotenv
import asyncio

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, WorkerOptions, JobProcess
from livekit.plugins import (
    noise_cancellation,
    silero,
)
from livekit.plugins import google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# Ensure get_current_time is imported from tools
from tools import get_weather, search_web, send_email, get_current_time

load_dotenv()

def prewarm(proc: JobProcess):
    """Prewarm VAD to reduce initial connection latency."""
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
                get_current_time # Registering the time tool here
            ],
        )

async def entrypoint(ctx: agents.JobContext):
    # Retrieve prewarmed VAD or fallback
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    session = AgentSession(
        preemptive_generation=True,
        min_endpointing_delay=0.1,
        vad=vad
    )

    # FIX: Connect to the room FIRST so Jarvis is present before speaking
    await ctx.connect()

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # FIX: Immediate greeting avoids the need for a 'nudge'
    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

if __name__ == "__main__":
    agents.cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
