/**
 * Application Entry Point & UI Controller
 * Manages the Chat Interface, REST API integrations, and Human-in-the-Loop workflows.
 */
import { auth, provider, signInWithPopup, signOut, onAuthStateChanged } from './firebase-config.js';

// ── Configuration ───────────────────────────────────────────────────────────
const API_BASE = 'http://localhost:8000';
let USER_ID  = null; // Set dynamically via Firebase Auth
let AUTH_TOKEN = null;

// ── State ───────────────────────────────────────────────────────────────────
let currentThreadId    = null;
let isThinking         = false;
let pendingConfirmation = false;
let conversations      = JSON.parse(localStorage.getItem('ag_conversations') || '[]');
let recognition        = null;
let isRecording        = false;
let isMuted            = true;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const messagesList        = document.getElementById('messages-list');
const messagesWrapper     = document.getElementById('messages-wrapper');
const welcomeScreen       = document.getElementById('welcome-screen');
const chatInput           = document.getElementById('chat-input');
const sendBtn             = document.getElementById('send-btn');
const statusDot           = document.getElementById('status-dot');
const confirmationBanner  = document.getElementById('confirmation-banner');
const confirmDetail       = document.getElementById('confirm-detail');
const btnConfirm          = document.getElementById('btn-confirm-action');
const btnCancel           = document.getElementById('btn-cancel-action');
const conversationList    = document.getElementById('conversation-list');
const btnNewChat          = document.getElementById('btn-new-chat');
const btnClear            = document.getElementById('btn-clear');
const btnSidebarToggle    = document.getElementById('btn-sidebar-toggle');
const sidebar             = document.querySelector('.sidebar');
const suggestionGrid      = document.getElementById('suggestion-grid');
const btnLogin            = document.getElementById('btn-login');
const btnLogout           = document.getElementById('btn-logout');
const userProfile         = document.getElementById('user-profile');
const userAvatar          = document.getElementById('user-avatar');
const btnVoice            = document.getElementById('btn-voice');
const btnTts              = document.getElementById('btn-tts');


// ── Init ──────────────────────────────────────────────────────────────────
function init() {
  renderConversationList();
  
  // Auth State Observer
  onAuthStateChanged(auth, async (user) => {
    if (user) {
      USER_ID = user.uid;
      AUTH_TOKEN = await user.getIdToken();
      btnLogin.style.display = 'none';
      userProfile.style.display = 'flex';
      userAvatar.src = user.photoURL || 'default-avatar.png';
      chatInput.disabled = false;
      chatInput.placeholder = 'Ask me anything…';
    } else {
      USER_ID = null;
      AUTH_TOKEN = null;
      btnLogin.style.display = 'block';
      userProfile.style.display = 'none';
      chatInput.disabled = true;
      chatInput.placeholder = 'Please sign in to chat...';
    }
  });

  // Auth Buttons
  btnLogin.addEventListener('click', () => {
    signInWithPopup(auth, provider).catch(err => console.error("Login failed", err));
  });
  
  btnLogout.addEventListener('click', () => {
    signOut(auth);
    startNewChat();
  });
  
  // Auto-resize textarea
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + 'px';
    sendBtn.disabled = chatInput.value.trim() === '';
  });

  // Send on Enter, new line on Shift+Enter
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled && !isThinking) handleSend();
    }
  });

  // Send button
  sendBtn.addEventListener('click', () => {
    if (!isThinking) handleSend();
  });

  // Confirmation buttons
  btnConfirm.addEventListener('click', () => handleConfirmation(true));
  btnCancel.addEventListener('click',  () => handleConfirmation(false));

  // New chat
  btnNewChat.addEventListener('click', startNewChat);

  // Clear chat
  btnClear.addEventListener('click', () => {
    if (confirm('Clear this conversation?')) {
      messagesList.innerHTML = '';
      welcomeScreen.style.display = '';
      currentThreadId = null;
      pendingConfirmation = false;
      hideBanner();
    }
  });

  // Sidebar toggle
  btnSidebarToggle.addEventListener('click', () => {
    if (window.innerWidth <= 640) {
      sidebar.classList.toggle('mobile-open');
    } else {
      sidebar.classList.toggle('collapsed');
    }
  });

  // Suggestion cards
  suggestionGrid?.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
      const msg = card.dataset.message;
      chatInput.value = msg;
      chatInput.dispatchEvent(new Event('input'));
      handleSend();
    });
  });

  // ── Web Speech API Setup ──
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    
    recognition.onstart = () => {
      isRecording = true;
      btnVoice.classList.add('recording');
      chatInput.placeholder = "Listening...";
    };
    
    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        transcript += event.results[i][0].transcript;
      }
      chatInput.value = transcript;
      chatInput.dispatchEvent(new Event('input'));
    };
    
    recognition.onerror = (event) => {
      console.error("Speech recognition error", event.error);
      stopRecording();
    };
    
    recognition.onend = () => {
      stopRecording();
      if (chatInput.value.trim() !== '' && !isThinking) {
        handleSend();
      }
    };
  } else {
    if (btnVoice) btnVoice.style.display = 'none';
  }

  btnVoice?.addEventListener('click', () => {
    if (isRecording) stopRecording();
    else startRecording();
  });

  btnTts?.addEventListener('click', () => {
    isMuted = !isMuted;
    btnTts.setAttribute('data-state', isMuted ? 'muted' : 'unmuted');
    if (isMuted) window.speechSynthesis.cancel();
  });
}

function startRecording() {
  if (recognition && !isRecording) {
    chatInput.value = '';
    recognition.start();
  }
}

function stopRecording() {
  if (recognition && isRecording) {
    recognition.stop();
    isRecording = false;
    btnVoice.classList.remove('recording');
    chatInput.placeholder = USER_ID ? "Ask me anything…" : "Please sign in to chat...";
  }
}


// ── Chat Session Management ───────────────────────────────────────────────
function startNewChat() {
  currentThreadId = null;
  pendingConfirmation = false;
  messagesList.innerHTML = '';
  welcomeScreen.style.display = '';
  hideBanner();
  chatInput.value = '';
  chatInput.style.height = 'auto';
  sendBtn.disabled = true;
  renderConversationList();
}

function saveConversation(threadId, firstMessage) {
  const existing = conversations.find(c => c.id === threadId);
  if (!existing) {
    conversations.unshift({
      id: threadId,
      title: firstMessage.slice(0, 36) + (firstMessage.length > 36 ? '…' : ''),
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
    if (conversations.length > 20) conversations.pop();
    localStorage.setItem('ag_conversations', JSON.stringify(conversations));
    renderConversationList();
  }
}

function renderConversationList() {
  conversationList.innerHTML = '';
  if (conversations.length === 0) {
    conversationList.innerHTML = '<p style="font-size:0.75rem;color:var(--text-muted);padding:8px 12px;">No conversations yet</p>';
    return;
  }
  conversations.forEach(conv => {
    const el = document.createElement('button');
    el.className = 'conv-item' + (conv.id === currentThreadId ? ' active' : '');
    el.setAttribute('aria-label', `Open conversation: ${conv.title}`);
    el.innerHTML = `<span class="conv-title">${escapeHTML(conv.title)}</span><span class="conv-meta">${conv.time}</span>`;
    el.addEventListener('click', () => {
      currentThreadId = conv.id;
      messagesList.innerHTML = '';
      welcomeScreen.style.display = 'none';
      appendSystemMessage('Conversation loaded. Continue chatting!');
      renderConversationList();
    });
    conversationList.appendChild(el);
  });
}


// ── Send & Receive ────────────────────────────────────────────────────────
async function handleSend() {
  const text = chatInput.value.trim();
  if (!text || isThinking) return;

  if (!text || isThinking) return;

  welcomeScreen.style.display = 'none';
  appendMessage('user', text);

  chatInput.style.height = 'auto';
  sendBtn.disabled = true;

  setThinking(true);
  const thinkingId = appendThinking();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AUTH_TOKEN}`
      },
      body: JSON.stringify({
        message: text,
        thread_id: currentThreadId,
        user_id: USER_ID,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Server error');
    }

    const data = await res.json();

    if (!currentThreadId) {
      currentThreadId = data.thread_id;
      saveConversation(currentThreadId, text);
    }

    removeThinking(thinkingId);
    setThinking(false);

    const toolTags = detectTools(data.response);
    appendMessage('ai', data.response, toolTags);

    if (data.requires_confirmation) {
      pendingConfirmation = true;
      showBanner(data.confirmation_details || data.response);
    }
    
    speak(data.response);

  } catch (err) {
    removeThinking(thinkingId);
    setThinking(false);
    appendMessage('ai', `❌ Error: ${err.message}. Please check the server logs.`);
  }
}

async function handleConfirmation(confirmed) {
  hideBanner();
  pendingConfirmation = false;
  setThinking(true);
  const thinkingId = appendThinking();

  try {
    const res = await fetch(`${API_BASE}/api/confirm`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AUTH_TOKEN}`
      },
      body: JSON.stringify({
        thread_id: currentThreadId,
        confirmed,
        user_id: USER_ID,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Server error');
    }

    const data = await res.json();
    removeThinking(thinkingId);
    setThinking(false);

    const label = confirmed ? '📅' : '🚫';
    appendMessage('ai', `${label} ${data.response}`, confirmed ? ['calendar'] : []);
    
    speak(data.response);

  } catch (err) {
    removeThinking(thinkingId);
    setThinking(false);
    appendMessage('ai', `❌ Error: ${err.message}`);
  }
}


// ── DOM Helpers & TTS ──────────────────────────────────────────────────────
function speak(text) {
  if (isMuted || !window.speechSynthesis) return;
  // Strip markdown syntax
  const plainText = text.replace(/[*_#`]/g, '');
  const utterance = new SpeechSynthesisUtterance(plainText);
  
  const voices = window.speechSynthesis.getVoices();
  const voice = voices.find(v => v.name.includes('Google US English') || v.lang === 'en-US');
  if (voice) utterance.voice = voice;
  
  window.speechSynthesis.speak(utterance);
}

function appendMessage(role, text, toolTags = []) {
  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${role === 'ai' ? 'ai-avatar' : 'user-avatar'}`;
  avatar.textContent = role === 'ai' ? '✦' : '👤';
  avatar.setAttribute('aria-hidden', 'true');

  const bubbleWrap = document.createElement('div');
  bubbleWrap.className = 'bubble-wrap';

  if (toolTags.length > 0) {
    const tagsEl = document.createElement('div');
    tagsEl.className = 'tool-tags';
    tagsEl.setAttribute('aria-label', 'Tools used');
    toolTags.forEach(tag => {
      const pill = document.createElement('span');
      pill.className = `tool-tag ${tag}`;
      const icons = { search: '🔍 Web Search', memory: '🧠 Memory', calendar: '📅 Calendar' };
      pill.textContent = icons[tag] || tag;
      tagsEl.appendChild(pill);
    });
    bubbleWrap.appendChild(tagsEl);
  }

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = role === 'ai' ? renderMarkdown(text) : escapeHTML(text);

  bubbleWrap.appendChild(bubble);
  wrap.appendChild(avatar);
  wrap.appendChild(bubbleWrap);
  messagesList.appendChild(wrap);
  scrollToBottom();
}

function appendSystemMessage(text) {
  const el = document.createElement('p');
  el.style.cssText = 'text-align:center;font-size:0.72rem;color:var(--text-muted);padding:4px 0;';
  el.textContent = text;
  messagesList.appendChild(el);
}

let thinkingCounter = 0;

function appendThinking() {
  const id = `thinking-${++thinkingCounter}`;
  const wrap = document.createElement('div');
  wrap.className = 'message ai thinking-msg';
  wrap.id = id;

  const avatar = document.createElement('div');
  avatar.className = 'avatar ai-avatar';
  avatar.textContent = '✦';
  avatar.setAttribute('aria-hidden', 'true');

  const bubbleWrap = document.createElement('div');
  bubbleWrap.className = 'bubble-wrap';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = `<span style="font-size:0.78rem;color:var(--text-muted)">Thinking</span><div class="thinking-dots"><span></span><span></span><span></span></div>`;

  bubbleWrap.appendChild(bubble);
  wrap.appendChild(avatar);
  wrap.appendChild(bubbleWrap);
  messagesList.appendChild(wrap);
  scrollToBottom();
  return id;
}

function removeThinking(id) {
  document.getElementById(id)?.remove();
}

function showBanner(detail) {
  confirmDetail.textContent = detail.length > 80 ? detail.slice(0, 80) + '…' : detail;
  confirmationBanner.hidden = false;
}

function hideBanner() {
  confirmationBanner.hidden = true;
}

function setThinking(state) {
  isThinking = state;
  statusDot.className = 'status-dot' + (state ? ' thinking' : '');
  chatInput.disabled = state;
  sendBtn.disabled = state || chatInput.value.trim() === '';
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesWrapper.scrollTo({ top: messagesWrapper.scrollHeight, behavior: 'smooth' });
  });
}


// ── Utilities ─────────────────────────────────────────────────────────────
function escapeHTML(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/**
 * Lightweight markdown parser for AI response formatting.
 * Supports bold, italics, inline code, blocks, and lists.
 */
function renderMarkdown(text) {
  let html = escapeHTML(text);

  // Code blocks (```...```)
  html = html.replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre style="background:rgba(255,255,255,0.06);padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:0.8rem;margin:4px 0;"><code>$1</code></pre>');
  
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  
  // Links
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  
  // Headings (## and ###)
  html = html.replace(/^### (.+)$/gm, '<strong style="font-size:0.9rem;display:block;margin:6px 0 2px;">$1</strong>');
  html = html.replace(/^## (.+)$/gm,  '<strong style="font-size:0.95rem;display:block;margin:8px 0 2px;">$1</strong>');
  
  // Unordered lists
  html = html.replace(/^[•\-\*] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
  
  // Numbered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  
  // Double newlines → paragraph breaks
  html = html.replace(/\n\n/g, '<br><br>');
  
  // Single newlines
  html = html.replace(/\n/g, '<br>');

  return html;
}

/**
 * Heuristically infers executed tools via response parsing for UI tagging.
 */
function detectTools(response) {
  const tags = [];
  if (/search|found|according|source|url|http|result/i.test(response)) tags.push('search');
  if (/remember|memory|saved|recalled|preference|forget/i.test(response)) tags.push('memory');
  if (/calendar|event|schedule|created|appointment/i.test(response)) tags.push('calendar');
  return tags;
}

// ── Start ─────────────────────────────────────────────────────────────────
init();
