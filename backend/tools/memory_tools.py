"""
Long-term semantic memory module.
Interfaces with a local ChromaDB vector database to persist, recall, and manage user-specific facts.
"""
import os
import uuid
from datetime import datetime
from langchain_core.tools import tool
import chromadb
from chromadb.config import Settings

# Initialize ChromaDB with a persistent local directory
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma_db")
_client = None
_collection = None


def _get_collection():
    """Lazily initializes and returns the ChromaDB collection for user memories."""
    global _client, _collection
    if _collection is None:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = _client.get_or_create_collection(
            name="user_memories",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


@tool
def save_memory(fact: str, user_id: str = "default_user") -> str:
    """
    Persists a user-specific fact or preference into long-term vector storage.
    Utilized for retaining important contextual information across sessions.
    
    Examples:
    - "User prefers meetings after 11 AM"
    - "User's name is Alex"
    - "User works in the London timezone"
    
    Args:
        fact: The fact or preference to remember.
        user_id: The identifier for the user (defaults to 'default_user').
    
    Returns:
        Confirmation message.
    """
    collection = _get_collection()
    memory_id = str(uuid.uuid4())
    collection.add(
        documents=[fact],
        metadatas=[{
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "fact": fact,
        }],
        ids=[memory_id],
    )
    return f"✅ Memory saved: '{fact}'"


@tool
def search_memory(query: str, user_id: str = "default_user") -> str:
    """
    Performs a semantic search against the long-term memory vector database.
    Should be invoked prior to processing queries requiring historical context or user preferences.
    
    Args:
        query: What you're looking for in memory (e.g., "meeting preferences", "user name").
        user_id: The identifier for the user (defaults to 'default_user').
    
    Returns:
        A list of relevant memories, or a message indicating none were found.
    """
    collection = _get_collection()
    
    # Check if collection is empty first
    if collection.count() == 0:
        return "No memories found. Memory is empty."
    
    results = collection.query(
        query_texts=[query],
        n_results=min(5, collection.count()),
        where={"user_id": user_id},
    )
    
    if not results["documents"] or not results["documents"][0]:
        return f"No memories found related to '{query}'."
    
    memories = results["documents"][0]
    metadatas = results["metadatas"][0]
    
    formatted = []
    for mem, meta in zip(memories, metadatas):
        ts = meta.get("timestamp", "Unknown date")
        formatted.append(f"• {mem} (saved: {ts[:10]})")
    
    return "🧠 Relevant memories found:\n" + "\n".join(formatted)


@tool
def forget_memory(fact_to_forget: str, user_id: str = "default_user") -> str:
    """
    Removes a specific memory from the vector database.
    Performs a semantic search to locate the closest matching memory and deletes it.
    
    Args:
        fact_to_forget: A description of what to forget. We will search for the 
                        closest matching memory and delete it.
        user_id: The identifier for the user.
    
    Returns:
        Confirmation of what was deleted, or a message if nothing was found.
    """
    collection = _get_collection()
    
    if collection.count() == 0:
        return "Memory is already empty. Nothing to forget."
    
    # Find the closest matching memory
    results = collection.query(
        query_texts=[fact_to_forget],
        n_results=1,
        where={"user_id": user_id},
    )
    
    if not results["documents"] or not results["documents"][0]:
        return f"Could not find any memory matching '{fact_to_forget}'."
    
    memory_to_delete = results["documents"][0][0]
    memory_id = results["ids"][0][0]
    
    collection.delete(ids=[memory_id])
    return f"🗑️ Memory deleted: '{memory_to_delete}'"


@tool
def list_all_memories(user_id: str = "default_user") -> str:
    """
    Retrieves the complete set of stored memories for a specific user.
    
    Args:
        user_id: The identifier for the user.
    
    Returns:
        All stored memories for this user.
    """
    collection = _get_collection()
    
    if collection.count() == 0:
        return "Memory is completely empty. I don't remember anything yet."
    
    results = collection.get(where={"user_id": user_id})
    
    if not results["documents"]:
        return "No memories found for this user."
    
    formatted = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        ts = meta.get("timestamp", "Unknown date")
        formatted.append(f"• {doc} (saved: {ts[:10]})")
    
    return f"🧠 All memories ({len(formatted)} total):\n" + "\n".join(formatted)
