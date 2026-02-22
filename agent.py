import os
import json
import logging
import asyncio
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
            # Updated to Google Gemini Realtime
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
    # --- SPEED OPTIMIZATION: CONNECT IMMEDIATELY ---
    # Registering with the room first makes the agent appear instantly in the Sandbox.
    await ctx.connect()
    logging.info("Connected to room instantly.")

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context to memory...")
        messages_formatted = []

        for item in chat_ctx.items:
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)
            if memory_str and memory_str in content_str:
                continue

            if item.role in ['user', 'assistant']:
                messages_formatted.append({
                    "role": item.role,
                    "content": content_str.strip()
                })

        # Updated username to Ivan
        await mem0.add(messages_formatted, user_id="Ivan")
        logging.info("Chat context saved to memory.")

    session = AgentSession()
    mem0 = AsyncMemoryClient()
    # Updated username to Ivan
    user_name = 'Ivan'

    # Retrieve memories in the background while connection is active
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
            content=f"The user's name is {user_name}, and this is relevant context about him: {memory_str}."
        )

    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, 
        agent_kwargs={"chat_ctx": initial_ctx},
        mcp_servers=[mcp_server]
    )

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    # Added num_idle_processes to keep the agent "warm" on Railway
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        num_idle_processes=3
    ))
