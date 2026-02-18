import asyncio
import os
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, room_io
from livekit.plugins import noise_cancellation, google, silero
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

# We use the most stable Gemini 2.0 Live model name
SELECTED_MODEL = "gemini-2.0-flash-exp" 

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                model=SELECTED_MODEL,
                voice="Aoede", # YouTuber's preferred voice
                temperature=0.8,
            ),
            tools=[
                get_weather,
                search_web,
                send_email,
                get_time
            ],
        )

async def entrypoint(ctx: agents.JobContext):
    # 1. Initialize the session with VAD (Voice Activity Detection)
    # This matches the YouTuber's clean structure
    session = AgentSession(
        vad=silero.VAD.load(),
    )

    # 2. Start the session BEFORE connecting to the room
    # This ensures the agent is ready the moment the user joins
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )

    # 3. Connect to the room
    await ctx.connect()
    print(f"--- Protocol Initiated: {ctx.room.name} ---")

    # 4. Use generate_reply for the initial greeting
    # This is much more stable than session.say()
    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

    # Keep the process alive
    while ctx.room.connection_state == "connected":
        await asyncio.sleep(1)

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
