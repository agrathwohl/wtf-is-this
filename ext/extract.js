// Runs inside the page; the last expression is returned to background.js.
(() => {
  const d = document;
  const squash = (s) => s.replace(/\s+/g, ' ').trim();
  const meta = {};
  for (const m of d.querySelectorAll('meta[name], meta[property], meta[http-equiv]')) {
    const k = m.getAttribute('name') || m.getAttribute('property') || m.getAttribute('http-equiv');
    const v = m.getAttribute('content');
    if (v) (meta[k] ||= []).push(v);
  }
  const root = d.querySelector('article, main, [role=main]') || d.body;
  const text = (root ? root.innerText : '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  const links = [...d.links].filter((a) => /^https?:/.test(a.href)).map((a) => [squash(a.innerText).slice(0, 80), a.href]).filter((l) => l[0]);
  return {
    url: location.href,
    canonical: d.querySelector('link[rel=canonical]')?.href || null,
    title: d.title,
    lang: d.documentElement.lang || null,
    charset: d.characterSet,
    content_type: d.contentType,
    referrer: d.referrer || null,
    last_modified: d.lastModified,
    captured_at: new Date().toISOString(),
    selection: String(getSelection()).trim().slice(0, 20000),
    meta,
    jsonld: [...d.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent.trim()).filter(Boolean).slice(0, 10).map((s) => s.slice(0, 20000)),
    feeds: [...d.querySelectorAll('link[type*="rss"], link[type*="atom"]')].map((l) => l.href),
    headings: [...d.querySelectorAll('h1, h2, h3')].map((h) => '#'.repeat(+h.tagName[1]) + ' ' + squash(h.innerText)).filter((h) => h.length > 3).slice(0, 200),
    text_root: root === d.body ? 'body' : root.tagName.toLowerCase(),
    text_chars: text.length,
    word_count: text.split(/\s+/).filter(Boolean).length,
    text: text.slice(0, 300000),
    link_count: d.links.length,
    links: links.slice(0, 80),
    image_count: d.images.length,
  };
})();
