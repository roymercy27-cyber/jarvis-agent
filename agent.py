import asyncio 
import os
import json
import logging
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

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "SCHOOL OUTREACH PROTOCOL: You are authorized to search the web for school contact information. "
            "If Ivan provides a list of email addresses, your priority is to organize them and use the email tool."
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
    # Setup infrastructure first
    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. QUICK MEMORY LOAD ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        all_memories = [m["memory"] for m in results]
        initial_ctx.add_message(
            role="assistant",
            content=f"Vault Synchronized: {json.dumps(all_memories)}"
        )

    # --- 2. TOOL LOADING (With a shorter timeout) ---
    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="Jarvis-Outreach-Link"
    )

    try:
        # Reduced timeout to 10s so Jarvis joins the room faster even if n8n is slow
        agent = await asyncio.wait_for(
            MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant, 
                agent_kwargs={"chat_ctx": initial_ctx},
                mcp_servers=[mcp_server]
            ), timeout=10.0 
        )
    except:
        logging.warning("MCP timed out. Entering room with local protocols.")
        agent = Assistant(chat_ctx=initial_ctx)

    # --- 3. START SESSION (VAD FIXED: Stops the mid-sentence cutting) ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
        # This prevents him from stopping mid-sentence
        min_interruption_duration=0.8,
        min_endpointing_delay=0.8,
    )

    # --- 4. THE CONNECTION (The working "Discord" style) ---
    await ctx.connect()

    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan and ask about the school outreach.",
    )

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient):
        messages_formatted = []
        recent_items = chat_ctx.items[-10:] if chat_ctx.items else []
        for item in recent_items:
            if not isinstance(item, llm.ChatMessage): continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if item.role in ['user', 'assistant']:
                messages_formatted.append({"role": item.role, "content": content_str.strip()})
        if messages_formatted:
            try: await mem0.add(messages_formatted, user_id="Ivan")
            except: pass

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

if __name__ == "__main__":
    # Ensure Port Binding for Railway/Render
    os.environ["LIVEKIT_HTTP_PORT"] = os.environ.get("PORT", "8081")
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
