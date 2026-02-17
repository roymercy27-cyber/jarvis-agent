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
    
    # Define JARVIS as a standard Agent
    # This automatically handles the voice, tools, and instructions
    jarvis_agent = Agent(
        instructions=AGENT_INSTRUCTION,
        tools=[get_weather, search_web, send_email, get_time]
    )

    # Use AgentSession - this is the most stable way to run the agent
    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            voice="Charon",
            temperature=0.7,
        ),
        vad=silero.VAD.load(),
        # Add background noise cancellation for a cleaner experience
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        )
    )

    # Start the session with your agent
    await session.start(room=ctx.room, agent=jarvis_agent)

    # Make JARVIS say his greeting
    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Connection lost: {e}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
