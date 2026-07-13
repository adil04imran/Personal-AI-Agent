"""
Long-term semantic memory module.
Interfaces with Firebase Firestore Vector Search to persist, recall, and manage user-specific facts.
"""
import os
import uuid
from datetime import datetime
from langchain_core.tools import tool
from langchain_google_firestore import FirestoreVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

_vector_store = None
_db = None

def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db

def _get_vector_store():
    """Lazily initializes and returns the Firestore Vector Store."""
    global _vector_store
    if _vector_store is None:
        db = _get_db()
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001", 
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        _vector_store = FirestoreVectorStore(
            collection="Memories",
            embedding_service=embeddings,
            client=db,
        )
    return _vector_store


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
    store = _get_vector_store()
    memory_id = str(uuid.uuid4())
    store.add_texts(
        texts=[fact],
        metadatas=[{
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
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
    store = _get_vector_store()
    
    try:
        filter = FieldFilter("user_id", "==", user_id)
        docs = store.similarity_search(query=query, k=5, filters=filter)
        
        if not docs:
            return f"No memories found related to '{query}'."
            
        formatted = []
        for doc in docs:
            ts = doc.metadata.get("timestamp", "Unknown date")
            formatted.append(f"• {doc.page_content} (saved: {ts[:10]})")
            
        return "🧠 Relevant memories found:\n" + "\n".join(formatted)
        
    except Exception as e:
        return f"Error searching memory: {str(e)}"


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
    store = _get_vector_store()
    
    try:
        filter = FieldFilter("user_id", "==", user_id)
        docs = store.similarity_search(query=fact_to_forget, k=1, filters=filter)
        
        if not docs:
            return f"Could not find any memory matching '{fact_to_forget}'."
            
        memory_to_delete = docs[0]
        # In Firestore, the Document ID is stored as an internal reference. 
        # But for VectorStore abstraction, deleting by ID requires knowing it.
        # Alternatively, we can query Firestore directly to find the doc by content.
        
        # We can find the document by its page_content
        db = _get_db()
        query = db.collection("Memories").where(filter=FieldFilter("user_id", "==", user_id)).where(filter=FieldFilter("content", "==", memory_to_delete.page_content)).limit(1)
        results = list(query.stream())
        
        if results:
            results[0].reference.delete()
            return f"🗑️ Memory deleted: '{memory_to_delete.page_content}'"
        else:
            return "Failed to delete: Could not locate the exact document ID."
            
    except Exception as e:
        return f"Error forgetting memory: {str(e)}"


@tool
def list_all_memories(user_id: str = "default_user") -> str:
    """
    Retrieves the complete set of stored memories for a specific user.
    
    Args:
        user_id: The identifier for the user.
    
    Returns:
        All stored memories for this user.
    """
    db = _get_db()
    
    try:
        query = db.collection("Memories").where(filter=FieldFilter("user_id", "==", user_id))
        docs = list(query.stream())
        
        if not docs:
            return "No memories found for this user."
            
        formatted = []
        for doc in docs:
            data = doc.to_dict()
            content = data.get("content", "Unknown memory")
            # Metadata is nested in the vector store schema
            metadata = data.get("metadata", {})
            ts = metadata.get("timestamp", "Unknown date")
            formatted.append(f"• {content} (saved: {ts[:10]})")
            
        return f"🧠 All memories ({len(formatted)} total):\n" + "\n".join(formatted)
        
    except Exception as e:
        return f"Error listing memories: {str(e)}"
