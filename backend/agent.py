"""
Core LangGraph agent orchestration.
Handles the state graph configuration, LLM bindings, and Human-in-the-Loop workflows.
"""
import os
from typing import Annotated, Literal
from datetime import datetime

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_google_firestore import FirestoreSaver
from firebase_admin import firestore
from typing_extensions import TypedDict

from backend.tools.search_tools import web_search, get_current_time
from backend.tools.memory_tools import save_memory, search_memory, forget_memory, list_all_memories
from backend.tools.calendar_tools import create_calendar_event, list_upcoming_events

load_dotenv()

# ─── State Schema ─────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str
    pending_confirmation: bool  # True when we are waiting for user to confirm a calendar action


# Tools that require explicit human confirmation before executing
CONFIRMATION_TOOLS = {"create_calendar_event"}

ALL_TOOLS = [
    web_search,
    get_current_time,
    save_memory,
    search_memory,
    forget_memory,
    list_all_memories,
    create_calendar_event,
    list_upcoming_events,
]


# ─── LLM Setup ───────────────────────────────────────────────────────────────
def _get_llm():
    """Initializes and returns the Gemini LLM bound with available tools."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-lite",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.7,
    )
    return llm.bind_tools(ALL_TOOLS)


# ─── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a highly capable Personal AI Agent. Your job is to help the user manage their life intelligently.

Current date and time: {current_datetime}
User ID: {user_id}

## Your Capabilities:
1. **Long-Term Memory**: You can SAVE, SEARCH, LIST, and FORGET facts about the user using memory tools. ALWAYS search memory first before responding to find relevant context.
2. **Google Calendar**: You can LIST upcoming events and CREATE new events. 
3. **Web Search**: You can search the internet for up-to-date information.

## Critical Rules:
- **ALWAYS search memory first** before responding to any personal question or request.
- **ALWAYS use web_search** to answer questions about the weather, current time, news, sports, recent events, or anything you are not 100% certain about. Do NOT guess or hallucinate facts.
- **ALWAYS ask for confirmation** before creating a calendar event. State exactly what event you plan to create and wait for "yes", "confirm", or "proceed" before calling `create_calendar_event`.
- **ASK for missing info**: If a user asks to schedule something but doesn't provide a specific time or date, ask them for it before proceeding.
- **Be precise with dates**: When creating events, always convert relative times (like "tomorrow" or "next Monday") to explicit ISO 8601 datetime strings based on the current date above.
- **Be concise but warm**: Respond naturally and helpfully. Don't be overly verbose.

## Example flows:
- User: "Schedule a call with John" → You: "I'd love to help! When should I schedule it? What date and time works for you?"
- User: "I prefer mornings for meetings" → You call `save_memory` with this fact, then confirm: "Got it, I'll remember that!"
- User: "What's the latest news on AI?" → You call `web_search` and summarize the results with sources.
"""

def get_system_prompt(user_id: str) -> str:
    return SYSTEM_PROMPT.format(
        current_datetime=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p (IST)"),
        user_id=user_id,
    )


# ─── Agent Nodes ─────────────────────────────────────────────────────────────
def agent_node(state: AgentState):
    """
    Main LLM execution node. Evaluates the current state and determines the next sequence of tool calls or responses.
    """
    llm_with_tools = _get_llm()
    
    # Inject system context
    system_msg = SystemMessage(content=get_system_prompt(state.get("user_id", "default_user")))
    # Filter messages to bypass Gemini 3.1 thought_signature bug in LangChain
    safe_messages = []
    for msg in state["messages"]:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            # Convert the AIMessage with tool calls to a text-only AIMessage so the LLM remembers its action
            tool_summaries = [f"I called tool '{t['name']}' with args {t['args']}" for t in msg.tool_calls]
            safe_messages.append(AIMessage(content="\\n".join(tool_summaries)))
        elif isinstance(msg, ToolMessage):
            # Pass the tool result as a HumanMessage instead
            safe_messages.append(HumanMessage(content=f"[System: Tool '{msg.name}' returned: {msg.content}]"))
        else:
            safe_messages.append(msg)
            
    messages_with_system = [system_msg] + safe_messages
    
    response = llm_with_tools.invoke(messages_with_system)
    
    # Check if any of the pending tool calls require confirmation
    pending_confirmation = False
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            if tc["name"] in CONFIRMATION_TOOLS:
                pending_confirmation = True
                break
    
    return {
        "messages": [response],
        "pending_confirmation": pending_confirmation,
    }


def should_continue(state: AgentState) -> Literal["tools", "await_confirmation", "__end__"]:
    """Routing function to decide the next step."""
    last_message = state["messages"][-1]
    
    # If the last message has no tool calls, we are done
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END
    
    # If any tool call requires confirmation, wait
    if state.get("pending_confirmation", False):
        return "await_confirmation"
    
    # Otherwise, execute tools directly
    return "tools"


def await_confirmation_node(state: AgentState):
    """
    Passthrough node to handle Human-in-the-Loop interrupts.
    The checkpointer freezes the state here until client confirmation is received.
    """
    # Returns an empty dict to maintain state without modification
    # The interrupt is handled by LangGraph's checkpointer.
    return {}


# ─── Graph Construction ───────────────────────────────────────────────────────
def create_graph():
    """Compiles the LangGraph state machine with the Firestore checkpointer."""
    tool_node = ToolNode(ALL_TOOLS)
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("await_confirmation", await_confirmation_node)
    
    # Set entry point
    workflow.add_edge(START, "agent")
    
    # Conditional routing from agent
    workflow.add_conditional_edges("agent", should_continue)
    
    # After tools execute, go back to agent
    workflow.add_edge("tools", "agent")
    
    # After confirmation pause, go to tools to execute
    workflow.add_edge("await_confirmation", "tools")
    
    # Compile with Firestore checkpointer for conversation memory
    try:
        db = firestore.client()
        memory = FirestoreSaver(client=db, collection="Checkpoints")
    except Exception as e:
        print(f"Warning: Could not connect to Firestore for checkpoints. Using fallback. Error: {e}")
        from langgraph.checkpoint.memory import MemorySaver
        memory = MemorySaver()
        
    graph = workflow.compile(
        checkpointer=memory,
        interrupt_before=["await_confirmation"],
    )
    
    return graph


# Singleton graph instance
_graph = None


def get_graph():
    """Returns the singleton graph instance, initializing it if necessary."""
    global _graph
    if _graph is None:
        _graph = create_graph()
    return _graph
