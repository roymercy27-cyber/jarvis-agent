import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins.noise_cancellation import BVC
from livekit.plugins.google import beta
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.6,
            ),
            tools=[
                get_weather,
                search_web,
                send_email,
                get_time
            ],
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    # FIX: preemptive_generation=True significantly reduces tool-call latency
    session = AgentSession(preemptive_generation=True)

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=BVC(),
        ),
    )

    # Initial greeting
    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception:
        pass

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
