import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import JobContext, JobProcess, llm
from livekit.agents.pipeline import VoicePipelineAgent 
from livekit.plugins import google, silero, noise_cancellation
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_time

load_dotenv()

def prewarm(proc: JobProcess):
    # Load VAD model into memory for instant voice detection
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"--- Protocol Initiated: {ctx.room.name} ---")

    # Setup the butler's persona
    chat_context = llm.ChatContext().append(
        role="system",
        text=AGENT_INSTRUCTION,
    )

    # Initialize the JARVIS Pipeline
    jarvis = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=google.STT(),
        llm=google.beta.realtime.RealtimeModel(
            voice="Charon", # High-quality British-style voice
            temperature=0.7,
        ),
        tts=google.TTS(),
        chat_ctx=chat_context,
        fnc_ctx=llm.FunctionContext()
    )

    # Register tools manually to the function context
    jarvis.fnc_ctx.add_callable(get_weather)
    jarvis.fnc_ctx.add_callable(search_web)
    jarvis.fnc_ctx.add_callable(send_email)
    jarvis.fnc_ctx.add_callable(get_time)

    # Start and Speak the greeting
    jarvis.start(ctx.room)
    await jarvis.say(SESSION_INSTRUCTION, allow_interruptions=True)

    try:
        while ctx.room.is_connected():
            await asyncio.sleep(1)
    except Exception as e:
        print(f"System Error: {e}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
