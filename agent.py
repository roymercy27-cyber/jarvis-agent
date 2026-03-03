import asyncio
import os
import json
import logging
import subprocess
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm, vad
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION 
from tools import get_weather, search_web, mobile_whatsapp, mobile_discord
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        # HUMAN-LIKE UPGRADE: Sophisticated Persona
        jarvis_persona = (
            f"{AGENT_INSTRUCTION}\n\n"
            "TONE: Sophisticated, calm, British. Avoid robotic lists. "
            "MEMORY PROTOCOL: You have access to Ivan's past preferences. "
            "Stay consistent with previous facts. If a topic (like ice cream) comes up, "
            "reference the specific context Ivan provided today vs last week."
        )
        
        super().__init__(
            instructions=jarvis_persona,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.6, # Slightly higher for more fluid, human-like phrasing
            ),
            tools=[get_weather, search_web, mobile_whatsapp, mobile_discord],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    logging.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")

    # --- SPEED OPTIMIZATION: Concurrent Loading ---
    # We load memory and connect to n8n at the same time to save seconds
    logging.info("Initializing Memory and MCP links...")
    
    async def load_memories():
        try:
            # Search specifically for relevant context to avoid mixing up old topics
            return await mem0.get_all(user_id=user_name)
        except: return []

    async def connect_mcp():
        if not mcp_url: return None
        try:
            mcp_server = MCPServerSse(params={"url": mcp_url}, name="Jarvis-Link")
            return mcp_server
        except: return None

    # Run both tasks in parallel
    memory_results, mcp_server = await asyncio.gather(load_memories(), connect_mcp())

    # --- MEMORY REFINEMENT ---
    initial_ctx = ChatContext()
    if memory_results:
        # Sort by 'updated_at' to ensure we prioritize current info
        sorted_memories = sorted(memory_results, key=lambda x: x.get('updated_at', ''), reverse=True)
        # Only inject the 4 most relevant/recent memories to prevent "memory soup"
        relevant_memories = [{"fact": m["memory"]} for m in sorted_memories[:4]]
        initial_ctx.add_message(
            role="assistant", 
            content=f"Ivan's Profile & Recent Context: {json.dumps(relevant_memories)}"
        )

    # --- AGENT CREATION ---
    try:
        if mcp_server:
            agent = await asyncio.wait_for(
                MCPToolsIntegration.create_agent_with_tools(
                    agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
                ), timeout=15.0
            )
        else:
            agent = Assistant(chat_ctx=initial_ctx)
    except Exception as e:
        logging.error(f"MCP Timeout: {e}")
        agent = Assistant(chat_ctx=initial_ctx)

    # --- STABILITY: Anti-Cutoff Session ---
    # We use a custom VAD threshold to ensure Jarvis doesn't stop mid-sentence
    session = AgentSession()

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            # Force the silence threshold higher so Jarvis is more patient
        ),
    )

    logging.info("Jarvis is online and stabilized.")
    await session.generate_reply() 

    # --- CLEAN SHUTDOWN & SAVE ---
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient):
        # Only save the core summary of this specific session
        if chat_ctx.items:
            recent_msgs = [item for item in chat_ctx.items[-6:] if isinstance(item, llm.ChatMessage)]
            msgs_to_save = [{"role": m.role, "content": "".join(m.content)} for m in recent_msgs]
            try:
                await asyncio.wait_for(mem0.add(msgs_to_save, user_id=user_name), timeout=4.0)
            except: pass
        chat_ctx.items.clear()

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=0))
