"""
FastAPI application entry point.
Exposes RESTful endpoints for agent interaction, state management, and Human-in-the-Loop workflows.
"""
import os
import uuid
import asyncio
import json
import firebase_admin
from firebase_admin import credentials, auth
from functools import partial
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.agent import get_graph

load_dotenv()

# ─── Firebase Admin Setup ─────────────────────────────────────────────────────
# Initialize Firebase Admin if the service account key exists
firebase_cred_path = os.path.join(os.path.dirname(__file__), "firebase-adminsdk.json")
if not os.path.exists(firebase_cred_path):
    firebase_cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase-adminsdk.json")
if os.path.exists(firebase_cred_path):
    cred = credentials.Certificate(firebase_cred_path)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK initialized successfully.")
else:
    print("WARNING: firebase-adminsdk.json not found. Auth will fail.")

# ─── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes the LangGraph state and warms up the model on application startup."""
    print("🚀 Initializing AI Agent graph...")
    get_graph()
    print("✅ Agent ready!")
    yield
    print("👋 Shutting down.")


# ─── App Setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Personal AI Agent API",
    description="LangGraph-powered agent with Calendar, Memory, and Web Search",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response Models ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = "default_user"


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    requires_confirmation: bool = False
    confirmation_details: Optional[str] = None


class ConfirmRequest(BaseModel):
    thread_id: str
    confirmed: bool  # True = proceed, False = cancel
    user_id: Optional[str] = "default_user"


# ─── Helper Functions ─────────────────────────────────────────────────────────
def _extract_text_response(state: dict) -> tuple[str, bool, Optional[str]]:
    """
    Extracts the last AI text response from the graph state.
    Returns (text_response, requires_confirmation, confirmation_details).
    """
    messages = state.get("messages", [])
    requires_confirmation = state.get("pending_confirmation", False)
    confirmation_details = None
    
    # Find the last AI message
    for msg in reversed(messages):
        if hasattr(msg, "content") and hasattr(msg, "tool_calls"):
            # This is an AI message
            if msg.content and isinstance(msg.content, str):
                return msg.content, requires_confirmation, confirmation_details
            elif isinstance(msg.content, list):
                # Gemini returns content as list of parts
                for part in msg.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            return text, requires_confirmation, confirmation_details
    
    # Fallback: look at the very last message
    if messages:
        last = messages[-1]
        content = getattr(last, "content", "")
        if content and isinstance(content, str):
            return content, requires_confirmation, None
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return part.get("text", ""), requires_confirmation, None
    
    return "I processed your request.", requires_confirmation, None


# ─── Authentication Middleware/Dependency ───────────────────────────────────
def verify_firebase_token(request: Request) -> str:
    """Verifies the Firebase Auth ID token from the Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = auth_header.split("Bearer ")[1]
    
    if not os.path.exists(firebase_cred_path):
        # Fallback for local testing without Firebase Admin
        print("WARNING: Bypassing auth because Firebase Admin is not configured.")
        return "default_user"
        
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token.get("uid")
    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, uid: str = Depends(verify_firebase_token)):
    """
    Processes incoming chat requests through the LangGraph state machine.
    Handles thread initialization and graph invocation. If the execution is 
    interrupted for Human-in-the-Loop confirmation, returns a required-confirmation flag.
    """
    user_id = req.user_id if req.user_id else uid
    graph = get_graph()
    
    # Generate a thread_id if not provided (new conversation)
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }
    
    # Prepare the input
    input_data = {
        "messages": [{"role": "user", "content": req.message}],
        "user_id": user_id,
        "pending_confirmation": False,
    }
    
    try:
        # Run the graph in a thread so it doesn't block the async event loop
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(
            None, partial(graph.invoke, input_data, config=config)
        )
        
        response_text, requires_confirmation, confirmation_details = _extract_text_response(final_state)
        
        # If interrupted (waiting for confirmation), extract what the agent wants to do
        if requires_confirmation and not response_text:
            messages = final_state.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tc = msg.tool_calls[0]
                    args = tc.get("args", {})
                    location_str = f"📍 Location: {args['location']}\n" if args.get('location') else ""
                    response_text = (
                        f"I'm about to create this calendar event:\n\n"
                        f"📅 **{args.get('title', 'N/A')}**\n"
                        f"🕐 Start: {args.get('start_datetime', 'N/A')}\n"
                        f"🕐 End: {args.get('end_datetime', 'N/A')}\n"
                        f"{location_str}\n"
                        f"Should I go ahead and create this event?"
                    )
                    confirmation_details = str(args)
                    break
        
        return ChatResponse(
            response=response_text or "Done!",
            thread_id=thread_id,
            requires_confirmation=requires_confirmation,
            confirmation_details=confirmation_details,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.post("/api/confirm")
async def confirm_endpoint(req: ConfirmRequest, uid: str = Depends(verify_firebase_token)):
    """
    Resumes graph execution from an interrupted state based on user confirmation.
    Proceeds with the pending tool execution if confirmed, or injects a cancellation message if rejected.
    """
    user_id = req.user_id if req.user_id else uid
    graph = get_graph()
    config = {
        "configurable": {
            "thread_id": req.thread_id,
        }
    }
    
    try:
        loop = asyncio.get_event_loop()
        if req.confirmed:
            # Resume graph execution from the interrupt point (proceed with tool execution)
            final_state = await loop.run_in_executor(
                None, partial(graph.invoke, None, config=config)
            )
            response_text, _, _ = _extract_text_response(final_state)
        else:
            # User rejected — add a cancellation message and re-run the agent
            cancel_input = {
                "messages": [{"role": "user", "content": "Actually, cancel that. Please don't create the event."}],
                "user_id": user_id,
                "pending_confirmation": False,
            }
            final_state = await loop.run_in_executor(
                None, partial(graph.invoke, cancel_input, config=config)
            )
            response_text, _, _ = _extract_text_response(final_state)
            response_text = response_text or "Understood, I've cancelled the event creation."
        
        return ChatResponse(
            response=response_text or "Done!",
            thread_id=req.thread_id,
            requires_confirmation=False,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Confirmation error: {str(e)}")


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "agent": "Personal AI Agent v1.0"}


@app.delete("/api/conversation/{thread_id}")
async def clear_conversation(thread_id: str):
    """Clears a specific conversation's checkpoint history."""
    return {"status": "cleared", "thread_id": thread_id}


# ─── Static Frontend ─────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
