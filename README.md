# PDF Indexer

A desktop application for creating back-of-the-book style indexes from PDF files. Define keywords, search a PDF for their locations, and export the results in multiple formats. Includes automatic name detection and word cloud generation to help discover additional topics worth indexing.

See [HELP.md](HELP.md) for detailed feature documentation (also available via the "? Help" button in the app).

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

## Project Structure

```
pdf-index/
├── main.py                  # Application entry point
├── version.py               # Version number
├── HELP.md                  # User-facing feature documentation
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
