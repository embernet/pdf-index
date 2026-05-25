"""HTML/CSS/JS template for the web bundle.

Single self-contained document. The render_html function takes the
payload dict produced by web_bundle.build_payload_from_inputs and
returns a complete HTML string.
"""
from __future__ import annotations

import html
import json


_CSS = """
:root {
  --toolbar-h: 56px;
  --sidebar-w: 320px;
  --hl-color: rgba(255, 230, 0, 0.42);
  --hl-active: rgba(255, 140, 0, 0.55);
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: #f0f0f0;
  color: #222;
}

#toolbar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  padding: 8px 12px;
  background: #fff;
  border-bottom: 1px solid #d0d0d0;
  min-height: var(--toolbar-h);
}
#toolbar button, #toolbar input, #toolbar .group {
  font: inherit;
}
#toolbar .group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
#toolbar button {
  padding: 4px 10px;
  background: #f5f5f5;
  border: 1px solid #c0c0c0;
  border-radius: 4px;
  cursor: pointer;
}
#toolbar button:hover { background: #e8e8e8; }
#toolbar button.active { background: #b3d9ff; border-color: #6fa8dc; }
#toolbar input[type="text"], #toolbar input[type="number"] {
  padding: 4px 6px;
  border: 1px solid #c0c0c0;
  border-radius: 4px;
  width: 70px;
}
#toolbar .total { color: #666; font-size: 0.9em; }

#layout {
  display: flex;
  align-items: stretch;
}

#document {
  flex: 1;
  min-width: 0;
  padding: 12px;
  overflow-y: auto;
  height: calc(100vh - var(--toolbar-h));
}
body.mode-page #document {
  scroll-snap-type: y mandatory;
}

.page {
  margin: 0 auto 16px auto;
  max-width: 95%;
  scroll-snap-align: start;
}
body.mode-page .page {
  height: calc(100vh - var(--toolbar-h) - 24px);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.page-header {
  font-weight: 600;
  font-size: 0.95em;
  color: #555;
  margin: 0 0 6px 2px;
}
.page-canvas {
  position: relative;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  width: 100%;
}
body.mode-page .page-canvas {
  height: 100%;
  width: auto;
}
.page-canvas img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.hl {
  position: absolute;
  background: var(--hl-color);
  cursor: pointer;
  border-radius: 2px;
  transition: background 0.12s;
}
.hl:hover { background: var(--hl-active); }
body.highlights-off .hl { display: none; }

#sidebar {
  width: var(--sidebar-w);
  background: #fafafa;
  border-left: 1px solid #d0d0d0;
  height: calc(100vh - var(--toolbar-h));
  display: flex;
  flex-direction: column;
}
body.sidebar-hidden #sidebar { display: none; }
#sidebar header {
  padding: 10px 12px;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
}
#sidebar .filter {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #c0c0c0;
  border-radius: 4px;
}
#sidebar .style-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
#sidebar .style-bar button {
  font-size: 0.85em;
  padding: 2px 8px;
  background: #f0f0f0;
  border: 1px solid #c0c0c0;
  border-radius: 999px;
  cursor: pointer;
}
#sidebar .style-bar button.active {
  background: #b3d9ff;
  border-color: #6fa8dc;
}
#sidebar .entries {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}
.entry {
  padding: 4px 6px;
  margin: 1px 0;
  border-radius: 3px;
  font-size: 0.9em;
  line-height: 1.35;
}
.entry b { font-weight: 600; }
.entry a {
  color: #0a58ca;
  text-decoration: none;
  margin: 0 1px;
  cursor: pointer;
}
.entry a:hover { text-decoration: underline; }
.entry.pulse {
  animation: pulse-bg 1.5s ease-out;
}
@keyframes pulse-bg {
  0%, 30% { background: #ffe48a; }
  100% { background: transparent; }
}
"""

_JS = r"""
(function () {
  const rawPayload = document.getElementById('bundle-data').textContent;
  // Reverse the </ -> <\/ escape applied by the Python side
  const payload = JSON.parse(rawPayload.replace(/<\\\//g, '</'));
  const doc = document.getElementById('document');
  const entriesEl = document.getElementById('entries');
  const pageInput = document.getElementById('page-input');
  const totalEl = document.getElementById('page-total');
  const intervalEl = document.getElementById('interval-input');
  const playBtn = document.getElementById('play-btn');

  // ----- Build sidebar entries (per bucket) -----
  let currentBucket = 'aggregate';
  function renderEntries() {
    const list = payload.buckets[currentBucket] || [];
    const filter = (document.getElementById('filter').value || '').toLowerCase();
    entriesEl.innerHTML = '';
    for (const entry of list) {
      if (filter && !entry.display.toLowerCase().includes(filter)) continue;
      const row = document.createElement('div');
      row.className = 'entry';
      row.id = 'term-' + entry.key;
      row.dataset.termKey = entry.key;
      const name = document.createElement('b');
      name.textContent = entry.display;
      row.appendChild(name);
      row.appendChild(document.createTextNode(' '));
      entry.pages.forEach((p, i) => {
        if (i > 0) row.appendChild(document.createTextNode(', '));
        const link = document.createElement('a');
        link.textContent = p.label;
        link.dataset.physical = p.physical;
        link.addEventListener('click', () => goToPage(p.physical));
        row.appendChild(link);
      });
      entriesEl.appendChild(row);
    }
  }

  // ----- Bucket selector -----
  document.querySelectorAll('.style-bar button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.style-bar button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentBucket = btn.dataset.bucket;
      renderEntries();
    });
  });

  // ----- Filter input -----
  document.getElementById('filter').addEventListener('input', renderEntries);

  // ----- Page navigation -----
  const pageEls = Array.from(document.querySelectorAll('.page'));
  totalEl.textContent = '/' + payload.pdf.page_count;

  function currentPageIdx() {
    const scrollTop = doc.scrollTop;
    let best = 0;
    let bestDist = Infinity;
    for (let i = 0; i < pageEls.length; i++) {
      const top = pageEls[i].offsetTop;
      const dist = Math.abs(top - scrollTop);
      if (dist < bestDist) { bestDist = dist; best = i; }
    }
    return best;
  }

  function goToPage(physicalIdx) {
    const el = pageEls[physicalIdx];
    if (!el) return;
    el.scrollIntoView({ behavior: document.body.classList.contains('mode-page') ? 'auto' : 'smooth' });
  }

  document.getElementById('first-btn').addEventListener('click', () => goToPage(0));
  document.getElementById('last-btn').addEventListener('click', () => goToPage(pageEls.length - 1));
  document.getElementById('prev-btn').addEventListener('click', () => goToPage(Math.max(0, currentPageIdx() - 1)));
  document.getElementById('next-btn').addEventListener('click', () => goToPage(Math.min(pageEls.length - 1, currentPageIdx() + 1)));

  pageInput.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const v = pageInput.value.trim().toLowerCase();
    pageInput.value = '';
    if (!v) return;
    const idx = payload.pageLabels.findIndex(lbl => (lbl || '').toLowerCase() === v);
    if (idx >= 0) goToPage(idx);
  });

  // ----- View mode toggle -----
  function setMode(mode) {
    document.body.classList.toggle('mode-page', mode === 'page');
    document.body.classList.toggle('mode-scroll', mode === 'scroll');
    document.getElementById('mode-page-btn').classList.toggle('active', mode === 'page');
    document.getElementById('mode-scroll-btn').classList.toggle('active', mode === 'scroll');
  }
  document.getElementById('mode-page-btn').addEventListener('click', () => setMode('page'));
  document.getElementById('mode-scroll-btn').addEventListener('click', () => setMode('scroll'));

  // ----- Sidebar toggle (persisted) -----
  function setSidebar(visible) {
    document.body.classList.toggle('sidebar-hidden', !visible);
    document.getElementById('sidebar-btn').classList.toggle('active', visible);
    try { localStorage.setItem('pdfix-sidebar', visible ? '1' : '0'); } catch (e) {}
  }
  document.getElementById('sidebar-btn').addEventListener('click', () => {
    setSidebar(document.body.classList.contains('sidebar-hidden'));
  });

  // ----- Highlights toggle (persisted) -----
  function setHighlights(on) {
    document.body.classList.toggle('highlights-off', !on);
    document.getElementById('hl-btn').classList.toggle('active', on);
    try { localStorage.setItem('pdfix-hl', on ? '1' : '0'); } catch (e) {}
  }
  document.getElementById('hl-btn').addEventListener('click', () => {
    setHighlights(document.body.classList.contains('highlights-off'));
  });

  // ----- In-page highlight clicks -> scroll sidebar entry -----
  document.querySelectorAll('.hl').forEach(span => {
    span.addEventListener('click', () => {
      const key = span.dataset.term;
      if (!key) return;
      const inBucket = (payload.buckets[currentBucket] || []).some(e => e.key === key);
      if (!inBucket) {
        currentBucket = 'aggregate';
        document.querySelectorAll('.style-bar button').forEach(b => {
          b.classList.toggle('active', b.dataset.bucket === 'aggregate');
        });
        renderEntries();
      }
      const target = document.getElementById('term-' + key);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.remove('pulse');
        void target.offsetWidth;
        target.classList.add('pulse');
      }
    });
  });

  // ----- Slideshow -----
  let timer = null;
  function isPlaying() { return timer !== null; }
  function setPlayBtn(playing) {
    playBtn.textContent = playing ? 'Pause' : 'Play';
    playBtn.classList.toggle('active', playing);
  }
  function stop() {
    if (timer !== null) { clearInterval(timer); timer = null; }
    setPlayBtn(false);
  }
  function start() {
    stop();
    let seconds = parseFloat(intervalEl.value);
    if (!isFinite(seconds) || seconds < 1) seconds = 5;
    if (seconds > 60) seconds = 60;
    timer = setInterval(() => {
      const next = currentPageIdx() + 1;
      if (next >= pageEls.length) { stop(); return; }
      goToPage(next);
    }, seconds * 1000);
    setPlayBtn(true);
  }
  playBtn.addEventListener('click', () => { isPlaying() ? stop() : start(); });

  // ----- Keyboard shortcuts -----
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      goToPage(Math.max(0, currentPageIdx() - 1));
      e.preventDefault();
    } else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
      goToPage(Math.min(pageEls.length - 1, currentPageIdx() + 1));
      e.preventDefault();
    } else if (e.key === 'Home') {
      goToPage(0); e.preventDefault();
    } else if (e.key === 'End') {
      goToPage(pageEls.length - 1); e.preventDefault();
    } else if (e.key === '/') {
      document.getElementById('filter').focus(); e.preventDefault();
    } else if (e.key.toLowerCase() === 'i') {
      setSidebar(document.body.classList.contains('sidebar-hidden'));
    } else if (e.key.toLowerCase() === 'h') {
      setHighlights(document.body.classList.contains('highlights-off'));
    }
  });

  // ----- Boot -----
  setMode('page');
  try {
    setSidebar(localStorage.getItem('pdfix-sidebar') !== '0');
    setHighlights(localStorage.getItem('pdfix-hl') !== '0');
  } catch (e) {
    setSidebar(true);
    setHighlights(true);
  }
  renderEntries();
})();
"""


def _escape_for_script(text: str) -> str:
    """Replace </ with <\\/ inside the embedded JSON so a term containing
    the literal </script> string can't break out of the script island.
    The JS in _JS reverses this with a regex before JSON.parse.
    """
    return text.replace("</", "<\\/")


def render_html(payload: dict) -> str:
    """Render the full HTML document for the given payload."""
    page_count = payload["pdf"]["page_count"]
    page_labels = payload["pageLabels"]
    page_dims = payload["pageDims"]
    page_highlights = payload["highlights"]
    title = html.escape(payload["pdf"].get("name", "Index"))

    bucket_buttons = []
    bucket_names = [
        ("aggregate", "Aggregate"),
        ("italic", "Italic"),
        ("bold", "Bold"),
        ("caps", "Caps"),
        ("single-quotes", "Single Quotes"),
        ("other", "Other"),
    ]
    for key, label in bucket_names:
        active = " active" if key == "aggregate" else ""
        bucket_buttons.append(
            f'<button class="bucket{active}" data-bucket="{key}">{label}</button>'
        )

    page_cards = []
    for i in range(page_count):
        label = html.escape(page_labels[i] or str(i + 1))
        dims = page_dims[i]
        aspect = f"{dims['w']}/{dims['h']}"
        img_name = f"images/page-{i+1:04d}.png"

        hls_html_parts = []
        for hl in page_highlights.get(str(i), []):
            left, top, w, h = hl["rect_pct"]
            key = html.escape(hl["term_key"], quote=True)
            hls_html_parts.append(
                f'<span class="hl" data-term="{key}" '
                f'style="left:{left:.3f}%;top:{top:.3f}%;'
                f'width:{w:.3f}%;height:{h:.3f}%"></span>'
            )

        page_cards.append(
            f'<div class="page" data-physical="{i}" data-label="{label}">'
            f'<div class="page-header">Page {label}</div>'
            f'<div class="page-canvas" style="aspect-ratio:{aspect}">'
            f'<img src="{img_name}" alt="Page {label}" loading="lazy">'
            f'{"".join(hls_html_parts)}'
            f'</div>'
            f'</div>'
        )

    payload_json = _escape_for_script(json.dumps(payload, ensure_ascii=False))

    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        f"<title>{title} — Index</title>"
        f"<style>{_CSS}</style>"
        "</head><body class=\"mode-page\">"
        '<div id="toolbar">'
        '<div class="group">'
        '<button id="mode-page-btn" class="active">Pages</button>'
        '<button id="mode-scroll-btn">Scroll</button>'
        '</div>'
        '<div class="group">'
        '<button id="sidebar-btn" class="active" title="Toggle sidebar (i)">Sidebar</button>'
        '<button id="hl-btn" class="active" title="Toggle highlights (h)">Highlights</button>'
        '</div>'
        '<div class="group">'
        '<button id="first-btn" title="First page">« First</button>'
        '<button id="prev-btn" title="Previous page (←)">‹ Prev</button>'
        '<input id="page-input" type="text" placeholder="Page" title="Type a page label and press Enter">'
        '<span class="total" id="page-total"></span>'
        '<button id="next-btn" title="Next page (→)">Next ›</button>'
        '<button id="last-btn" title="Last page">Last »</button>'
        '</div>'
        '<div class="group">'
        '<button id="play-btn" title="Play/Pause slideshow">Play</button>'
        '<label>Interval: <input id="interval-input" type="number" min="1" max="60" step="1" value="5"> s</label>'
        '</div>'
        '</div>'
        '<div id="layout">'
        '<div id="document">'
        + "".join(page_cards) +
        '</div>'
        '<aside id="sidebar">'
        '<header>'
        '<input class="filter" id="filter" type="text" placeholder="Filter index...">'
        '<div class="style-bar">' + "".join(bucket_buttons) + '</div>'
        '</header>'
        '<div class="entries" id="entries"></div>'
        '</aside>'
        '</div>'
        f'<script id="bundle-data" type="application/json">{payload_json}</script>'
        f'<script>{_JS}</script>'
        '</body></html>'
    )
