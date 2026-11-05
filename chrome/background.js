// WTFISTHIS background (Chrome, MV3 service worker): glue between popup / shortcut / URL marker and the native host.
// Same flow as ext/background.js; chrome.scripting replaces tabs.executeScript and onMessage needs sendResponse.
const MARKER = '#WTFISTHIS';
const native = (msg) => chrome.runtime.sendNativeMessage('wtfisthis', msg).then((r) => (r && r.error ? Promise.reject(new Error(r.error)) : r));
const inject = (tabId, what) => chrome.scripting.executeScript({ target: { tabId }, ...what }).then(([r]) => r.result);

async function digest(tabId, userPrompt = '') {
  const tab = await chrome.tabs.get(tabId);
  let page;
  try {
    page = await inject(tabId, { files: ['extract.js'] });
    if (!page) throw new Error('extract.js returned nothing');
  } catch (e) {
    // chrome://, the PDF viewer and other privileged pages refuse content scripts; send what the tab API knows.
    page = { url: tab.url, title: tab.title, extract_error: String(e) };
  }
  if (page.url.endsWith(MARKER)) {
    page.url = page.url.slice(0, -MARKER.length);
    inject(tabId, { func: (n) => history.replaceState(null, '', location.href.slice(0, -n)), args: [MARKER.length] }).catch(() => {});
  }
  return native({ action: 'digest', page, user_prompt: userPrompt });
}

chrome.runtime.onMessage.addListener((m, sender, respond) => {
  (m.action === 'digest' ? digest(m.tabId, m.user_prompt) : native(m)).then(respond, (e) => respond({ error: e.message || String(e) }));
  return true;
});

chrome.commands.onCommand.addListener(async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  digest(tab.id);
});

// CLI trigger: `google-chrome "https://example.com/page#WTFISTHIS"` digests the page once it finishes loading.
// Cloudflare's "Just a moment..." interstitial also completes with the marker and then redirects; skip it and wait for the real page.
const marked = (t) => t.url && t.url.endsWith(MARKER);
const busy = new Set();
async function digestMarked(tabId) {
  if (busy.has(tabId)) return;
  busy.add(tabId);
  try {
    const interstitial = await inject(tabId, { func: () => document.title === 'Just a moment...' || !!document.querySelector('#challenge-running') });
    if (!interstitial) await digest(tabId);
  } finally { busy.delete(tabId); }
}
chrome.tabs.onUpdated.addListener((id, info, tab) => { if (info.status === 'complete' && marked(tab)) digestMarked(id); });
chrome.tabs.query({}).then((tabs) => tabs.filter((t) => marked(t) && t.status === 'complete').forEach((t) => digestMarked(t.id)));
