# 🤖 Personal AI Agent

A fully-featured personal assistant built with **LangGraph + Google Gemini 1.5 Flash** — completely free to run.

## ✨ Features

| Capability | Description |
|---|---|
| 🧠 **Long-Term Memory** | Remembers your preferences across sessions using ChromaDB |
| 📅 **Google Calendar** | Lists and creates events with confirmation flow |
| 🔍 **Web Search** | Searches the internet via Tavily for up-to-date info |
| 💬 **Multi-turn Chat** | Remembers conversation context via SQLite checkpointing |
| 🛡️ **Human-in-the-loop** | Asks for confirmation before creating calendar events |

## 🆓 Free Stack

- **LLM**: Google Gemini 1.5 Flash (via [Google AI Studio](https://aistudio.google.com) — free tier)
- **Web Search**: [Tavily](https://app.tavily.com) (free tier: 1,000 searches/month)
- **Memory**: ChromaDB (local, no cost)
- **Calendar**: Google Calendar API (free)
- **Backend**: FastAPI + LangGraph
- **Frontend**: Vanilla JS + CSS (glassmorphism design)

---

## 🚀 Quick Start

### 1. Clone & Install Dependencies

```bash
cd "Personal Ai Agent"
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Get Your Free API Keys

#### Google Gemini API Key (LLM)
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **"Create API Key"**
3. Copy the key

#### Tavily API Key (Web Search)
1. Go to [https://app.tavily.com/home](https://app.tavily.com/home)
2. Sign up for a free account
3. Copy your API key from the dashboard

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys:
# GOOGLE_API_KEY=...
# TAVILY_API_KEY=...
```

### 4. Google Calendar Setup (Optional)

> Skip this step if you don't need Calendar integration — all other features work without it.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **Google Calendar API**
4. Go to **APIs & Services → Credentials → Create OAuth 2.0 Client ID**
5. Choose **Desktop App**, then download the JSON file
6. Save it as `backend/credentials.json`

On first run, a browser window will open to authorize access. Your token is cached in `backend/token.json` for future runs.

### 5. Run the Backend

```bash
# Make sure your venv is active
source venv/bin/activate

# Start FastAPI server
uvicorn backend.main:app --reload --port 8000
```

### 6. Open the Frontend

Open `frontend/index.html` directly in your browser, **OR** the backend serves it at:

```
http://localhost:8000
```

---

## 💬 Example Conversations

```
You: Remember that I prefer meetings after 11 AM
Agent: Got it! I'll remember that you prefer meetings after 11 AM. ✅

You: What time do I prefer meetings?
Agent: Based on your saved preferences, you prefer meetings after 11 AM. 🧠

You: Search for the latest Python release
Agent: 🔍 [searches web] Python 3.13 was released in October 2024...

You: Schedule a team standup tomorrow at 10 AM for 30 minutes
Agent: I'll create this event:
  📅 Team Standup
  🕐 Start: 2025-01-16T10:00:00
  🕐 End: 2025-01-16T10:30:00
  Should I go ahead? [Confirm / Cancel]

You: Yes
Agent: ✅ Event created! View it here: https://calendar.google.com/...
```

---

## 📂 Project Structure

```
Personal Ai Agent/
├── backend/
│   ├── __init__.py
│   ├── main.py            # FastAPI server
│   ├── agent.py           # LangGraph agent definition
│   ├── credentials.json   # Google Calendar OAuth (you add this)
│   └── tools/
│       ├── __init__.py
│       ├── search_tools.py   # Tavily web search
│       ├── memory_tools.py   # ChromaDB long-term memory
│       └── calendar_tools.py # Google Calendar integration
├── frontend/
│   ├── index.html         # App shell
│   ├── style.css          # Premium glassmorphism UI
│   └── main.js            # Chat logic & API calls
├── data/                  # Auto-created: ChromaDB + SQLite
├── .env                   # Your API keys (don't commit!)
├── .env.example           # Template
├── requirements.txt
└── README.md
```

---

## 🔒 Privacy Notes

- **Memory** is stored locally in `data/chroma_db/` — never leaves your machine.
- **Conversation history** is stored locally in `data/agent_checkpoints.sqlite`.
- Only your chat messages are sent to Gemini API and Tavily API servers.
