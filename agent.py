import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import JobContext, VoicePipelineAgent, JobProcess
from livekit.plugins import google, silero, noise_cancellation
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

# Pre-loading Silero so the "ears" are ready immediately
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"--- Connected to Room: {ctx.room.name} ---")

    # We define the agent as a Pipeline. This is much more stable for initial greetings.
    # We use Google's Realtime LLM as the "brain".
    initial_ctx = agents.llm.ChatContext().append(
        role="system",
        text=AGENT_INSTRUCTION,
    )

    jarvis = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=google.STT(),
        llm=google.beta.realtime.RealtimeModel(
            voice="Charon",
            temperature=0.7,
        ),
        tts=google.TTS(), # Fallback TTS ensures he always has a voice
        chat_ctx=initial_ctx,
        fnc_ctx=agents.llm.FunctionContext(), # This connects your tools
    )

    # Register your tools manually to the context
    jarvis.fnc_ctx.add_callable(get_weather)
    jarvis.fnc_ctx.add_callable(search_web)
    jarvis.fnc_ctx.add_callable(send_email)
    jarvis.fnc_ctx.add_callable(get_time)

    # Start the agent in the room
    jarvis.start(ctx.room)

    # MANDATORY: The Greeting. This is why he was silent.
    # We use 'say' because it bypasses the 'thinking' delay for the first message.
    await jarvis.say(SESSION_INSTRUCTION, allow_interruptions=True)

    # Keep the worker alive
    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
