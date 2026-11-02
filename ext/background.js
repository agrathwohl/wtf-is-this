// WTFISTHIS background: glue between popup / shortcut / URL marker and the native host.
const MARKER = '#WTFISTHIS';
const native = (msg) => browser.runtime.sendNativeMessage('wtfisthis', msg).then((r) => (r && r.error ? Promise.reject(new Error(r.error)) : r));

async function digest(tabId, userPrompt = '') {
  const tab = await browser.tabs.get(tabId);
  let page;
  try {
    [page] = await browser.tabs.executeScript(tabId, { file: 'extract.js' });
  } catch (e) {
    // about:, the PDF viewer and other privileged pages refuse content scripts; send what the tab API knows.
    page = { url: tab.url, title: tab.title, extract_error: String(e) };
  }
  if (page.url.endsWith(MARKER)) {
    page.url = page.url.slice(0, -MARKER.length);
    browser.tabs.executeScript(tabId, { code: 'history.replaceState(null, "", location.href.slice(0, -' + MARKER.length + '))' }).catch(() => {});
  }
  return native({ action: 'digest', page, user_prompt: userPrompt });
}

browser.runtime.onMessage.addListener((m) => (m.action === 'digest' ? digest(m.tabId, m.user_prompt) : native(m)));

browser.commands.onCommand.addListener(async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  digest(tab.id);
});

// CLI trigger: `firefox "https://example.com/page#WTFISTHIS"` digests the page once it finishes loading.
// Cloudflare's "Just a moment..." interstitial also completes with the marker and then redirects; skip it and wait for the real page.
const marked = (t) => t.url && t.url.endsWith(MARKER);
const busy = new Set();
async function digestMarked(tabId) {
  if (busy.has(tabId)) return;
  busy.add(tabId);
  try {
    const [interstitial] = await browser.tabs.executeScript(tabId, { code: 'document.title === "Just a moment..." || !!document.querySelector("#challenge-running")' });
    if (!interstitial) await digest(tabId);
  } finally { busy.delete(tabId); }
}
browser.tabs.onUpdated.addListener((id, info, tab) => { if (info.status === 'complete' && marked(tab)) digestMarked(id); }, { properties: ['status'] });
browser.tabs.query({}).then((tabs) => tabs.filter((t) => marked(t) && t.status === 'complete').forEach((t) => digestMarked(t.id)));
