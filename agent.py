import asyncio
import os
import json
import logging
from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm, Worker
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
    """Endpoint for Render health checks and heartbeat."""
    return {"status": "online", "agent": "Jarvis"}

# --- PART 2: THE ASSISTANT ---
class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "SCHOOL OUTREACH PROTOCOL: Authorized to search for school contact info. "
            "Priority: organize email lists and use the email tool. "
            "Always confirm recipient lists with Ivan before sending."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.4, 
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord],
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

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    
    # Load Memory
    results = await mem0.get_all(user_id='Ivan')
    initial_ctx = ChatContext()
    if results:
        initial_ctx.add_message(role="assistant", content=f"Vault Synchronized: {json.dumps([m['memory'] for m in results])}")

    # MCP Setup
    mcp_server = MCPServerSse(params={"url": os.environ.get("N8N_MCP_SERVER_URL")}, cache_tools_list=True, name="Jarvis-Outreach-Link")

    try:
        agent = await asyncio.wait_for(
            MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
            ), timeout=20.0 
        )
    except:
        agent = Assistant(chat_ctx=initial_ctx)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(video_enabled=True, noise_cancellation=noise_cancellation.BVC()),
    )
    await ctx.connect()
    await session.generate_reply(instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan and ask about the school email list.")
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

# --- PART 3: THE DUAL-RUNNER ---
async def main():
    # Use the port Render provides
    port = int(os.environ.get("PORT", 8080))
    
    # 1. Initialize the LiveKit Worker manually
    # This bypasses the CLI and prevents the "Missing command" error
    options = agents.WorkerOptions(entrypoint_fnc=entrypoint)
    worker = Worker(options)
    
    # 2. Setup the FastAPI Server config
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    
    # 3. Run both concurrently in the same event loop
    logging.info(f"System Online. Starting Jarvis on port {port}...")
    await asyncio.gather(
        worker.run(),
        server.serve()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
