import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, JobProcess
from livekit.plugins.noise_cancellation import BVC
from livekit.plugins.google import beta
from livekit.plugins import silero # Added for pre-warming
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

# This "prewarms" the VAD so it's ready the millisecond the app starts
def prewarm(proc: JobProcess):
    silero.VAD.load_model()

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.6,
            ),
            tools=[get_weather, search_web, send_email, get_time],
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    # preemptive_generation=True makes him start 'thinking' while you are still talking
    session = AgentSession(preemptive_generation=True)

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=BVC(),
            # JARVIS will wait only 0.4s of silence before replying
            min_endpointing_delay=0.4, 
        ),
    )

    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception:
        pass

if __name__ == "__main__":
    # Added the prewarm hook here
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm 
    ))
