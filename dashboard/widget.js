(() => {
  'use strict';

  const script = document.currentScript;
  const accountId = script?.dataset.accountId;
  if (!accountId || !script?.src) return;
  const apiBase = new URL(script.src).origin;
  const storageKey = `mdcskh:webchat:${accountId}`;
  const state = {
    token: '', visitorId: '', messages: [], connected: false, sending: false,
  };

  const host = document.createElement('div');
  host.dataset.webchatAccount = accountId;
  document.body.append(host);
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      :host { color-scheme: light; }
      * { box-sizing: border-box; }
      button, textarea { font: inherit; }
      .launcher {
        position: fixed; right: 22px; bottom: 22px; z-index: 2147483000;
        width: 58px; height: 58px; border: 0; border-radius: 19px;
        color: #fff; background: #1746d1; cursor: pointer;
        box-shadow: 0 18px 42px rgba(23,70,209,.28);
        display: grid; place-items: center; transition: transform .18s ease;
      }
      .launcher:hover { transform: translateY(-2px); }
      .launcher:focus-visible, .send:focus-visible, textarea:focus-visible {
        outline: 3px solid #7ce0c3; outline-offset: 3px;
      }
      .launcher svg { width: 25px; }
      .panel {
        position: fixed; right: 22px; bottom: 92px; z-index: 2147483000;
        width: min(388px, calc(100vw - 28px)); height: min(610px, calc(100vh - 120px));
        display: grid; grid-template-rows: auto 1fr auto; overflow: hidden;
        border: 1px solid #dce3f0; border-radius: 24px; background: #f7f9fd;
        box-shadow: 0 28px 80px rgba(12,27,64,.22);
        transform-origin: right bottom; transition: opacity .18s, transform .18s;
      }
      .panel[hidden] { display: none; }
      .head { padding: 18px 19px 16px; color: #fff; background: #10214a; }
      .eyebrow { display: flex; align-items: center; gap: 8px; color: #b9c7eb;
        font: 600 11px/1.2 'Cascadia Mono','Segoe UI',sans-serif; letter-spacing: .09em;
        text-transform: uppercase; }
      .signal { width: 8px; height: 8px; border-radius: 50%; background: #ffb547; }
      .signal.live { background: #62d7b5; box-shadow: 0 0 0 5px rgba(98,215,181,.14); }
      h2 { margin: 9px 0 3px; font: 690 20px/1.2 'Segoe UI Variable','Segoe UI',sans-serif; }
      .sub { margin: 0; color: #cbd5ee; font: 13px/1.4 'Segoe UI',sans-serif; }
      .messages { padding: 18px 15px; overflow: auto; scroll-behavior: smooth; }
      .empty { margin: 28px 18px; color: #5a6782; text-align: center;
        font: 14px/1.55 'Segoe UI',sans-serif; }
      .row { display: flex; margin: 0 0 10px; }
      .row.mine { justify-content: flex-end; }
      .bubble { max-width: 82%; padding: 10px 12px; border-radius: 14px 14px 14px 4px;
        color: #18213a; background: #fff; border: 1px solid #e2e7f1;
        font: 14px/1.5 'Segoe UI Variable','Segoe UI',sans-serif; white-space: pre-wrap;
        box-shadow: 0 3px 12px rgba(24,33,58,.045); }
      .mine .bubble { color: #fff; background: #1746d1; border-color: #1746d1;
        border-radius: 14px 14px 4px 14px; }
      .composer { padding: 12px; border-top: 1px solid #dde4f0; background: #fff; }
      form { display: grid; grid-template-columns: 1fr auto; gap: 9px; align-items: end; }
      textarea { min-height: 44px; max-height: 108px; resize: none; padding: 11px 12px;
        border: 1px solid #ccd5e4; border-radius: 13px; color: #142044; background: #f9fbff; }
      textarea::placeholder { color: #7f8aa2; }
      .send { width: 44px; height: 44px; border: 0; border-radius: 13px; cursor: pointer;
        color: #fff; background: #1746d1; display: grid; place-items: center; }
      .send:disabled { opacity: .45; cursor: wait; }
      .send svg { width: 18px; }
      .error { min-height: 17px; margin: 7px 3px 0; color: #b42318; font: 12px/1.3 'Segoe UI',sans-serif; }
      @media (max-width: 520px) {
        .panel { right: 8px; bottom: 80px; width: calc(100vw - 16px); height: calc(100vh - 94px); border-radius: 20px; }
        .launcher { right: 14px; bottom: 14px; }
      }
      @media (prefers-reduced-motion: reduce) { * { transition: none !important; scroll-behavior: auto !important; } }
    </style>
    <button class="launcher" type="button" aria-label="Mở hỗ trợ trực tuyến" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a8 8 0 0 1-8 8H7l-4 2 1.4-4.2A9 9 0 1 1 21 12Z"/></svg>
    </button>
    <section class="panel" hidden aria-label="Hỗ trợ trực tuyến">
      <header class="head"><div class="eyebrow"><i class="signal"></i><span class="status">Đang kết nối</span></div>
        <h2>Hỗ trợ khách hàng</h2><p class="sub">Tin nhắn của bạn được chuyển tới đúng đội phụ trách.</p></header>
      <main class="messages" aria-live="polite"><p class="empty">Hãy để lại câu hỏi. Bạn có thể tiếp tục ngay cả khi đổi trang.</p></main>
      <footer class="composer"><form><textarea rows="1" maxlength="4000" placeholder="Nhập tin nhắn…" aria-label="Tin nhắn"></textarea>
        <button class="send" type="submit" aria-label="Gửi tin nhắn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg></button></form><div class="error" role="alert"></div></footer>
    </section>`;

  const $ = (selector) => root.querySelector(selector);
  const panel = $('.panel'); const launcher = $('.launcher'); const list = $('.messages');
  const form = $('form'); const input = $('textarea'); const send = $('.send'); const error = $('.error');

  function headers() { return { 'content-type': 'application/json', authorization: `Bearer ${state.token}` }; }
  function setConnected(value) {
    state.connected = value; $('.signal').classList.toggle('live', value);
    $('.status').textContent = value ? 'Đang trực tuyến' : 'Đang kết nối';
  }
  function render(items) {
    const signature = items.map((item) => item.id).join('|');
    if (list.dataset.signature === signature) return;
    list.dataset.signature = signature; list.replaceChildren();
    if (!items.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'Hãy để lại câu hỏi. Bạn có thể tiếp tục ngay cả khi đổi trang.'; list.append(p); return; }
    for (const item of items) {
      const row = document.createElement('div'); row.className = `row ${item.role === 'customer' ? 'mine' : ''}`;
      const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = item.content;
      row.append(bubble); list.append(row);
    }
    list.scrollTop = list.scrollHeight;
  }
  async function session() {
    let stored = {}; try { stored = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch {}
    const response = await fetch(`${apiBase}/webchat/${accountId}/session`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ visitor_id: stored.visitorId || null }),
    });
    if (!response.ok) throw new Error('Kênh hỗ trợ chưa sẵn sàng trên website này.');
    const data = await response.json(); state.token = data.token; state.visitorId = data.visitor_id;
    localStorage.setItem(storageKey, JSON.stringify({ visitorId: state.visitorId }));
  }
  async function history() {
    const response = await fetch(`${apiBase}/webchat/${accountId}/history`, { headers: headers() });
    if (!response.ok) throw new Error('Không tải được lịch sử trò chuyện.');
    const data = await response.json(); state.messages = data.items; render(state.messages);
  }
  async function stream() {
    while (state.token) {
      try {
        const response = await fetch(`${apiBase}/webchat/${accountId}/events`, { headers: { authorization: `Bearer ${state.token}` } });
        if (!response.ok || !response.body) throw new Error();
        setConnected(true); const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true });
          if (buffer.includes('\n\n')) { buffer = buffer.slice(buffer.lastIndexOf('\n\n') + 2); await history(); } }
      } catch { setConnected(false); await new Promise((resolve) => setTimeout(resolve, 1800)); }
    }
  }
  async function boot() {
    try { await session(); await history(); setConnected(true); stream(); }
    catch (cause) { error.textContent = cause.message || 'Không kết nối được kênh hỗ trợ.'; }
  }
  launcher.addEventListener('click', () => {
    const opening = panel.hidden; panel.hidden = !opening; launcher.setAttribute('aria-expanded', String(opening));
    if (opening) input.focus();
  });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 108)}px`; });
  input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); const text = input.value.trim(); if (!text || state.sending) return;
    state.sending = true; send.disabled = true; error.textContent = '';
    try {
      const response = await fetch(`${apiBase}/webchat/${accountId}/messages`, {
        method: 'POST', headers: headers(), body: JSON.stringify({ client_message_id: crypto.randomUUID(), text }),
      });
      if (!response.ok) throw new Error('Tin chưa gửi được. Kiểm tra kết nối rồi thử lại.');
      input.value = ''; input.style.height = 'auto'; await history();
    } catch (cause) { error.textContent = cause.message; }
    finally { state.sending = false; send.disabled = false; input.focus(); }
  });
  boot();
})();
