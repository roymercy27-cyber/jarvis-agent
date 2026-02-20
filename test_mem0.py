from dotenv import load_dotenv
from mem0 import MemoryClient
import logging
import json

load_dotenv()

# Global config to keep everything in sync
USER_NAME = 'Ivan'
mem0 = MemoryClient()

def add_memory():
    """
    Manually injects conversation history. 
    Mem0 will automatically extract facts like 'Likes Linkin Park' 
    from this list of messages.
    """
    messages_formatted = [
        {"role": "user", "content": "I really like Linkin Park."},
        {"role": "assistant", "content": "That is a good choice. What is your favorite song by them?"},
        {"role": "user", "content": "Probably Numb or In the End. Also, I live in London now."},
        {"role": "assistant", "content": "Excellent choices, Sir. I have noted your location as London."}
    ]

    # Storing under USER_NAME ensure the agent can find it later
    mem0.add(messages_formatted, user_id=USER_NAME)
    logging.info(f"✓ Memory sync complete for {USER_NAME}")

def get_comprehensive_memory():
    """
    Instead of searching for one specific thing, we ask a broad 
    question to get ALL relevant personality traits and facts.
    """
    # Broad query to catch music, location, and persona details
    query = f"Provide a full profile of {USER_NAME}'s preferences, locations, and interests."
    
    # Increase the limit if you have a lot of memories
    results = mem0.search(query, user_id=USER_NAME, limit=10)

    memories = [
        {
            "memory": result["memory"],
            "updated_at": result.get("updated_at", "N/A")
        }
        for result in results
    ]
    
    memories_str = json.dumps(memories, indent=2)
    print(f"--- CURRENT BRAIN STATE FOR {USER_NAME} ---")
    print(memories_str)
    return memories_str

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 1. Run this once to seed the data
    # add_memory() 
    
    # 2. Check what Jarvis actually knows
    get_comprehensive_memory()
