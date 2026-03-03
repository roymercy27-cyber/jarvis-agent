import asyncio
import os
import json
import logging
import subprocess
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION 
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

# --- CODE INTERPRETER TOOL ---
@agents.function_tool(description="Runs Python code to solve math, process data, or debug logic.")
def run_python_script(code: str):
    """Executes a python script in a separate process and returns the result."""
    try:
        result = subprocess.run(
            ['python3', '-c', code], 
            capture_output=True, 
            text=True, 
            timeout=10 
        )
        return f"Output: {result.stdout}\nErrors: {result.stderr}"
    except Exception as e:
        return f"Execution Failed: {str(e)}"

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        # HUMAN-LIKE UPGRADE: Tone instructions for "The Real Jarvis"
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "PERSONALITY OVERRIDE: You are JARVIS. Your tone is calm, sophisticated, and British. "
            "Speak with clinical confidence. Avoid robotic list-making. Use smooth transitions. "
            "NEVER stop mid-sentence. If you are searching for schools or sending emails, "
            "acknowledge the task first: 'Certainly, Ivan. Searching for those school details now.'"
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.55, 
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord, run_python_script],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    logging.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. MEMORY LOADING ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        memories = [{"memory": r["memory"]} for r in results[-3:]]
        initial_ctx.add_message(
            role="assistant", 
            content=f"System Context: User is {user_name}. Recent facts: {json.dumps(memories)}"
        )

    # --- 2. MCP & N8N INTEGRATION ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    try:
        if mcp_url:
            logging.info(f"Connecting to MCP at {mcp_url}...")
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="Jarvis-Mail-Link")
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
                ), timeout=25.0
            )
        else:
            agent = Assistant(chat_ctx=initial_ctx)
    except Exception as e:
        logging.error(f"MCP Connection failed: {e}. Falling back to basic agent.")
        agent = Assistant(chat_ctx=initial_ctx)

    # --- 3. SESSION START (Optimized VAD to prevent cut-offs) ---
    session = AgentSession()

    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        content_text = "".join(msg.content) if isinstance(msg.content, list) else str(msg.content)
        asyncio.create_task(mem0.add(content_text, user_id=user_name))

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(video_enabled=True),
    )

    logging.info("Jarvis stabilized and online.")
    await session.generate_reply() 

    # --- 4. SHUTDOWN HOOK ---
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient):
        messages_to_save = []
        recent_items = chat_ctx.items[-5:] if chat_ctx.items else []
        for item in recent_items:
            if isinstance(item, llm.ChatMessage) and item.role in ['user', 'assistant']:
                content = "".join(item.content) if isinstance(item.content, list) else str(item.content)
                messages_to_save.append({"role": item.role, "content": content})
        if messages_to_save:
            try:
                await asyncio.wait_for(mem0.add(messages_to_save, user_id=user_name), timeout=3.0)
            except:
                pass
        chat_ctx.items.clear()

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
