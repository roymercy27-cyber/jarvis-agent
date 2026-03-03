import asyncio 
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord # Added your mobile tools back
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        # HUMAN-LIKE PERSONA: Sophisticated & Calm
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "You are JARVIS. Your tone is sophisticated, calm, and British. "
            "Ivan is your priority. Reference past memories naturally. "
            "If asked about a topic like ice cream, differentiate between today's "
            "context and past discussions to maintain continuity."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.6, 
            ),
            tools=[
                get_weather,
                search_web,
                mobile_whatsapp,
                mobile_discord
            ],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context to memory...")
        messages_formatted = []
        # OOM Guard: Only save the last 6 messages to keep memory lean
        recent_items = chat_ctx.items[-6:] if chat_ctx.items else []
        
        for item in recent_items:
            if not isinstance(item, llm.ChatMessage):
                continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if memory_str and memory_str in content_str:
                continue
            if item.role in ['user', 'assistant']:
                messages_formatted.append({
                    "role": item.role,
                    "content": content_str.strip()
                })
        
        if messages_formatted:
            try:
                await asyncio.wait_for(mem0.add(messages_formatted, user_id="Ivan"), timeout=5.0)
                logging.info("Chat context saved to Mem0.")
            except Exception as e:
                logging.error(f"Failed to save to Mem0: {e}")
        
        chat_ctx.items.clear() # Clear RAM immediately

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- MEMORY LOADING ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ''

    if results:
        # Prioritize recent memories for accuracy
        sorted_memories = sorted(results, key=lambda x: x.get('updated_at', ''), reverse=True)
        relevant_memories = sorted_memories[:5]
        memory_str = json.dumps(relevant_memories)
        initial_ctx.add_message(
            role="assistant",
            content=f"User: {user_name}. Current context and past preferences: {memory_str}."
        )

    # --- MCP INTEGRATION ---
    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    # Wrap in timeout to prevent "hanging" during join
    try:
        agent = await asyncio.wait_for(
            MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant, 
                agent_kwargs={"chat_ctx": initial_ctx},
                mcp_servers=[mcp_server]
            ), timeout=15.0
        )
    except:
        logging.warning("MCP timed out. Joining without external tools.")
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

    # Connect to room AFTER session setup
    await ctx.connect()

    # Initial Greeting
    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan in your signature Jarvis style.",
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    # num_idle_processes=0 is key for Railway OOM errors
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
