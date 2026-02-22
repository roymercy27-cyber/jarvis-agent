import asyncio
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import noise_cancellation, google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration

load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Charon",
                temperature=0.5,
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan' # Changed to Ivan for consistency

    # 1. ROBUST SHUTDOWN HOOK
    async def shutdown_hook(chat_ctx: ChatContext):
        logging.info(f"Finalizing session for {user_name}...")
        messages = []
        for item in chat_ctx.items:
            if item.role in ['user', 'assistant'] and item.content:
                text = "".join(item.content) if isinstance(item.content, list) else str(item.content)
                if text.strip():
                    messages.append({"role": item.role, "content": text})
        if messages:
            await mem0.add(messages, user_id=user_name)

    # Load memories at start
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    if results:
        mem_str = "\n".join([r['memory'] for r in results])
        initial_ctx.add_message(role="assistant", content=f"Context for {user_name}: {mem_str}")

    mcp_server = MCPServerSse(params={"url": os.environ.get("N8N_MCP_SERVER_URL")}, name="SSE MCP Server")
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
    )

    session = AgentSession()
    
    # 2. THE MOBILE FIX: REAL-TIME AUTO-SAVE
    # This captures your speech and saves it the moment you finish a sentence
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        logging.info("Auto-saving speech to Mem0...")
        asyncio.create_task(mem0.add(msg.content, user_id=user_name))

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(instructions=SESSION_INSTRUCTION)
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
