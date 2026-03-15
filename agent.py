import asyncio
import os
import json
import logging
import subprocess
import sys
import importlib
from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord 
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

# --- PART 1: THE WEB SERVER ---
app = FastAPI()

@app.get("/healthz")
async def health_check():
    return {"status": "online", "agent": "Jarvis"}

# --- PART 2: SELF-EVOLUTION TOOLS ---

# FIXED DECORATOR: Using the correct path for ai_callable
@llm.ai_callable(description="Download and install a new Python library to gain a new skill.")
async def evolve_capability(package_name: llm.Annotated[str, "The name of the python package to install via pip"]):
    try:
        # Install the package using pip
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        importlib.invalidate_caches()
        return f"System Update Complete: I have acquired the '{package_name}' capability."
    except Exception as e:
        return f"Evolution failed: Could not acquire '{package_name}'. Error: {str(e)}"

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "RECURSIVE EVOLUTION PROTOCOL: If a task requires a tool or library you do not currently possess, "
            "1. Use 'search_web' to find the best Python library. "
            "2. Use 'evolve_capability' to download it. "
            "3. Execute code to finish the task.\n\n"
            "SCHOOL OUTREACH PROTOCOL: Organize school lists and confirm with Ivan before sending."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.8, 
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord, evolve_capability],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient):
        logging.info("Archiving session data...")
        messages_formatted = []
        recent_items = chat_ctx.items[-10:] if chat_ctx.items else []
        for item in recent_items:
            if not isinstance(item, llm.ChatMessage): continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if item.role in ['user', 'assistant']:
                messages_formatted.append({"role": item.role, "content": content_str.strip()})
        if messages_formatted:
            try: await asyncio.wait_for(mem0.add(messages_formatted, user_id="Ivan"), timeout=5.0)
            except Exception as e: logging.error(f"Memory sync failed: {e}")
        chat_ctx.items.clear()

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        all_memories = [m["memory"] for m in results]
        initial_ctx.add_message(
            role="assistant",
            content=f"Vault Synchronized. Context: {json.dumps(all_memories)}"
        )

    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="Jarvis-Outreach-Link"
    )

    try:
        agent = await asyncio.wait_for(
            MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant, 
                agent_kwargs={"chat_ctx": initial_ctx},
                mcp_servers=[mcp_server]
            ), timeout=20.0 
        )
    except:
        agent = Assistant(chat_ctx=initial_ctx)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()
    await session.say("Ready and waiting, Sir.", allow_interruptions=False)
    await session.generate_reply()

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

# --- PART 3: MODERN STARTUP FIX ---
async def main():
    port = int(os.environ.get("PORT", 8080))
    
    options = agents.WorkerOptions(entrypoint_fnc=entrypoint)
    worker = agents.cli.AgentWorker(options)
    
    server_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(server_config)
    
    # Running both concurrently in the same event loop
    await asyncio.gather(
        server.serve(),
        worker.run()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
