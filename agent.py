import asyncio 
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, llm
from livekit.plugins import (
    noise_cancellation,
    openai
)
from livekit.plugins import google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration
import os
import json
import logging
load_dotenv()

class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        DIRECT_ACTION_INSTRUCTION = f"""
        {AGENT_INSTRUCTION}

        # DIRECT ACTION PROTOCOL
        1. When the user asks for information (time, weather, facts), CALL THE TOOL IMMEDIATELY.
        2. Do NOT say "Let me check that for you" or "One moment." 
        3. Execute the tool call first, then provide the answer in your very first spoken response.
        4. If you have memories (like the Friday date), include them only if they add value to the current request.
        5. Never require a second nudge. If you are asked once, you answer with the data immediately.
        6. Speak like a classy butler.
        """
        
        super().__init__(
            instructions=DIRECT_ACTION_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.7,
            ),
            tools=[
                get_weather,
                search_web,
                send_email
            ],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # 1. Connect to the room FIRST
    # This registers the agent's presence so LiveKit knows it's ready.
    logging.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()

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
                logging.info("Chat context saved to Mem0.")
            except Exception as e:
                logging.error(f"Failed to save to Mem0: {e}")
            await asyncio.sleep(3) 

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ''

    if results:
        memories = [
            {"memory": result["memory"], "updated_at": result["updated_at"]}
            for result in results
        ]
        memory_str = json.dumps(memories)
        initial_ctx.add_message(
            role="assistant",
            content=f"User: {user_name}. Memories: {memory_str}. Important: Use tools immediately when asked."
        )

    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, agent_kwargs={"chat_ctx": initial_ctx},
        mcp_servers=[mcp_server]
    )

    # 2. Start the session AFTER connecting
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # 3. Greet the user
    await session.generate_reply(
        instructions=f"{SESSION_INSTRUCTION}\nBriefly greet Ivan and give him the current time and weather update immediately without being asked.",
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
