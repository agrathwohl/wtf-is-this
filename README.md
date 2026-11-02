# WTFISTHIS

**A Firefox extension that looks at whatever godforsaken tab you have open, rips out everything useful, and throws it at your coding agent in a fresh tmux session so it can tell you what the fuck you are looking at.**

You know the feeling. You click a link from a PDF. You land on a 40-page paper, a GitHub repo with 11 README badges and zero sentences, a news article with 600 words of ads around 80 words of news, or an email thread with 14 replies that all say "see below". Your brain says *wtf is this*. Now your toolbar says it too.

Click the red **WTF** button. A terminal pops up. Your agent (Claude Code, Codex, OpenCode, Hermes, or whatever other thing you pay $200/month for) is already reading a full digest of the page: URL, title, every meta tag, JSON-LD, headings, the visible text, the links, the text you had selected. It explains it. You ask follow-ups. Everything gets stored in a sqlite database that you can search from the extension popup, including the agent's answers. That's it. That's the whole thing.

It is for people who can edit a JSON file and already have a terminal that doesn't suck. If that is not you, close this tab and go buy a browser "AI sidebar" from someone who wants your data.

## How it works

```
 Firefox tab ──click/shortcut/#WTFISTHIS──▶ ext/extract.js (runs in the page)
                                                  │  url, title, meta[], json-ld, headings,
                                                  │  text, links, selection, counts
                                                  ▼
                                         ext/background.js ──native messaging──▶ host/wtfisthis_host.py
                                                                                      │
                                   sqlite  ◀────────── row + digest.md + prompt.md ───┤
                                                                                      ▼
                                             tmux new-session -d  "$AGENT --flags "$(cat prompt.md)""
                                                                                      │
                                             $TERMINAL -e tmux attach ◀──────────────┘
                                                                                      │
                                   popup search ◀─ answers synced from agent transcripts / tmux pane
```

No server. No cloud. No telemetry. No Electron. A WebExtension, one Python file with zero dependencies, tmux, and your terminal. If any of those words scare you, see the previous paragraph about closing the tab.

## Requirements

- Firefox 115+ (tested on 158). Chrome users: no. Go away. Chrome has no native-messaging host dir you'd enjoy configuring either.
- Linux. macOS probably works if your terminal takes `-e cmd` and you fix the paths; nobody has tried. PRs welcome, whining is not.
- `tmux`.
- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/). The host is one stdlib-only file and the wrapper runs it with `uv run python`. No, there is no `python3` fallback. Install uv, it takes four seconds.
- A terminal emulator that accepts a command argument: alacritty, foot, kitty, ghostty, wezterm, xterm, gnome-terminal, whatever. Configure it, see below.
- An agent CLI with a subscription or API key you are already bleeding money into. Presets exist for `claude`, `codex`, `opencode`, `hermes`. Anything else: write one line of config.

## Install

Two halves. The extension half is on Mozilla's add-on site. The host half is one script in this repo, because AMO does not ship things that spawn tmux on your machine, and thank fuck for that.

1. **Extension:** https://addons.mozilla.org/firefox/addon/wtfisthis/ — click **Add to Firefox**. Signed by Mozilla, auto-updates, no `about:debugging` nonsense.
2. **Host:**
   ```sh
   git clone https://github.com/agrathwohl/wtf-is-this
   cd wtf-is-this
   ./install.sh
   ```
   `install.sh` writes the native-messaging manifest to `~/.mozilla/native-messaging-hosts/wtfisthis.json` (macOS: `~/Library/Application Support/Mozilla/NativeMessagingHosts/`), which is how Firefox is allowed to spawn `host/wtfisthis-host` ([MDN: Native messaging](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging)). It also writes a default config to `~/.config/wtfisthis/config.json` if you have none. **Open it. Edit it.** It picks up `$TERMINAL`; if that's unset you get `xterm -e`, and you deserve it.
3. Click the red **WTF**. If the popup shows an error about the native host, you skipped step 2. Read it again.

### Hacking on it (or: the part where Mozilla ruins your afternoon)

You changed `ext/` and want to run your copy. Release Firefox **refuses to permanently install an unsigned extension**. Not a pref. Not a flag. Compiled in. Source: [Mozilla: Add-on signing in Firefox](https://support.mozilla.org/en-US/kb/add-on-signing-in-firefox). Two options, you will hate both:

**Option A, the temporary load (zero setup, dies on restart):**
1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**
3. Pick `ext/manifest.json`.
4. Repeat every time you restart Firefox, like an animal.

**Option B, sign your own copy (ten minutes once, permanent):**
1. Get AMO API credentials: https://addons.mozilla.org/developers/addon/api/key/. You get a "JWT issuer" and a "JWT secret". Yes, the free account. No, nobody reviews unlisted add-ons, a robot does.
2. Change the add-on id in `ext/manifest.json` (`browser_specific_settings.gecko.id`) **and** in `host/wtfisthis.json` (`allowed_extensions`) to something that is yours, e.g. `wtfisthis@yourdomain.example`. The id in the repo belongs to the author's AMO account and the robot will tell you to fuck off if you reuse it.
3. ```sh
   web-ext sign -s ext --channel unlisted --api-key 'user:XXXX:XXX' --api-secret 'XXXX'
   ```
   (Nix: `nix run nixpkgs#web-ext -- sign ...`. npm: `npm i -g web-ext`.) Reference: [web-ext command reference](https://extensionworkshop.com/documentation/develop/web-ext-command-reference/#web-ext-sign). AMO never accepts a version number twice, so bump `version` in the manifest first.
4. Open the signed file: `firefox web-ext-artifacts/*.xpi`, click **Add**. If your Firefox runs with an explicit `--profile`, pass the same absolute path, or you get a second Firefox on your default profile and a very confusing afternoon.

Developer Edition and Nightly honor `xpinstall.signatures.required = false`. Release and Beta do not. Don't argue with me, argue with Mozilla.

## Use

- Click the **WTF** toolbar button. Optionally type what you actually want to know ("is this paper's statistics bullshit?", "how do I build this repo?"). Hit **WTF IS THIS?**
- Or press **Ctrl+Alt+W** on any tab. No prompt, straight to the terminal.
- Or from a shell: `firefox 'https://example.com/whatever#WTFISTHIS'`. The extension sees the marker, waits for the page to finish loading, digests it, strips the marker from the stored URL. This is how the author tests it and how you can wire it into anything that can run a command.
- The popup's search box searches titles, URLs, your prompts, the digest text, and the agent's answers. **show** expands a row (answer first, digest below). **continue in tmux** reopens a terminal on the still-running session, or, for agents that support it, resumes the agent's session in a fresh tmux session after the old one died.
- "open as tab" turns the popup into a full page, for when the 560px popup offends you.

## Config

`~/.config/wtfisthis/config.json` (or wherever `$WTFISTHIS_CONFIG` points). Every key is optional. Unknown keys are ignored, so typos fail silently, so don't make typos.

| key | default | what |
| --- | --- | --- |
| `agent` | `"claude"` | preset: `claude`, `codex`, `opencode`, `hermes`, `custom` |
| `start_command` | preset's | shell string run inside the new tmux session |
| `resume_command` | preset's | shell string to resume a dead session; `null` = reattach only |
| `transcript` | preset's | how answers get into the DB: `claude`, `codex`, `pane`, `none` |
| `terminal` | `"$TERMINAL -e"` | command prefix; `tmux attach-session -t NAME` is appended |
| `env` | `{}` | extra `export`s inside the tmux session, e.g. `{"PATH": "/weird/bin:$PATH"}`; values are double-quoted, so `$VAR` expands and spaces survive |
| `tmux_prefix` | `"wtfisthis"` | sessions are named `PREFIX-<row id>` |
| `data_dir` | `"~/.local/share/wtfisthis"` | holds `wtfisthis.db` and `work/` (the agent's cwd) |
| `preamble` | built-in | the instruction text in front of the digest; `{digest_file}` and `{session_id}` are substituted |

Placeholders in `start_command` / `resume_command`, each shell-quoted for you:

- `{prompt_file}`: the full prompt (instructions + digest). Pass it as `"$(cat {prompt_file})"`. The host keeps it under 120 KB because Linux caps a single argv entry at 128 KiB ([`MAX_ARG_STRLEN`](https://github.com/torvalds/linux/blob/master/include/uapi/linux/binfmts.h)); the full digest is always in `{digest_file}` and the prompt says so.
- `{digest_file}`: the digest markdown in `data_dir/work/<id>.md`.
- `{session_id}`: a UUID we generate. If your start command contains it, we assume the agent adopted it as its own session id.
- `{agent_session_id}`: what the agent itself calls the session (equals `{session_id}` when you passed it; discovered from the transcript for Codex).

### Presets

| preset | start | resume | answers via | source |
| --- | --- | --- | --- | --- |
| `claude` | `claude --session-id {session_id} "$(cat {prompt_file})"` | `claude --resume {agent_session_id}` | `~/.claude/projects/*/<id>.jsonl` | `claude --help` |
| `codex` | `codex "$(cat {prompt_file})"` | `codex resume {agent_session_id}` | `~/.codex/sessions/**/rollout-*.jsonl`, found by the session token in the prompt | [Codex CLI reference](https://developers.openai.com/codex/cli/reference) |
| `opencode` | `opencode --session {session_id} --prompt "$(cat {prompt_file})"` | `opencode --session {agent_session_id}` | tmux pane capture | [OpenCode CLI docs](https://opencode.ai/docs/cli/) |
| `hermes` | `hermes chat -q "$(cat {prompt_file})"` | none | tmux pane capture | [Hermes CLI reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands) |
| `custom` | you write it | you write it | tmux pane capture | you |

Presets do **not** add yolo flags. If you want `--dangerously-skip-permissions`, `--yolo`, `--auto`, `--dangerously-bypass-approvals-and-sandbox` or whatever your vendor calls "let the robot run `rm`", put it in `start_command` yourself. The author does. Example, the author's actual config, Claude Code via a Nix flake because of course:

```json
{
  "agent": "claude",
  "start_command": "nix run github:ryoppippi/nix-claude-code -- --dangerously-skip-permissions --session-id {session_id} \"$(cat {prompt_file})\"",
  "resume_command": "nix run github:ryoppippi/nix-claude-code -- --dangerously-skip-permissions --resume {agent_session_id}",
  "terminal": "alacritty -e"
}
```

`transcript: "pane"` means: while the tmux session is alive, `tmux capture-pane -p -S -` is stored as the answer each time you open the popup. It's exactly as good as your agent's TUI lets it be. Agents that redraw the whole screen (alternate-screen TUIs) give you the last screen, not the history. Agents that write proper transcript files get proper parsers; only Claude Code and Codex have one so far, because those are the formats the author could verify on disk. Send a PR with a real sample file or don't send one.

## Where your shit lives

- `~/.local/share/wtfisthis/wtfisthis.db`: one table, `digests`. Columns: `id, created_at, url, title, user_prompt, page_json, digest_md, agent, session_id, agent_session_id, tmux_session, transcript_path, answer, transcript_mtime`. It's sqlite. Open it with whatever. Search is `LIKE '%q%'` over five columns because you will never have enough rows for FTS to matter, and if you do, congratulations on your reading problem.
- `~/.local/share/wtfisthis/work/<id>.md` and `<id>.prompt.md`: what the agent got. The agent's cwd is `work/`, so it can `cat` the digest and anything else it wants.
- `~/.config/wtfisthis/config.json`: see above.
- Nothing else. No browser storage, no cache, no "sync".

## Known limits, a.k.a. things you will file issues about anyway

- **Cloudflare-walled pages digest exactly what Firefox rendered.** That's the point: it runs in *your* browser with *your* cookies. Run it in a fresh profile and you get a captcha digested in loving detail.
- **Firefox's built-in PDF viewer, `about:` pages, and other privileged pages don't allow content scripts.** You get URL + title + the extraction error in the digest, and the prompt tells the agent to fetch the URL itself. It usually does.
- **The extension is Manifest V2.** Firefox still runs it. When Mozilla kills MV2 the author will be angry on the internet and then port it.
- **One digest = one agent session = one tmux session = one terminal window.** If that's too many windows, you have a window manager problem, not a WTFISTHIS problem.
- **Answers only sync when you open the popup** (or search). There is no daemon. There will be no daemon.

## License

MIT. See LICENSE. Do whatever you want, just do not come crying.
