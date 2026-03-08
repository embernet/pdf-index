# PDF Indexer

A desktop application for creating back-of-the-book style indexes from PDF files. Define keywords, search a PDF for their locations, and export the results in multiple formats. Includes automatic name detection and word cloud generation to help discover additional topics worth indexing.

## Features

### Indexing

- **Keyword Indexing** -- Define keywords and search an entire PDF for page occurrences. Consecutive pages are collapsed into ranges (e.g. "5-8" instead of "5, 6, 7, 8").
- **Name Indexing** -- Automatically detect proper nouns from mid-sentence capitalised words and multi-word names. Every occurrence (including sentence-initial) is indexed. Variations are consolidated under the longest form with surname-first formatting. Enabled by default.
- **Bold Text Indexing** -- Optionally index bold text found in the PDF as additional entries.
- **Exclude List** -- Maintain a list of words to exclude from automatic name indexing (e.g. common words that happen to be capitalised).
- **Stop Words** -- Customisable stop word list pre-populated with common English words. Stop words are filtered out of name indexing results.
- **Capitalize Entries** -- Optionally capitalise the first letter of each index entry.

### Output Formats

- **Markdown** -- Standard Markdown formatted index.
- **Plain Text** -- Simple text output.
- **HTML** -- Formatted HTML index.
- **Active Index** -- Interactive HTML with clickable page numbers that jump to the corresponding page in the PDF viewer and highlight the referenced term in orange. Selected by default.
- **Tag Cloud** -- Visual word cloud generated from the PDF text. Existing keywords are highlighted in green. Click any word to add or remove it as a keyword.
- **View Source** -- Toggle to see the raw markup of any output format.

### PDF Viewer

- **Fit-Width Rendering** -- Pages automatically scale to fill the viewer width. Responds to window resizing with debounced re-rendering.
- **Page Navigation** -- Previous/Next buttons, page slider, and a Go To page field. Scrolling past the top or bottom of a page automatically advances to the adjacent page.
- **Term Highlighting** -- All indexed terms on the current page are highlighted in yellow. When clicking a page number in the Active Index, the specific term is highlighted in orange so it stands out.
- **Click-to-Lookup** -- Click any highlighted word in the PDF to scroll the index output to that term and highlight it.
- **Add Keywords from PDF** -- Double-click a word or select a phrase and right-click to add it as a keyword.
- **Resizable Panes** -- Drag the splitter bars to make the PDF wider or narrower. Minimum widths on the side panes allow the PDF to take up most of the window.

### Workspace

- **Project Management** -- Organise work into project folders. Each project stores its PDF, keywords, exclude list, stop words, configuration, and generated output files. The last project is automatically reopened on launch.
- **Collapsible Panels** -- The Keywords, Exclude List, and Stop Words editors are collapsible. A maximum of two panels can be open at once; opening a third automatically closes the oldest.
- **Page Numbering** -- Supports logical page labels (as defined in the PDF metadata) or physical page numbering with an optional offset for front matter.
- **Help Panel** -- Click the "? Help" button to toggle this documentation in a panel on the right.
- **Autosave** -- Keywords, exclude list, stop words, and all settings are saved automatically as you type.

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. **Create or open a project** via the File menu.
2. **Import a PDF** into the project.
3. **Add keywords** in the Keywords panel (one per line), or select text in the PDF viewer to add keywords directly.
4. **Click "Create Index"** to search the PDF and generate the index.
5. **Browse the Active Index** -- click any page number to jump to that page in the PDF with the term highlighted in orange.
6. **Use name indexing** (on by default) to automatically discover proper nouns without manually adding them as keywords. Add false positives to the Exclude List.
7. **Use the Tag Cloud** to discover frequent terms and click them to toggle keywords, then re-index.

## Project Structure

```
pdf-index/
├── main.py                  # Application entry point
├── version.py               # Version number
├── controller/
│   └── main_controller.py   # Orchestrates UI, indexing, and project state
├── model/
│   ├── indexer.py            # PDF keyword search and index generation
│   ├── name_indexer.py       # Automatic proper-noun indexing
│   ├── tag_cloud.py          # Word cloud generation
│   ├── config.py             # Per-project configuration
│   └── app_config.py         # Application-wide settings (recent projects)
├── view/
│   ├── main_window.py        # Main window layout with splitter panes
│   ├── keyword_editor.py     # Keyword entry editor with sort and autosave
│   ├── exclude_editor.py     # Exclude list editor with autosave
│   ├── stopwords_editor.py   # Stop words editor with autosave
│   ├── collapsible_panel.py  # Generic collapsible panel wrapper
│   ├── pdf_viewer.py         # Built-in PDF viewer with highlighting
│   └── controls_output.py    # Index output display, format controls, tag cloud
└── requirements.txt
```

## Tech Stack

- **PyQt6** -- Desktop GUI framework
- **PyMuPDF (fitz)** -- PDF text extraction and rendering
- **wordcloud** -- Word cloud generation
- **Pillow / NumPy** -- Image processing for word cloud rendering
