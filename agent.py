import asyncio
import os
import json
import logging
import subprocess
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION 
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

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
        # STRONGER INSTRUCTIONS: Forces Jarvis to verify email strings before sending
        mcp_instructions = (
            f"{AGENT_INSTRUCTION}\n\n"
            "CRITICAL: You have MCP tools for Gmail. When you find a school's email via search, "
            "you must use the 'send_email' tool. You MUST provide a valid email string for the 'To' field. "
            "If you cannot find a clear email address, ask the user for clarification before sending."
        )
        
        super().__init__(
            instructions=mcp_instructions,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.4, 
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord, run_python_script],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    logging.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. MEMORY LOADING (Lean) ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ""
    if results:
        memories = [{"memory": r["memory"]} for r in results[-3:]]
        memory_str = json.dumps(memories)
        initial_ctx.add_message(
            role="assistant", 
            content=f"System Context: User is {user_name}. Recent facts: {memory_str}"
        )

    # --- 2. MCP & N8N INTEGRATION ---
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    try:
        if mcp_url:
            logging.info(f"Connecting to MCP at {mcp_url}...")
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="SSE MCP Server")
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
                ), timeout=20
            )
        else:
            agent = Assistant(chat_ctx=initial_ctx)
    except Exception as e:
        logging.error(f"MCP Connection failed: {e}. Falling back to basic agent.")
        agent = Assistant(chat_ctx=initial_ctx)

    session = AgentSession()

    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        content_text = "".join(msg.content) if isinstance(msg.content, list) else str(msg.content)
        asyncio.create_task(mem0.add(content_text, user_id=user_name))

    # --- 3. SESSION START ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(video_enabled=True),
    )

    logging.info("Jarvis ready.")
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
    # Ensure memory stays stable on Railway
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
