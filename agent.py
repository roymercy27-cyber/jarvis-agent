import asyncio
import os
import json
import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext
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
                temperature=0.5, # Lowered slightly for better tool accuracy
            ),
            tools=[get_weather, search_web, send_email],
            chat_ctx=chat_ctx
        )

async def entrypoint(ctx: agents.JobContext):
    # Connect immediately to reduce perceived latency
    await ctx.connect()
    
    mem0 = AsyncMemoryClient()
    user_name = 'Ivan'

    async def shutdown_hook(chat_ctx: ChatContext):
        logging.info(f"Session ending. Logging conversation for {user_name}...")
        
        # Format the current session's messages for Mem0
        messages_to_record = []
        for item in chat_ctx.items:
            # We filter for user and assistant messages only
            if item.role in ['user', 'assistant'] and hasattr(item, 'content'):
                content = item.content
                if isinstance(content, list):
                    content = " ".join([str(c) for c in content])
                
                messages_to_record.append({
                    "role": item.role,
                    "content": str(content).strip()
                })

        if messages_to_record:
            # Persistent conversation logging
            await mem0.add(messages_to_record, user_id=user_name)
            logging.info(f"Successfully saved {len(messages_to_record)} messages to Mem0.")

    # Retrieve past context
    results = await mem0.get_all(user_id=user_name)
    initial_ctx = ChatContext()
    
    if results:
        memory_summary = "\n".join([r['memory'] for r in results])
        initial_ctx.add_message(
            role="assistant",
            content=f"System: You are Jarvis. The user is {user_name}. Past context: {memory_summary}"
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

    session = AgentSession()
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(instructions=SESSION_INSTRUCTION)
    
    # Trigger memory save on disconnect
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx))

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        num_idle_processes=1
    ))
