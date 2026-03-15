import asyncio
import os
import json
import logging
from dotenv import load_dotenv

# New imports for the Keep-Alive server
from fastapi import FastAPI
import uvicorn

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord 
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

# --- PART 1: THE WEB SERVER (The Doorbell) ---
app = FastAPI()

@app.get("/healthz")
async def health_check():
    """Endpoint for cron-job.org to ping."""
    return {"status": "online", "agent": "Jarvis"}

# --- PART 2: YOUR ASSISTANT LOGIC ---
class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "SCHOOL OUTREACH PROTOCOL: You are authorized to search the web for school contact information. "
            "If Ivan provides a list of email addresses, or if you find them via search, "
            "your priority is to organize them and use the email tool to initiate contact. "
            "Always confirm the recipient list with Ivan before sending the first batch."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.8, 
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
            if not isinstance(item, llm.ChatMessage):
                continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if item.role in ['user', 'assistant']:
                messages_formatted.append({"role": item.role, "content": content_str.strip()})
        if messages_formatted:
            try:
                await asyncio.wait_for(mem0.add(messages_formatted, user_id="Ivan"), timeout=5.0)
            except Exception as e:
                logging.error(f"Memory sync failed: {e}")
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
            content=f"Vault Synchronized. Full history and school lists: {json.dumps(all_memories)}"
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
        logging.warning("MCP Outreach link failed. Running local protocols.")
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
    
    # --- INSTANT RESPONSE HACK ---
    # This greets you immediately while the brain is still loading context
    await session.say("Ready and waiting, Sir.", allow_interruptions=False)

    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan and ask if we should proceed with the school email list.",
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

# --- PART 3: THE RENDER STARTUP ---
if __name__ == "__main__":
    # Start the LiveKit agent in a background task
    loop = asyncio.get_event_loop()
    
    # Render provides the PORT env var automatically
    port = int(os.environ.get("PORT", 8080))
    
    # Run the worker and the web server together
    # Note: cli.run_app normally blocks, so we use a custom run logic for Render
    from livekit.agents import WorkerOptions
    options = WorkerOptions(entrypoint_fnc=entrypoint)
    
    # Start the Agent Worker in the background
    asyncio.ensure_future(agents.cli.run_app(options))
    
    # Start the Web Server (This is what Cron-job.org hits)
    uvicorn.run(app, host="0.0.0.0", port=port)
