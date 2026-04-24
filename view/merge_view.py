"""Merge tool view — card-based UI for reviewing containment merge suggestions."""
import html as html_mod

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PyQt6.QtCore import pyqtSignal


class MergeView(QWidget):
    """Displays merge suggestion cards with Merge / Keep Separate / Revisit actions."""

    merge_requested = pyqtSignal(str, str)   # source, target
    separate_requested = pyqtSignal(str)      # source
    revisit_requested = pyqtSignal(str)       # source

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_link_clicked)
        layout.addWidget(self.browser)

        self._pending = []   # list of suggestion dicts
        self._decided = []   # list of (suggestion_dict, decision_str) tuples

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_suggestions(self, pending, decided):
        """Render merge suggestion cards.

        pending: list of suggestion dicts (not yet decided)
        decided: list of (suggestion_dict, decision_string) tuples
        """
        self._pending = list(pending)
        self._decided = list(decided)
        self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    _STYLE = """\
<style>
body { font-family: sans-serif; font-size: 13px; }
a { text-decoration: none; }
</style>"""

    def _render(self):
        parts = [self._STYLE]

        np = len(self._pending)
        nd = len(self._decided)

        parts.append('<h2>Merge Tool</h2>')

        if np == 0 and nd == 0:
            parts.append(
                '<p style="color:#666;">No containment relationships found '
                'in the current index.</p>'
            )
        else:
            parts.append(
                f'<p>{np} pending suggestion{"s" if np != 1 else ""}, '
                f'{nd} decided</p>'
            )

        # ---- Pending cards ----
        if np > 0:
            parts.append('<h3>Pending</h3>')
            for i, s in enumerate(self._pending):
                parts.append(self._card_pending(i, s))

        # ---- Decided cards ----
        if nd > 0:
            parts.append('<h3>Decided</h3>')
            for i, (s, decision) in enumerate(self._decided):
                parts.append(self._card_decided(i, s, decision))

        self.browser.setHtml('\n'.join(parts))

    # ---- individual card helpers ----

    def _card_pending(self, idx, s):
        esc = html_mod.escape
        source = esc(s["source"])
        sp = s["source_pages"]
        target = esc(s["target"])

        container_lines = []
        for c in s["containers"]:
            entry = esc(c["entry"])
            pages = c["pages"]
            tag = (' <span style="color:#0a0;font-size:11px;">'
                   '(merge target)</span>') if c["entry"] == s["target"] else ''
            container_lines.append(
                f'&nbsp;&nbsp;&bull; <b>{entry}</b> '
                f'<span style="color:#666;font-size:12px;">'
                f'({pages} pg{"s" if pages != 1 else ""})</span>{tag}'
            )

        containers_html = '<br>'.join(container_lines)

        return (
            f'<div style="margin:6px 0;padding:8px;border:1px solid #ccc;'
            f'background:#fafafa;">'
            f'<b>{source}</b> '
            f'<span style="color:#666;font-size:12px;">'
            f'({sp} pg{"s" if sp != 1 else ""})</span><br>'
            f'<span style="color:#555;">contained in:</span><br>'
            f'{containers_html}<br><br>'
            f'[<a href="#merge|{idx}" style="color:#28a745;font-weight:bold;">'
            f'Merge into &ldquo;{target}&rdquo;</a>] &nbsp; '
            f'[<a href="#separate|{idx}" style="color:#6c757d;">'
            f'Keep Separate</a>]'
            f'</div>'
        )

    def _card_decided(self, idx, s, decision):
        esc = html_mod.escape
        source = esc(s["source"])

        if decision == "merged":
            target = esc(s.get("target", "?"))
            badge = (f'<span style="color:#155724;background:#d4edda;'
                     f'padding:1px 6px;font-size:11px;">'
                     f'Merged into &ldquo;{target}&rdquo;</span>')
        else:
            badge = ('<span style="color:#383d41;background:#e2e3e5;'
                     'padding:1px 6px;font-size:11px;">Kept Separate</span>')

        return (
            f'<div style="margin:6px 0;padding:8px;border:1px solid #ddd;'
            f'background:#f0f0f0;">'
            f'<b>{source}</b> {badge}<br>'
            f'[<a href="#revisit|{idx}" style="color:#856404;">Revisit</a>]'
            f'</div>'
        )

    # ------------------------------------------------------------------
    # Link handling
    # ------------------------------------------------------------------

    def _on_link_clicked(self, url):
        fragment = url.fragment()
        if not fragment:
            return
        parts = fragment.split("|", 1)
        if len(parts) != 2:
            return
        action = parts[0]
        try:
            idx = int(parts[1])
        except ValueError:
            return

        if action == "merge" and 0 <= idx < len(self._pending):
            s = self._pending[idx]
            self.merge_requested.emit(s["source"], s["target"])
        elif action == "separate" and 0 <= idx < len(self._pending):
            s = self._pending[idx]
            self.separate_requested.emit(s["source"])
        elif action == "revisit" and 0 <= idx < len(self._decided):
            s, _ = self._decided[idx]
            self.revisit_requested.emit(s["source"])
