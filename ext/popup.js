const $ = (s) => document.querySelector(s);
const send = (m) => browser.runtime.sendMessage(m);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const status = (msg, err = false) => { $('#status').textContent = msg; $('#status').className = err ? 'err' : ''; };

let tab;
browser.tabs.query({ active: true, currentWindow: true }).then(([t]) => {
  tab = t;
  if (t.url.startsWith('moz-extension:')) { document.body.classList.add('tab'); $('#digest').hidden = true; return; }
  $('#tab').textContent = `${t.title} — ${t.url}`;
});

$('#open-tab').onclick = (e) => { e.preventDefault(); browser.tabs.create({ url: browser.runtime.getURL('popup.html') }); };

$('#go').onclick = async () => {
  status('extracting page and starting tmux session…');
  $('#go').disabled = true;
  try {
    const r = await send({ action: 'digest', tabId: tab.id, user_prompt: $('#prompt').value.trim() });
    status(`digest #${r.id} saved; claude is running in tmux session ${r.tmux_session}`);
    search();
  } catch (e) { status(String(e), true); }
  $('#go').disabled = false;
};

async function search() {
  const q = $('#q').value.trim();
  let rows;
  try { rows = await send({ action: 'search', q }); } catch (e) { status(String(e), true); return; }
  $('#results').innerHTML = rows.length ? '' : '<div class="m">no digests yet</div>';
  for (const r of rows) {
    const el = document.createElement('div');
    el.className = 'row';
    el.innerHTML = `<span class="t">${esc(r.title) || '(untitled)'}</span>
      <a class="u" href="${esc(r.url)}" target="_blank">${esc(r.url)}</a>
      <div class="m">#${r.id} · ${esc(r.created_at.slice(0, 16).replace('T', ' '))} · ${esc(r.agent)} · ${r.has_answer ? 'answered' : 'no answer yet'}
        · <button class="sm show">show</button> <button class="sm cont">continue in tmux</button></div>
      ${r.user_prompt ? `<div class="s">prompt: ${esc(r.user_prompt)}</div>` : ''}
      ${r.snippet ? `<div class="s">${esc(r.snippet)}</div>` : ''}
      <div class="a" hidden></div>`;
    el.querySelector('.show').onclick = async (e) => {
      const a = el.querySelector('.a');
      if (!a.hidden) { a.hidden = true; e.target.textContent = 'show'; return; }
      const full = await send({ action: 'get', id: r.id });
      a.textContent = (full.answer || '(no answer captured yet — the claude session may still be running)') + '\n\n--- digest sent to claude ---\n' + full.digest_md;
      a.hidden = false;
      e.target.textContent = 'hide';
    };
    el.querySelector('.cont').onclick = async () => {
      try { const c = await send({ action: 'continue', id: r.id }); status(`${c.how} tmux session ${c.tmux_session}`); }
      catch (e) { status(String(e), true); }
    };
    $('#results').append(el);
  }
}
let timer;
$('#q').oninput = () => { clearTimeout(timer); timer = setTimeout(search, 200); };
search();

send({ action: 'config' }).then((c) => {
  $('#cfg').textContent = `agent: ${c.agent} · transcript: ${c.transcript} · terminal: ${c.terminal}\nstart: ${c.start_command}\nconfig: ${c.config_path}${c.config_exists ? '' : ' (missing, using defaults)'}`;
}, (e) => { $('#cfg').textContent = String(e); });
