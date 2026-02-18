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
from tools import get_weather, search_web, send_email

load_dotenv()

# We load the VAD once at the module level for stability in containers
# If Railway still crashes, remove the prewarm logic entirely and load inside entrypoint
def prewarm(proc: JobProcess):
    try:
        proc.userdata["vad"] = silero.VAD.load()
    except Exception as e:
        print(f"Prewarm failed: {e}")

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
            ],
        )

async def entrypoint(ctx: agents.JobContext):
    # Retrieve prewarmed VAD or fallback to a fresh load to prevent crashes
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    session = AgentSession(
        preemptive_generation=True,
        min_endpointing_delay=0.1, # Set to 0.1s for stability; 0.05 can be too aggressive for cloud
        vad=vad
    )

    # Connect to the room first
    await ctx.connect()

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Initial greeting to avoid "nudging"
    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

if __name__ == "__main__":
    agents.cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm 
    ))


