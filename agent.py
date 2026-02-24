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
                temperature=0.4, 
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # --- 1. MEMORY LOADING ---
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ""
    if results:
        memories = [{"memory": r["memory"], "updated_at": r["updated_at"]} for r in results]
        memory_str = json.dumps(memories)
        logging.info(f"Loaded memories for {user_name}")
        initial_ctx.add_message(
            role="assistant", 
            content=f"System Context: User is {user_name}. Past facts: {memory_str}"
        )

    # --- 2. THE MEMORY LOGGING FIX ---
    # This matches the logic from your computer code that successfully notes memory.
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context to memory...")
        messages_formatted = []
        
        for item in chat_ctx.items:
            if not isinstance(item, llm.ChatMessage):
                continue
            
            # Use the content extraction logic from your computer code
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            
            # Avoid re-saving the initial context/system strings
            if memory_str and memory_str in content_str:
                continue
            
            if item.role in ['user', 'assistant']:
                messages_formatted.append({
                    "role": item.role,
                    "content": content_str.strip()
                })
        
        if messages_formatted:
            try:
                # Shield prevents the API call from being cancelled during the disconnect
                await asyncio.shield(mem0.add(messages_formatted, user_id="Ivan"))
                logging.info("Chat context saved to Mem0 successfully.")
            except Exception as e:
                logging.error(f"Failed to save to Mem0: {e}")
            
            # Short sleep to ensure the network buffer clears before process exit
            await asyncio.sleep(2)

    mcp_server = MCPServerSse(params={"url": os.environ.get("N8N_MCP_SERVER_URL")}, name="SSE MCP Server")
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx}, mcp_servers=[mcp_server]
    )

    session = AgentSession()

    # Real-time safeguard for mobile speech capture
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        logging.info(f"Friday is committing user speech: {msg.content}")
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

    # Register the shutdown hook to trigger when the job finishes
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, num_idle_processes=1))
