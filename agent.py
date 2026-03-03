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
            "SYSTEM OVERRIDE: You have full access to ALL historical memories in Mem0. "
            "Do not ignore old data. If Ivan sets a reminder for the future, "
            "track it as a primary objective. Maintain perfect continuity across weeks and months."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.6, 
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Saving session context to long-term memory...")
        messages_formatted = []
        # We save the tail end of the conversation to capture new decisions/reminders
        recent_items = chat_ctx.items[-10:] if chat_ctx.items else []
        
        for item in recent_items:
            if not isinstance(item, llm.ChatMessage):
                continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if item.role in ['user', 'assistant']:
                messages_formatted.append({
                    "role": item.role,
                    "content": content_str.strip()
                })
        
        if messages_formatted:
            try:
                # Reliability check: wait for Mem0 to confirm storage
                await asyncio.wait_for(mem0.add(messages_formatted, user_id="Ivan"), timeout=5.0)
            except Exception as e:
                logging.error(f"Memory storage failed: {e}")
        
        chat_ctx.items.clear()

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- FULL ARCHIVE LOADING ---
    # We pull everything. No more 4-day or 5-item limits.
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    
    if results:
        # We pass the entire history string to the LLM. 
        # This ensures 15-day reminders are always in the context window.
        all_memories = [m["memory"] for m in results]
        memory_payload = json.dumps(all_memories)
        
        initial_ctx.add_message(
            role="assistant",
            content=f"Vault Status: Fully Synchronized. Ivan's Entire History and Reminders: {memory_payload}"
        )

    # --- MCP INTEGRATION ---
    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    try:
        agent = await asyncio.wait_for(
            MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant, 
                agent_kwargs={"chat_ctx": initial_ctx},
                mcp_servers=[mcp_server]
            ), timeout=15.0
        )
    except:
        logging.warning("MCP timed out. Running on local protocols.")
        agent = Assistant(chat_ctx=initial_ctx)

    # --- SESSION START ---
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()

    # The greeting now has the context of all past conversations
    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nBriefly greet Ivan. If there is a pending reminder in the history, mention it now.",
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_payload if results else ""))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
