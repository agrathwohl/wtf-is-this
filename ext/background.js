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
  page.url = page.url.replace(MARKER, '');
  return native({ action: 'digest', page, user_prompt: userPrompt });
}

browser.runtime.onMessage.addListener((m) => (m.action === 'digest' ? digest(m.tabId, m.user_prompt) : native(m)));

browser.commands.onCommand.addListener(async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  digest(tab.id);
});

// CLI trigger: `firefox "https://example.com/page#WTFISTHIS"` digests the page once it finishes loading.
const marked = (t) => t.url && t.url.endsWith(MARKER);
browser.tabs.onUpdated.addListener((id, info, tab) => { if (info.status === 'complete' && marked(tab)) digest(id); }, { properties: ['status'] });
browser.tabs.query({}).then((tabs) => tabs.filter((t) => marked(t) && t.status === 'complete').forEach((t) => digest(t.id)));
