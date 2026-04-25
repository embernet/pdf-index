"""Reports view — displays index quality review reports in a QTextBrowser."""
import html

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSpinBox, QLabel, QTextBrowser,
)
from PyQt6.QtCore import pyqtSignal, QUrl

from model.reports import ReportSection, PageRef, format_page_ref


class ReportsView(QWidget):
    """Displays index quality review reports with navigation links."""

    run_reports_requested = pyqtSignal(int, int)       # (thin_threshold, dense_threshold)
    run_report_requested  = pyqtSignal(str, int, int)  # (report_id, thin_threshold, dense_threshold)
    navigate_requested    = pyqtSignal(str)            # fragment like "42|Smith, John"

    MAX_LINKS = 15  # Maximum number of page links to display per term

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # --- Toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        run_btn = QPushButton("Run All Reports")
        run_btn.clicked.connect(self._on_run_all)
        toolbar.addWidget(run_btn)

        toolbar.addWidget(QLabel("Thin ≤"))
        self.thin_spin = QSpinBox()
        self.thin_spin.setMinimum(1)
        self.thin_spin.setMaximum(10)
        self.thin_spin.setValue(1)
        toolbar.addWidget(self.thin_spin)

        toolbar.addWidget(QLabel("Dense ≥"))
        self.dense_spin = QSpinBox()
        self.dense_spin.setMinimum(5)
        self.dense_spin.setMaximum(500)
        self.dense_spin.setValue(20)
        toolbar.addWidget(self.dense_spin)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # --- Browser ---
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._handle_link_click)
        layout.addWidget(self.browser, stretch=1)

        self.set_not_run()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_not_run(self):
        self.browser.setHtml(
            "<html><body style='font-family:sans-serif; padding:12px;'>"
            "<p style='color:#888; font-style:italic;'>No reports have been run yet."
            " Click <b>Run All Reports</b> to analyse the index.</p>"
            "</body></html>"
        )

    def set_reports(self, sections):
        """Render a list of ReportSection objects into the browser."""
        self.browser.setHtml(self._render_html(sections))

    # ------------------------------------------------------------------
    # Link handling
    # ------------------------------------------------------------------

    def _handle_link_click(self, url: QUrl):
        fragment = url.fragment()
        if not fragment:
            return
        if fragment.startswith("run:"):
            report_id = fragment[len("run:"):]
            self.run_report_requested.emit(
                report_id,
                self.thin_spin.value(),
                self.dense_spin.value(),
            )
        else:
            self.navigate_requested.emit(fragment)

    # ------------------------------------------------------------------
    # Toolbar slot
    # ------------------------------------------------------------------

    def _on_run_all(self):
        self.run_reports_requested.emit(self.thin_spin.value(), self.dense_spin.value())

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    _STYLE = """\
<html>
<head><style>
  body { font-family: sans-serif; font-size: 13px; padding: 8px; }
  h3 { color: #333; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 16px; }
  h3 a { font-size: 0.75em; color: #888; text-decoration: none; margin-left: 8px; }
  ul { margin: 4px 0 8px 0; padding-left: 16px; }
  li { margin-bottom: 6px; }
  a { color: #1565c0; text-decoration: none; }
  .desc { color: #666; font-style: italic; font-size: 0.9em; margin: 2px 0 6px 0; }
  .none { color: #888; font-style: italic; }
  .note { color: #e65100; font-size: 0.85em; }
  .timing { color: #aaa; font-size: 0.8em; margin-left: 6px; }
</style></head>
<body>
"""

    def _render_html(self, sections):
        parts = [self._STYLE]

        for section in sections:
            title = html.escape(section.title)
            desc = html.escape(section.description)
            run_href = f"#run:{section.report_id}"

            if section.not_run:
                parts.append(
                    f'<h3>▶ {title}</h3>'
                    f'<p class="none">Not run — click Run All Reports or '
                    f'<a href="{run_href}">↺ re-run</a></p>'
                    f'<p class="desc">{desc}</p>'
                )
            elif not section.findings:
                parts.append(
                    f'<h3>▶ {title} <span class="none">(none found)</span>'
                    f' <a href="{run_href}">↺</a>'
                    f' <span class="timing">{section.run_time_ms:.0f}ms</span></h3>'
                    f'<p class="desc">{desc}</p>'
                )
            else:
                count = len(section.findings)
                parts.append(
                    f'<h3>▶ {title} <small>({count} found)</small>'
                    f' <a href="{run_href}">↺</a>'
                    f' <span class="timing">{section.run_time_ms:.0f}ms</span></h3>'
                    f'<p class="desc">{desc}</p>'
                    f'<ul>'
                )
                for finding in section.findings:
                    parts.append(self._render_finding(finding))
                parts.append('</ul>')

        parts.append('</body></html>')
        return '\n'.join(parts)

    def _render_finding(self, finding):
        if not finding.terms:
            return ''

        esc = html.escape

        # Bold term names joined with " / "
        bold_terms = ' / '.join(f'<b>{esc(t)}</b>' for t in finding.terms)

        note_html = ''
        if finding.note:
            note_html = f' <span class="note">({esc(finding.note)})</span>'

        lines = [f'{bold_terms}{note_html}']

        for term in finding.terms:
            refs = finding.pages_by_term.get(term, [])
            if not refs:
                # unused include term — show as "not found in PDF"
                lines.append(
                    f'<br>&nbsp;&nbsp;<b>{esc(term)}</b>'
                    f' <span class="note">(not found in PDF)</span>'
                )
                continue

            page_links = []
            for ref in refs[:self.MAX_LINKS]:
                label_text = format_page_ref(ref.page_idx, ref.page_label)
                href = f'#{ref.page_idx}|{term}'
                page_links.append(f'<a href="{href}">{esc(label_text)}</a>')

            pages_html = ', '.join(page_links)
            remaining = len(refs) - self.MAX_LINKS
            if remaining > 0:
                pages_html += f' <span class="note">…and {remaining} more</span>'

            lines.append(f'<br>&nbsp;&nbsp;{esc(term)}: {pages_html}')

        return f'<li>{"".join(lines)}</li>'
