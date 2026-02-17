import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import JobContext, JobProcess, AgentSession, Agent, RoomInputOptions
from livekit.plugins import google, silero, noise_cancellation
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

def prewarm(proc: JobProcess):
    silero.VAD.load()

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"--- Jarvis Joined Room: {ctx.room.name} ---")

    # 1. Create the Agent Logic
    jarvis_logic = Agent(
        instructions=AGENT_INSTRUCTION,
        tools=[get_weather, search_web, send_email, get_time]
    )

    # 2. Create the Session
    # Using 'preemptive_generation=False' for the initial greeting to prevent race conditions
    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            voice="Charon",
            temperature=0.7,
        ),
        vad=silero.VAD.load(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        )
    )

    # 3. Start the session
    await session.start(room=ctx.room, agent=jarvis_logic)

    # 4. THE FIX: Force immediate speech.
    # 'generate_reply' waits for the LLM to process. 
    # 'say' sends the text to TTS immediately, which wakes up the mobile audio track.
    await session.say(SESSION_INSTRUCTION, allow_interruptions=True)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Session error: {e}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
