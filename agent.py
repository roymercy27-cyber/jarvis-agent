import asyncio 
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm, RoomOptions
from livekit.plugins import noise_cancellation, google

# Import your custom prompts and tools
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email
from mem0 import AsyncMemoryClient

load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        # Lower temperature to 0.6 for more stable tool calls
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.6, 
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context to memory...")
        messages_formatted = []

        for item in chat_ctx.items:
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
                await mem0.add(messages_formatted, user_id="Ivan")
                logging.info("Chat context saved.")
            except Exception as e:
                logging.error(f"Save failed: {e}")
            
            await asyncio.sleep(2) 

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    # Load memories from Mem0
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ''

    if results:
        memories = [{"memory": r["memory"], "updated_at": r["updated_at"]} for r in results]
        memory_str = json.dumps(memories)
        initial_ctx.add_message(
            role="assistant",
            content=f"User: {user_name}. Context: {memory_str}. Use tools immediately when asked."
        )

    # Simplified Agent creation (No MCP/n8n overhead)
    agent = Assistant(chat_ctx=initial_ctx)

    await session.start(
        room=ctx.room,
        agent=agent,
        # Optimization: Explicitly using RoomOptions (newer API)
        room_options=RoomOptions(
            video_out_enabled=True,
        ),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()

    # Direct instruction to prevent "nudging" for the first response
    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nGreet Ivan and proactively provide the current time/weather if relevant to his memories.",
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    # --- CRITICAL RAILWAY MEMORY FIX ---
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            max_parallel_jobs=1,      # Process only 1 call at a time to save RAM
            num_warmed_workers=0,     # Stop Railway from pre-loading extra copies of the agent
        )
    )
