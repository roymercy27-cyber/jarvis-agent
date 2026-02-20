from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, JobProcess, llm
from livekit.plugins import (
    noise_cancellation,
    openai,
    silero, 
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

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

class Assistant(Agent):
    def __init__(self, chat_ctx=None, vad=None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                 voice="Charon",
                 temperature=0.8 # Added temperature here
            ),
            vad=vad,
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    prewarmed_vad = ctx.proc.userdata["vad"]
    user_name = 'Ivan' # Syncing all IDs to Ivan
    mem0 = AsyncMemoryClient()

    async def shutdown_hook(chat_ctx: ChatContext, mem_client: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving context...")
        messages_formatted = []

        for item in chat_ctx.items:
            # FIX: Only save actual chat messages, skip config updates
            if not isinstance(item, llm.ChatMessage):
                continue

            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)

            # Don't save the memory facts back into the memory (prevents duplicates)
            if memory_str and memory_str in content_str:
                continue

            if item.role in ['user', 'assistant']:
                messages_formatted.append({
                    "role": item.role,
                    "content": content_str.strip()
                })

        if messages_formatted:
            await mem_client.add(messages_formatted, user_id=user_name)
            logging.info(f"Context saved for {user_name}.")

    # 1. Fetch EVERYTHING relevant
    # We use search with a broad query to get the most relevant facts first
    results = await mem0.search(f"What should I know about {user_name}?", user_id=user_name)
    
    initial_ctx = ChatContext()
    memory_str = ''

    if results:
        memories = [{"memory": r["memory"], "updated_at": r.get("updated_at")} for r in results]
        memory_str = json.dumps(memories)
        # 2. Inject as SYSTEM role so the AI treats it as factual background
        initial_ctx.add_message(
            role="system",
            content=f"FACTS ABOUT THE USER ({user_name}): {memory_str}"
        )

    mcp_server = MCPServerSse(
        params={"url": os.environ.get("N8N_MCP_SERVER_URL")},
        cache_tools_list=True,
        name="SSE MCP Server"
    )

    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=Assistant, 
        agent_kwargs={"chat_ctx": initial_ctx, "vad": prewarmed_vad},
        mcp_servers=[mcp_server]
    )

    session = AgentSession(vad=prewarmed_vad)
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()
    await session.generate_reply(instructions=SESSION_INSTRUCTION)
    
    # Use agent.chat_ctx to ensure we get the full updated history
    ctx.add_shutdown_callback(lambda: shutdown_hook(agent.chat_ctx, mem0, memory_str))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm
    ))
