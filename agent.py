from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, JobProcess, llm
from livekit.plugins import (
    noise_cancellation,
    openai,
    silero, # Added for prewarm
    google
)
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email
from mem0 import AsyncMemoryClient
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration
import os
import json
import logging
load_dotenv()

# --- PREWARM LOGIC ---
def prewarm(proc: JobProcess):
    # Pre-loads the VAD model into memory so the agent joins instantly
    proc.userdata["vad"] = silero.VAD.load()

class Assistant(Agent):
    def __init__(self, chat_ctx=None, vad=None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon"
            ),
            vad=vad, # Pass prewarmed VAD to the agent
            tools=[
                get_weather,
                search_web,
                send_email
            ],
            chat_ctx=chat_ctx
        )
        

async def entrypoint(ctx: agents.JobContext):
    # Retrieve prewarmed VAD from process memory
    prewarmed_vad = ctx.proc.userdata["vad"]

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context to memory...")
        messages_formatted = []

        for item in chat_ctx.items:
            # --- FIX: Only process ChatMessages (skips AgentConfigUpdate) ---
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
            # Synced user_id to "Ivan" to match your retrieval logic
            await mem0.add(messages_formatted, user_id="Ivan")
            logging.info("Chat context saved to memory.")


    # Initialize session with prewarmed VAD
    session = AgentSession(vad=prewarmed_vad)

    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    memory_str = ''

    if results:
        memories = [
            {
                "memory": result["memory"],
                "updated_at": result["updated_at"]
            }
            for result in results
        ]
        memory_str = json.dumps(memories)
        logging.info(f"Memories: {memory_str}")
        # Injecting as system role makes the memory "stick" better than assistant role
        initial_ctx.add_message(
            role="system",
            content=f"The user's name is {user_name}, and this is relvant context about him: {memory_str}."
        )

    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    # Pass VAD into the agent creation
    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, 
        agent_kwargs={"chat_ctx": initial_ctx, "vad": prewarmed_vad},
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

    await ctx.connect()

    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

    # Fixed: Use agent.chat_ctx to ensure we capture the full conversation
    ctx.add_shutdown_callback(lambda: shutdown_hook(agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm # Registered prewarm
    ))
