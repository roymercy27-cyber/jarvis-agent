import asyncio
from dotenv import load_dotenv
from livekit import agents
# Notice: No more '.pipeline' import. We use the core classes.
from livekit.agents import JobContext, JobProcess, AgentSession, Agent, RoomInputOptions
from livekit.plugins import google, silero, noise_cancellation
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

def prewarm(proc: JobProcess):
    # This prepares the 'ears' of the agent
    silero.VAD.load()

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"--- Jarvis Online: {ctx.room.name} ---")

    # 1. Define the Agent (Brain + Tools)
    jarvis_logic = Agent(
        instructions=AGENT_INSTRUCTION,
        tools=[get_weather, search_web, send_email, get_time]
    )

    # 2. Setup the Session (Voice + Ears)
    # We use Google's Realtime model directly here
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

    # 3. Join the room and start the greeting
    await session.start(room=ctx.room, agent=jarvis_logic)
    
    # Forced greeting: This ensures he speaks the moment you connect
    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Session ended: {e}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
