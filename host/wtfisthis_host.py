"""WTFISTHIS native messaging host. stdlib only.

Actions (JSON over stdin/stdout, 4-byte little-endian length prefix):
  digest   {page, user_prompt}  -> store the page digest, start the agent in a new tmux session, open a terminal on it
  search   {q}                  -> rows matching q (LIKE over title/url/prompt/digest/answer), newest first
  get      {id}                 -> one full row
  continue {id}                 -> reattach the terminal to the tmux session, or resume the agent session in a new one
  config   {}                   -> the effective configuration

Config file: $WTFISTHIS_CONFIG or $XDG_CONFIG_HOME/wtfisthis/config.json (see config.example.json / README).
"""
import glob, json, os, shlex, sqlite3, struct, subprocess, sys, time, uuid
from datetime import datetime, timezone

HOME = os.path.expanduser('~')
CONFIG_PATH = os.environ.get('WTFISTHIS_CONFIG') or os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config')), 'wtfisthis/config.json')
ARG_LIMIT = 120_000  # Linux MAX_ARG_STRLEN is 128 KiB; "$(cat prompt_file)" becomes one argv entry
QUIET = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # children must never touch the messaging pipe

# Placeholders: {prompt_file} {digest_file} {session_id} (the uuid we generate) {agent_session_id} (what the agent calls it)
PRESETS = {
    'claude':   dict(start='claude --session-id {session_id} "$(cat {prompt_file})"', resume='claude --resume {agent_session_id}', transcript='claude'),
    'codex':    dict(start='codex "$(cat {prompt_file})"', resume='codex resume {agent_session_id}', transcript='codex'),
    'opencode': dict(start='opencode --session {session_id} --prompt "$(cat {prompt_file})"', resume='opencode --session {agent_session_id}', transcript='pane'),
    'hermes':   dict(start='hermes chat -q "$(cat {prompt_file})"', resume=None, transcript='pane'),
    'custom':   dict(start=None, resume=None, transcript='pane'),
}
DEFAULTS = dict(agent='claude', start_command=None, resume_command=None, transcript=None,
                terminal=f"{os.environ.get('TERMINAL', 'xterm')} -e", env={}, tmux_prefix='wtfisthis',
                data_dir='~/.local/share/wtfisthis', preamble=None)
PREAMBLE = ('You are WTFISTHIS. The user is looking at something in Firefox and asks: WTF is this?\n'
            'Below is an automated digest of the page (metadata and extracted text). Describe in full detail what this is: '
            'what kind of thing it is (web page, paper, GitHub project, news article, email, product, ...), who made it, '
            'what it says or does, the key points, relevant context, credibility signals, and anything notable. '
            'For a paper: summarize question, methods, findings, limitations. For code: purpose, architecture, how to use. '
            'For an email: summarize and list action items. For an article: summary and context.\n'
            'The complete digest is saved at {digest_file} (the page text below may be truncated). '
            'Fetch the URL yourself if you need more. The user may ask follow-up questions after your answer.\n'
            'WTFISTHIS session token: {session_id}\n')


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    if cfg['agent'] not in PRESETS:
        raise ValueError(f"config agent={cfg['agent']!r}; known presets: {', '.join(PRESETS)}")
    p = PRESETS[cfg['agent']]
    cfg['start_command'] = cfg['start_command'] or p['start']
    cfg['resume_command'] = cfg['resume_command'] or p['resume']
    cfg['transcript'] = cfg['transcript'] or p['transcript']
    cfg['data_dir'] = os.path.expanduser(cfg['data_dir'])
    cfg['work_dir'] = os.path.join(cfg['data_dir'], 'work')  # the agent's cwd; digest files live here so it can read them
    if not cfg['start_command']:
        raise ValueError(f"agent {cfg['agent']!r} needs start_command in {CONFIG_PATH}")
    return cfg


def db(cfg):
    os.makedirs(cfg['work_dir'], exist_ok=True)
    c = sqlite3.connect(os.path.join(cfg['data_dir'], 'wtfisthis.db'))
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS digests(
        id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, url TEXT NOT NULL, title TEXT, user_prompt TEXT,
        page_json TEXT NOT NULL, digest_md TEXT NOT NULL, agent TEXT NOT NULL, session_id TEXT NOT NULL,
        agent_session_id TEXT, tmux_session TEXT NOT NULL, transcript_path TEXT, answer TEXT, transcript_mtime REAL)''')
    return c


def render_digest(page):
    L = ['# WTFISTHIS page digest', '']
    for k in ('url', 'canonical', 'title', 'lang', 'charset', 'content_type', 'referrer', 'last_modified', 'captured_at',
              'text_root', 'text_chars', 'word_count', 'link_count', 'image_count', 'extract_error'):
        if page.get(k) not in (None, '', []):
            L.append(f'- {k}: {page[k]}')
    if page.get('meta'):
        L += ['', '## Meta tags']
        for k, vs in page['meta'].items():
            for v in vs:
                L.append(f'- {k}: {v}')
    if page.get('jsonld'):
        L += ['', '## JSON-LD'] + [f'```json\n{j}\n```' for j in page['jsonld']]
    if page.get('feeds'):
        L += ['', '## Feeds'] + [f'- {f}' for f in page['feeds']]
    if page.get('headings'):
        L += ['', '## Headings outline'] + page['headings']
    if page.get('selection'):
        L += ['', '## Text the user selected', page['selection']]
    if page.get('text'):
        L += ['', f"## Page text ({page['text_root']}, {page['text_chars']} chars)", page['text']]
    if page.get('links'):
        L += ['', f"## Links (first {len(page['links'])} of {page['link_count']})"] + [f'- [{t}]({h})' for t, h in page['links']]
    return '\n'.join(L)


def build_prompt(cfg, digest_md, digest_file, session_id, user_prompt):
    head = (cfg['preamble'] or PREAMBLE).format(digest_file=digest_file, session_id=session_id)
    if user_prompt:
        head += f'\nThe user also asks: {user_prompt}\n'
    cap = len(digest_md)
    while True:
        prompt = head + '\n--- DIGEST ---\n' + digest_md[:cap] + ('\n[truncated; full digest in file]' if cap < len(digest_md) else '')
        if len(prompt.encode()) <= ARG_LIMIT:
            return prompt
        cap = int(cap * 0.8)


def render(cmd, **vals):
    return cmd.format_map({k: shlex.quote(str(v)) for k, v in vals.items()})


def tmux(*args, **kw):
    return subprocess.run(['tmux', *args], **QUIET, **kw)


def open_terminal(cfg, name):
    subprocess.Popen(shlex.split(cfg['terminal']) + ['tmux', 'attach-session', '-t', name], start_new_session=True, **QUIET)


def start_session(cfg, name, cmd):
    exports = ' '.join([f'PATH={shlex.quote(os.environ["PATH"])}'] + [f'{k}={v}' for k, v in cfg['env'].items()])
    tmux('new-session', '-d', '-s', name, '-c', cfg['work_dir'], f'export {exports}; {cmd}', check=True)
    open_terminal(cfg, name)


def digest(cfg, c, msg):
    page, user_prompt = msg['page'], msg.get('user_prompt', '')
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    sid = str(uuid.uuid4())
    # If the start command tells the agent its id, we already know what to resume; otherwise the transcript reveals it.
    agent_sid = sid if '{session_id}' in cfg['start_command'] else None
    md = render_digest(page)
    cur = c.execute('''INSERT INTO digests(created_at,url,title,user_prompt,page_json,digest_md,agent,session_id,agent_session_id,tmux_session)
                       VALUES(?,?,?,?,?,?,?,?,?,'')''',
                    (now, page.get('url', ''), page.get('title', ''), user_prompt, json.dumps(page), md, cfg['agent'], sid, agent_sid))
    rid = cur.lastrowid
    name = f"{cfg['tmux_prefix']}-{rid}"
    c.execute('UPDATE digests SET tmux_session=? WHERE id=?', (name, rid))
    c.commit()
    digest_file = os.path.join(cfg['work_dir'], f'{rid}.md')
    prompt_file = os.path.join(cfg['work_dir'], f'{rid}.prompt.md')
    with open(digest_file, 'w') as f:
        f.write(md)
    with open(prompt_file, 'w') as f:
        f.write(build_prompt(cfg, md, digest_file, sid, user_prompt))
    start_session(cfg, name, render(cfg['start_command'], prompt_file=prompt_file, digest_file=digest_file, session_id=sid, agent_session_id=agent_sid or ''))
    return {'id': rid, 'tmux_session': name, 'session_id': sid, 'agent': cfg['agent']}


# --- answer capture -------------------------------------------------------------------------------------------------

def jsonl(path):
    for line in open(path):
        try:
            yield json.loads(line)
        except ValueError:
            continue


def text_of(content):
    if isinstance(content, list):
        content = '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') in ('text', 'input_text', 'output_text'))
    return (content or '').strip()


def messages_claude(path):
    for o in jsonl(path):
        if o.get('type') in ('user', 'assistant') and not o.get('isSidechain'):
            yield o['type'], text_of(o.get('message', {}).get('content'))


def messages_codex(path):
    for o in jsonl(path):
        p = o.get('payload', {})
        if o.get('type') == 'response_item' and p.get('type') == 'message' and p.get('role') in ('user', 'assistant'):
            yield p['role'], text_of(p.get('content'))


def conversation(messages, token):
    """Everything after the user message that carried our prompt, as '### Claude' / '### You' blocks."""
    out, seen_prompt = [], False
    for role, text in messages:
        if not text:
            continue  # tool calls, tool results, empty turns
        if not seen_prompt:
            seen_prompt = role == 'user' and token in text
            continue
        out.append(('### Agent\n' if role == 'assistant' else '### You\n') + text)
    return '\n\n'.join(out)


TRANSCRIPTS = {
    'claude': (os.path.join(HOME, '.claude/projects/*/{session_id}.jsonl'), messages_claude),
    'codex': (os.path.join(HOME, '.codex/sessions/*/*/*/rollout-*.jsonl'), messages_codex),
}


def find_transcript(r, pattern):
    if r['transcript_path'] and os.path.exists(r['transcript_path']):
        return r['transcript_path']
    since = datetime.fromisoformat(r['created_at']).timestamp() - 120
    for path in glob.glob(pattern.format(session_id=r['session_id'])):
        if os.path.getmtime(path) >= since and r['session_id'] in open(path, errors='replace').read():
            return path
    return None


def sync_answers(cfg, c):
    kind = cfg['transcript']
    for r in c.execute('SELECT * FROM digests').fetchall():
        if kind == 'pane':
            if tmux('has-session', '-t', r['tmux_session']).returncode == 0:
                cap = subprocess.run(['tmux', 'capture-pane', '-p', '-S', '-', '-t', r['tmux_session']], capture_output=True, text=True, stdin=subprocess.DEVNULL)
                c.execute('UPDATE digests SET answer=?, transcript_mtime=? WHERE id=?', (cap.stdout.strip(), time.time(), r['id']))
        elif kind in TRANSCRIPTS:
            pattern, messages = TRANSCRIPTS[kind]
            path = find_transcript(r, pattern)
            if path and os.path.getmtime(path) != r['transcript_mtime']:
                agent_sid = r['agent_session_id']
                if kind == 'codex' and not agent_sid:
                    agent_sid = next((o['payload']['id'] for o in jsonl(path) if o.get('type') == 'session_meta'), None)
                c.execute('UPDATE digests SET answer=?, transcript_path=?, transcript_mtime=?, agent_session_id=? WHERE id=?',
                          (conversation(messages(path), r['session_id']), path, os.path.getmtime(path), agent_sid, r['id']))
    c.commit()


# --- queries ----------------------------------------------------------------------------------------------------------

def snippet(text, q):
    if not text:
        return ''
    i = max(text.lower().find(q.lower()) if q else 0, 0)
    return ('…' if i > 60 else '') + text[max(0, i - 60): i + 180].replace('\n', ' ') + '…'


def search(cfg, c, msg):
    sync_answers(cfg, c)
    q = msg.get('q', '').strip()
    # ponytail: LIKE scan; swap for an FTS5 table if the digest count ever makes this slow
    like = f'%{q}%'
    rows = c.execute('''SELECT id, created_at, url, title, user_prompt, agent, answer, digest_md FROM digests
                        WHERE ? = '' OR title LIKE ? OR url LIKE ? OR user_prompt LIKE ? OR digest_md LIKE ? OR answer LIKE ?
                        ORDER BY id DESC LIMIT 50''', (q, like, like, like, like, like)).fetchall()
    return [{'id': r['id'], 'created_at': r['created_at'], 'url': r['url'], 'title': r['title'], 'user_prompt': r['user_prompt'],
             'agent': r['agent'], 'has_answer': bool(r['answer']),
             'snippet': snippet(r['answer'] if (r['answer'] and (not q or q.lower() in r['answer'].lower())) else r['digest_md'], q)}
            for r in rows]


def get(cfg, c, msg):
    sync_answers(cfg, c)
    r = c.execute('SELECT * FROM digests WHERE id=?', (msg['id'],)).fetchone()
    return {k: r[k] for k in r.keys() if k != 'page_json'}


def continue_(cfg, c, msg):
    sync_answers(cfg, c)
    r = c.execute('SELECT * FROM digests WHERE id=?', (msg['id'],)).fetchone()
    if tmux('has-session', '-t', r['tmux_session']).returncode == 0:
        open_terminal(cfg, r['tmux_session'])
        return {'how': 'attached to running', 'tmux_session': r['tmux_session']}
    if not cfg['resume_command'] or not r['agent_session_id']:
        raise RuntimeError(f"tmux session {r['tmux_session']} is gone and agent {r['agent']!r} has no resumable session id; "
                           f'set resume_command in {CONFIG_PATH}')
    start_session(cfg, r['tmux_session'], render(cfg['resume_command'], session_id=r['session_id'], agent_session_id=r['agent_session_id'],
                                                 prompt_file=os.path.join(cfg['work_dir'], f"{r['id']}.prompt.md"),
                                                 digest_file=os.path.join(cfg['work_dir'], f"{r['id']}.md")))
    return {'how': 'resumed agent session in new', 'tmux_session': r['tmux_session']}


def config(cfg, c, msg):
    return dict(cfg, config_path=CONFIG_PATH, config_exists=os.path.exists(CONFIG_PATH), presets=list(PRESETS))


ACTIONS = {'digest': digest, 'search': search, 'get': get, 'continue': continue_, 'config': config}


def main():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return
    msg = json.loads(sys.stdin.buffer.read(struct.unpack('<I', raw)[0]))
    try:
        cfg = load_config()
        reply = ACTIONS[msg['action']](cfg, db(cfg), msg)
    except Exception as e:  # the popup shows this text
        reply = {'error': f'{type(e).__name__}: {e}'}
    data = json.dumps(reply).encode()
    sys.stdout.buffer.write(struct.pack('<I', len(data)) + data)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
