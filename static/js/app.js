/**
 * app.js — claude-local-proxy chat UI
 *
 * Features:
 *  - Conversation management (create, list, switch, delete, rename)
 *  - Streaming responses via Server-Sent Events
 *  - Markdown rendering (bold, italic, code blocks, tables, lists)
 *  - Auto-expanding textarea
 *  - Dark / light mode toggle
 *  - Export conversation as JSON or Markdown
 *  - Mobile sidebar toggle
 *  - Toast notifications
 *  - Settings panel (system prompt, max tokens, streaming toggle)
 */

'use strict';

// ── State ───────────────────────────────────────────────────────
const state = {
  convId      : null,
  streaming   : true,
  maxTokens   : 1024,
  systemPrompt: '',
  isLoading   : false,
};

// ── DOM refs ────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
  sidebar       : $('sidebar'),
  overlay       : $('overlay'),
  menuBtn       : $('menuBtn'),
  convList      : $('convList'),
  newConvBtn    : $('newConvBtn'),
  convTitle     : $('convTitle'),
  messages      : $('messages'),
  welcome       : $('welcome'),
  userInput     : $('userInput'),
  sendBtn       : $('sendBtn'),
  clearBtn      : $('clearBtn'),
  tokenCount    : $('tokenCount'),
  modelSelect   : $('modelSelect'),
  themeToggle   : $('themeToggle'),
  exportBtn     : $('exportBtn'),
  settingsBtn   : $('settingsBtn'),
  settingsPanel : $('settingsPanel'),
  panelOverlay  : $('panelOverlay'),
  closePanelBtn : $('closePanelBtn'),
  savePanelBtn  : $('savePanelBtn'),
  systemPrompt  : $('systemPrompt'),
  maxTokensInput: $('maxTokens'),
  streamToggle  : $('streamToggle'),
};

// ── Markdown renderer (no external deps) ────────────────────────

function renderMarkdown(text) {
  // Escape HTML first (outside code blocks)
  function escapeHtml(s) {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Extract code blocks first to protect them
  const codeBlocks = [];
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang: lang || '', code });
    return `\x00CODE${idx}\x00`;
  });

  // Inline code
  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    const idx = inlineCodes.length;
    inlineCodes.push(escapeHtml(code));
    return `\x00INLINE${idx}\x00`;
  });

  // Escape remaining HTML
  text = escapeHtml(text);

  // Block elements
  // Tables
  text = text.replace(
    /((?:\|.+\|\n?)+)/g,
    (match) => {
      const rows = match.trim().split('\n');
      let html = '<table>';
      rows.forEach((row, i) => {
        if (/^[\|\s\-:]+$/.test(row)) return; // separator row
        const cells = row.split('|').slice(1, -1);
        const tag = (i === 0) ? 'th' : 'td';
        html += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
      });
      return html + '</table>';
    }
  );

  // Blockquotes
  text = text.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // Headings
  text = text.replace(/^#{3} (.+)$/gm, '<h3>$1</h3>');
  text = text.replace(/^#{2} (.+)$/gm, '<h2>$1</h2>');
  text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Horizontal rule
  text = text.replace(/^---+$/gm, '<hr/>');

  // Unordered lists (supports - * •)
  text = text.replace(/((?:^[-*•] .+\n?)+)/gm, (match) => {
    const items = match.trim().split('\n')
      .map(l => `<li>${l.replace(/^[-*•] /, '')}</li>`)
      .join('');
    return `<ul>${items}</ul>`;
  });

  // Ordered lists
  text = text.replace(/((?:^\d+\. .+\n?)+)/gm, (match) => {
    const items = match.trim().split('\n')
      .map(l => `<li>${l.replace(/^\d+\. /, '')}</li>`)
      .join('');
    return `<ol>${items}</ol>`;
  });

  // Inline formatting
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/_(.+?)_/g, '<em>$1</em>');
  text = text.replace(/~~(.+?)~~/g, '<del>$1</del>');
  text = text.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Paragraphs: double newline = paragraph break
  text = text
    .split(/\n{2,}/)
    .map(p => {
      p = p.trim();
      if (!p) return '';
      if (/^<(h[1-3]|ul|ol|blockquote|table|hr|pre)/.test(p)) return p;
      return `<p>${p.replace(/\n/g, '<br/>')}</p>`;
    })
    .join('\n');

  // Restore inline codes
  text = text.replace(/\x00INLINE(\d+)\x00/g, (_, idx) => {
    return `<code>${inlineCodes[parseInt(idx)]}</code>`;
  });

  // Restore code blocks
  text = text.replace(/\x00CODE(\d+)\x00/g, (_, idx) => {
    const { lang, code } = codeBlocks[parseInt(idx)];
    const escaped = escapeHtml(code);
    const copyId  = `cb-${Math.random().toString(36).slice(2, 8)}`;
    return `<pre id="${copyId}"><span class="code-lang">${lang}</span>` +
      `<button class="copy-code-btn" onclick="copyCode('${copyId}')">نسخ</button>` +
      `<code>${escaped}</code></pre>`;
  });

  return text;
}

window.copyCode = function(preId) {
  const pre  = document.getElementById(preId);
  const code = pre ? pre.querySelector('code')?.textContent || '' : '';
  navigator.clipboard.writeText(code).then(() => showToast('تم نسخ الكود ✓'));
};

// ── Toast ────────────────────────────────────────────────────────

function showToast(msg, duration = 2000) {
  let t = document.querySelector('.toast');
  if (!t) {
    t = document.createElement('div');
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), duration);
}

// ── API helpers ──────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

// ── Conversation management ──────────────────────────────────────

async function loadConversations() {
  try {
    const data = await apiFetch('/v1/conversations');
    renderConvList(data.conversations || []);
  } catch (e) {
    console.error('loadConversations:', e);
  }
}

function renderConvList(convs) {
  els.convList.innerHTML = '';
  if (!convs.length) {
    els.convList.innerHTML = '<div style="padding:12px;font-size:13px;color:var(--text3);text-align:center">لا توجد محادثات بعد</div>';
    return;
  }
  convs.forEach(conv => {
    const item = document.createElement('div');
    item.className = 'conv-item' + (conv.id === state.convId ? ' active' : '');
    item.dataset.id = conv.id;

    const title = document.createElement('span');
    title.className = 'conv-item-title';
    title.textContent = conv.title || 'محادثة';

    const del = document.createElement('button');
    del.className = 'conv-item-del';
    del.textContent = '✕';
    del.title = 'حذف المحادثة';
    del.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('هل تريد حذف هذه المحادثة؟')) return;
      try {
        await apiFetch(`/v1/conversations/${conv.id}`, { method: 'DELETE' });
        if (state.convId === conv.id) {
          state.convId = null;
          els.convTitle.textContent = 'محادثة جديدة';
          clearMessages();
          showWelcome();
        }
        loadConversations();
      } catch (e) { showToast('خطأ في الحذف'); }
    });

    item.appendChild(title);
    item.appendChild(del);
    item.addEventListener('click', () => openConversation(conv.id, conv.title));
    els.convList.appendChild(item);
  });
}

async function createConversation() {
  const model  = els.modelSelect.value;
  const system = state.systemPrompt;
  try {
    const conv = await apiFetch('/v1/conversations', {
      method: 'POST',
      body  : JSON.stringify({ title: 'محادثة جديدة', model, system_prompt: system }),
    });
    state.convId = conv.id;
    els.convTitle.textContent = conv.title;
    clearMessages();
    hideWelcome();
    await loadConversations();
    return conv;
  } catch (e) {
    showToast('خطأ في إنشاء المحادثة');
    return null;
  }
}

async function openConversation(id, title) {
  state.convId = id;
  els.convTitle.textContent = title || 'محادثة';
  clearMessages();
  closeSidebar();

  // Mark active
  document.querySelectorAll('.conv-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });

  try {
    const data = await apiFetch(`/v1/conversations/${id}/messages`);
    const msgs = data.messages || [];
    if (msgs.length === 0) {
      showWelcome();
    } else {
      hideWelcome();
      msgs.forEach(m => {
        if (m.role === 'user' || m.role === 'assistant') {
          appendMessage(m.role, m.content, false);
        }
      });
      scrollToBottom();
    }
  } catch (e) {
    showToast('خطأ في تحميل المحادثة');
  }
}

// Auto-name conversation based on first user message
async function autoNameConversation(text) {
  if (!state.convId) return;
  const title = text.slice(0, 48) + (text.length > 48 ? '…' : '');
  try {
    await apiFetch(`/v1/conversations/${state.convId}`, {
      method: 'PUT',
      body  : JSON.stringify({ title }),
    });
    els.convTitle.textContent = title;
    loadConversations();
  } catch (_) {}
}

// ── Message rendering ────────────────────────────────────────────

function clearMessages() {
  // Keep only the welcome div placeholder
  while (els.messages.firstChild) {
    els.messages.removeChild(els.messages.firstChild);
  }
  // Re-add welcome (hidden)
  if (!$('welcome')) {
    const w = document.createElement('div');
    w.id        = 'welcome';
    w.className = 'welcome';
    w.style.display = 'none';
    els.messages.appendChild(w);
  }
}

function showWelcome() {
  const w = $('welcome');
  if (w) {
    w.style.display = '';
    w.innerHTML = `
      <div class="welcome-icon">🤖</div>
      <h2>ابدأ محادثة جديدة</h2>
      <p>اكتب رسالتك في الأسفل وسيرد Claude فوراً.</p>
      <div class="welcome-tips">
        <div class="tip">💡 يدعم Markdown والكود البرمجي</div>
        <div class="tip">⚡ بث الردود في الوقت الحقيقي</div>
        <div class="tip">💾 المحادثات محفوظة محلياً</div>
      </div>`;
  }
}

function hideWelcome() {
  const w = $('welcome');
  if (w) w.style.display = 'none';
}

function appendMessage(role, content, animate = true) {
  hideWelcome();

  const wrap = document.createElement('div');
  wrap.className = `msg msg-${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🤖';

  const body = document.createElement('div');
  body.className = 'msg-body';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  if (role === 'assistant') {
    bubble.innerHTML = renderMarkdown(content);
  } else {
    bubble.textContent = content;
  }

  const meta = document.createElement('div');
  meta.className = 'msg-meta';

  const timeSpan = document.createElement('span');
  timeSpan.textContent = new Date().toLocaleTimeString('ar', { hour: '2-digit', minute: '2-digit' });

  const copyBtn = document.createElement('button');
  copyBtn.className = 'msg-copy';
  copyBtn.textContent = 'نسخ';
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(content).then(() => showToast('تم النسخ ✓'));
  });

  meta.appendChild(timeSpan);
  meta.appendChild(copyBtn);
  body.appendChild(bubble);
  body.appendChild(meta);
  wrap.appendChild(avatar);
  wrap.appendChild(body);
  els.messages.appendChild(wrap);

  if (!animate) wrap.style.animation = 'none';

  return { wrap, bubble, copyBtn, meta };
}

function appendTypingIndicator() {
  const wrap = document.createElement('div');
  wrap.className = 'msg msg-assistant';
  wrap.id = 'typing-indicator';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '🤖';

  const body = document.createElement('div');
  body.className = 'msg-body';

  const ind = document.createElement('div');
  ind.className = 'typing-indicator';
  ind.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

  body.appendChild(ind);
  wrap.appendChild(avatar);
  wrap.appendChild(body);
  els.messages.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function removeTypingIndicator() {
  const el = $('typing-indicator');
  if (el) el.remove();
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

// ── Send message ─────────────────────────────────────────────────

async function sendMessage() {
  const text = els.userInput.value.trim();
  if (!text || state.isLoading) return;

  // Create conversation if none active
  if (!state.convId) {
    const conv = await createConversation();
    if (!conv) return;
    // Auto-name on first message
    await autoNameConversation(text);
  }

  state.isLoading = true;
  els.sendBtn.disabled = true;
  els.userInput.value  = '';
  resizeTextarea();
  updateTokenCount('');

  appendMessage('user', text);
  scrollToBottom();

  const useStream = state.streaming;
  const model     = els.modelSelect.value;
  const maxTok    = state.maxTokens;

  if (useStream) {
    await sendStreaming(text, model, maxTok);
  } else {
    await sendBlocking(text, model, maxTok);
  }

  state.isLoading = false;
  els.sendBtn.disabled = false;
  els.userInput.focus();
}

async function sendStreaming(text, model, maxTokens) {
  const indicator = appendTypingIndicator();

  try {
    const res = await fetch(`/v1/conversations/${state.convId}/messages`, {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({
        content   : text,
        model,
        max_tokens: maxTokens,
        stream    : true,
      }),
    });

    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const d = await res.json(); msg = d.detail || msg; } catch (_) {}
      throw new Error(msg);
    }

    removeTypingIndicator();
    const { bubble, copyBtn } = appendMessage('assistant', '', true);
    let fullText = '';

    // Add streaming cursor
    const cursor = document.createElement('span');
    cursor.className = 'cursor';
    bubble.appendChild(cursor);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (!data) continue;

        if (data.startsWith('[DONE]')) {
          // Final metadata — update copy button with full content
          break;
        }

        try {
          const evt = JSON.parse(data);
          if (evt.error) throw new Error(evt.error);
          if (evt.text) {
            fullText += evt.text;
            // Re-render markdown incrementally
            bubble.innerHTML = renderMarkdown(fullText);
            bubble.appendChild(cursor);
            scrollToBottom();
          }
        } catch (e) {
          if (e.message !== 'Unexpected end of JSON input') {
            console.warn('SSE parse:', e.message);
          }
        }
      }
    }

    // Remove cursor, final render
    cursor.remove();
    bubble.innerHTML = renderMarkdown(fullText);

    // Update copy button
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(fullText).then(() => showToast('تم النسخ ✓'));
    });

    scrollToBottom();

  } catch (e) {
    removeTypingIndicator();
    const errDiv = document.createElement('div');
    errDiv.className = 'error-msg';
    errDiv.textContent = `خطأ: ${e.message}`;
    els.messages.appendChild(errDiv);
    scrollToBottom();
  }
}

async function sendBlocking(text, model, maxTokens) {
  const indicator = appendTypingIndicator();
  try {
    const data = await apiFetch(`/v1/conversations/${state.convId}/messages`, {
      method: 'POST',
      body  : JSON.stringify({
        content   : text,
        model,
        max_tokens: maxTokens,
        stream    : false,
      }),
    });
    removeTypingIndicator();
    appendMessage('assistant', data.content || '');
    scrollToBottom();
  } catch (e) {
    removeTypingIndicator();
    const errDiv = document.createElement('div');
    errDiv.className = 'error-msg';
    errDiv.textContent = `خطأ: ${e.message}`;
    els.messages.appendChild(errDiv);
    scrollToBottom();
  }
}

// ── Textarea auto-resize ─────────────────────────────────────────

function resizeTextarea() {
  const ta = els.userInput;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
}

function updateTokenCount(text) {
  // Rough estimate: 1 token ≈ 4 chars
  const count = Math.ceil(text.length / 4);
  els.tokenCount.textContent = count > 0 ? `~${count} رمز` : '0 رمز';
}

// ── Export ───────────────────────────────────────────────────────

async function exportConversation() {
  if (!state.convId) { showToast('لا توجد محادثة مفتوحة'); return; }
  try {
    const data = await apiFetch(`/v1/conversations/${state.convId}/export`);
    const msgs  = data.messages || [];

    // Build Markdown
    let md = `# ${data.conversation?.title || 'محادثة'}\n\n`;
    md += `**التاريخ:** ${data.conversation?.created_at || ''}\n\n---\n\n`;
    msgs.forEach(m => {
      const who = m.role === 'user' ? '**المستخدم**' : '**Claude**';
      md += `${who}\n\n${m.content}\n\n---\n\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `claude-${state.convId.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('تم التصدير ✓');
  } catch (e) {
    showToast('خطأ في التصدير');
  }
}

// ── Sidebar ──────────────────────────────────────────────────────

function openSidebar() {
  els.sidebar.classList.add('open');
  els.overlay.classList.add('active');
}
function closeSidebar() {
  els.sidebar.classList.remove('open');
  els.overlay.classList.remove('active');
}

// ── Settings panel ───────────────────────────────────────────────

function openPanel() {
  els.settingsPanel.classList.add('open');
  els.panelOverlay.classList.add('active');
}
function closePanel() {
  els.settingsPanel.classList.remove('open');
  els.panelOverlay.classList.remove('active');
}

// ── Theme ────────────────────────────────────────────────────────

function toggleTheme() {
  const body = document.body;
  if (body.classList.contains('dark')) {
    body.classList.replace('dark', 'light');
    els.themeToggle.textContent = '☀️ المظهر';
    localStorage.setItem('claude-theme', 'light');
  } else {
    body.classList.replace('light', 'dark');
    els.themeToggle.textContent = '🌙 المظهر';
    localStorage.setItem('claude-theme', 'dark');
  }
}

function loadTheme() {
  const saved = localStorage.getItem('claude-theme') || 'dark';
  document.body.className = saved;
  els.themeToggle.textContent = saved === 'dark' ? '🌙 المظهر' : '☀️ المظهر';
}

// ── Settings persistence ─────────────────────────────────────────

function loadSettings() {
  const s = JSON.parse(localStorage.getItem('claude-settings') || '{}');
  state.streaming   = s.streaming   !== false;
  state.maxTokens   = s.maxTokens   || 1024;
  state.systemPrompt= s.systemPrompt|| '';

  els.streamToggle.checked = state.streaming;
  els.maxTokensInput.value = state.maxTokens;
  els.systemPrompt.value   = state.systemPrompt;
}

function saveSettings() {
  state.streaming    = els.streamToggle.checked;
  state.maxTokens    = parseInt(els.maxTokensInput.value) || 1024;
  state.systemPrompt = els.systemPrompt.value.trim();
  localStorage.setItem('claude-settings', JSON.stringify({
    streaming   : state.streaming,
    maxTokens   : state.maxTokens,
    systemPrompt: state.systemPrompt,
  }));
  closePanel();
  showToast('تم الحفظ ✓');
}

// ── Event listeners ──────────────────────────────────────────────

els.sendBtn.addEventListener('click', sendMessage);

els.userInput.addEventListener('input', () => {
  resizeTextarea();
  updateTokenCount(els.userInput.value);
  els.sendBtn.disabled = !els.userInput.value.trim();
});

els.userInput.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    sendMessage();
  }
  // Shift+Enter = newline (default behaviour, no override needed)
});

els.clearBtn.addEventListener('click', () => {
  els.userInput.value = '';
  resizeTextarea();
  updateTokenCount('');
  els.sendBtn.disabled = true;
  els.userInput.focus();
});

els.newConvBtn.addEventListener('click', async () => {
  state.convId = null;
  els.convTitle.textContent = 'محادثة جديدة';
  clearMessages();
  showWelcome();
  closeSidebar();
  // deactivate all items
  document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
  els.userInput.focus();
});

els.menuBtn.addEventListener('click', openSidebar);
els.overlay.addEventListener('click', closeSidebar);

els.themeToggle.addEventListener('click', toggleTheme);
els.exportBtn.addEventListener('click', exportConversation);

els.settingsBtn.addEventListener('click', openPanel);
els.closePanelBtn.addEventListener('click', closePanel);
els.panelOverlay.addEventListener('click', closePanel);
els.savePanelBtn.addEventListener('click', saveSettings);

// ── Init ─────────────────────────────────────────────────────────

async function init() {
  loadTheme();
  loadSettings();
  await loadConversations();
  showWelcome();
  els.userInput.focus();
}

init();
