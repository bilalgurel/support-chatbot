/* Chat widget. Add it to any page with one line:
   <script src="https://YOUR-SERVER/widget.js" data-title="Chat with us" data-color="#0f766e"></script> */
(function () {
  var script = document.currentScript;
  var api = new URL(script.src).origin + '/api/chat';
  var title = script.getAttribute('data-title') || 'Chat with us';
  var color = script.getAttribute('data-color') || '#0f766e';
  var greeting = script.getAttribute('data-greeting') || 'Hi! How can I help you today?';

  // One id per visitor so the assistant remembers the conversation.
  var sessionId;
  try { sessionId = localStorage.getItem('sc_session'); } catch (e) {}
  if (!sessionId) {
    sessionId = 'w' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
    try { localStorage.setItem('sc_session', sessionId); } catch (e) {}
  }

  var style = document.createElement('style');
  style.textContent =
    '.sc-btn{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;cursor:pointer;color:#fff;font-size:24px;box-shadow:0 4px 14px rgba(0,0,0,.25);z-index:99998}' +
    '.sc-panel{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 24px);height:520px;max-height:calc(100vh - 110px);background:#fff;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden;z-index:99999;font:14px/1.45 system-ui,sans-serif;color:#1c2330}' +
    '.sc-panel.sc-open{display:flex}' +
    '.sc-head{padding:14px 16px;color:#fff;font-weight:600}' +
    '.sc-msgs{flex:1;overflow-y:auto;padding:14px;background:#f6f7f9}' +
    '.sc-msg{max-width:85%;margin-bottom:10px;padding:9px 12px;border-radius:12px;white-space:pre-wrap;word-wrap:break-word}' +
    '.sc-bot{background:#fff;border:1px solid #e2e5ea}' +
    '.sc-user{margin-left:auto;color:#fff}' +
    '.sc-note{text-align:center;font-size:12px;color:#667085;margin:8px 0}' +
    '.sc-form{display:flex;gap:8px;padding:10px;border-top:1px solid #e2e5ea}' +
    '.sc-form input{flex:1;padding:9px 11px;border:1px solid #e2e5ea;border-radius:8px;font:inherit}' +
    '.sc-form button{border:0;border-radius:8px;padding:0 14px;color:#fff;cursor:pointer;font:inherit}' +
    '.sc-form button:disabled{opacity:.5}';
  document.head.appendChild(style);

  var button = document.createElement('button');
  button.className = 'sc-btn';
  button.style.background = color;
  button.setAttribute('aria-label', title);
  button.textContent = '💬';

  var panel = document.createElement('div');
  panel.className = 'sc-panel';
  var head = document.createElement('div');
  head.className = 'sc-head';
  head.style.background = color;
  head.textContent = title;
  var msgs = document.createElement('div');
  msgs.className = 'sc-msgs';
  var form = document.createElement('form');
  form.className = 'sc-form';
  var input = document.createElement('input');
  input.placeholder = 'Type a message...';
  input.maxLength = 1000;
  input.autocomplete = 'off';
  var send = document.createElement('button');
  send.style.background = color;
  send.textContent = 'Send';
  form.append(input, send);
  panel.append(head, msgs, form);
  document.body.append(button, panel);

  function add(text, cls) {
    var el = document.createElement('div');
    el.className = 'sc-msg ' + cls;
    if (cls === 'sc-user') el.style.background = color;
    el.textContent = text;
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
    return el;
  }
  function note(text) {
    var el = document.createElement('div');
    el.className = 'sc-note';
    el.textContent = text;
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
  }

  var greeted = false;
  var handoffShown = false;
  button.addEventListener('click', function () {
    panel.classList.toggle('sc-open');
    if (!greeted) { add(greeting, 'sc-bot'); greeted = true; }
    input.focus();
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    send.disabled = true;
    add(text, 'sc-user');
    var typing = add('...', 'sc-bot');
    fetch(api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: text })
    })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (result) {
        typing.textContent = result.ok ? result.data.reply : (result.data.detail || 'Something went wrong.');
        if (result.ok && result.data.needs_human && !handoffShown) {
          note('A team member has been notified.');
          handoffShown = true;
        }
      })
      .catch(function () { typing.textContent = 'Could not reach the server. Please try again.'; })
      .finally(function () { send.disabled = false; input.focus(); msgs.scrollTop = msgs.scrollHeight; });
  });
})();
