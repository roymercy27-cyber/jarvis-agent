import asyncio
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, room_io
from livekit.plugins import (
    noise_cancellation,
    google,
    silero,  # <--- Required for Jarvis to "hear" you
)
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email

load_dotenv()

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Aoede",
                temperature=0.8,
            ),
            tools=[get_weather, search_web, send_email],
        )

async def entrypoint(ctx: agents.JobContext):
    # 1. Load the "Ears" (VAD) so Jarvis knows when you're speaking
    vad = silero.VAD.load()

    # 2. Setup the session with Preemptive Generation for instant replies
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

    # 3. Connect to the room first
    await ctx.connect()
    
    # 4. Give the connection 1 second to breathe so the first reply doesn't fail
    await asyncio.sleep(1)

    # 5. Jarvis introduces himself
    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    # Keep the process alive
    while ctx.room.connection_state == "connected":
        await asyncio.sleep(1)

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
