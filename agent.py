import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, JobContext, JobProcess
from livekit.plugins.noise_cancellation import BVC
from livekit.plugins.google import beta
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

# We pre-load the VAD to save 200-500ms on the first turn
def prewarm(proc: JobProcess):
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load()

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

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"--- Protocol Initiated: {ctx.room.name} ---")
    
    # Preemptive generation makes tool calls and responses feel instant
    session = AgentSession(preemptive_generation=True)

    # We use the prewarmed VAD for faster voice detection
    from livekit.plugins import silero
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=BVC(),
        ),
    )

    # FIX FOR SILENCE: Instead of generate_reply, use session.say for the initial greeting.
    # On mobile, generate_reply can occasionally time out before the audio buffer fills.
    # session.say() forces the audio stream to open immediately.
    await session.say(SESSION_INSTRUCTION, allow_interruptions=True)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception:
        pass

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
