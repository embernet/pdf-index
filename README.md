# PDF Indexer

A desktop application for creating back-of-the-book style indexes from PDF files. Define keywords, search a PDF for their locations, and export the results in multiple formats. Includes word cloud generation to help discover additional topics worth indexing.

## Features

- **Keyword Indexing** -- Define keywords and search an entire PDF for page occurrences. Consecutive pages are collapsed into ranges (e.g. "5-8" instead of "5, 6, 7, 8").
- **Word Cloud** -- Generate a visual word cloud from the PDF text. Existing keywords are highlighted in green. Click any word in the cloud to add or remove it as a keyword.
- **Multiple Output Formats** -- Export the index as Markdown, plain text, HTML, or an interactive HTML file with clickable links that jump to the corresponding PDF page.
- **Page Numbering** -- Supports logical page labels (as defined in the PDF) or physical page numbering with an optional offset for front matter.
- **PDF Viewer** -- Built-in viewer with text selection so you can highlight text and add it as a keyword directly.
- **Project Management** -- Organize work into project folders. Each project stores its PDF, keywords, configuration, and generated output files.

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
3. **Add keywords** in the left pane (one per line), or select text in the PDF viewer to add keywords directly.
4. **Click "Create Index"** to search the PDF and generate the index.
5. **Switch output formats** using the controls on the right to view Markdown, text, HTML, or word cloud output.
6. **Use the word cloud** to discover frequent terms and click them to add new keywords, then re-index.

## Project Structure

```
pdf-index/
├── main.py                  # Application entry point
├── controller/
│   └── main_controller.py   # Orchestrates UI, indexing, and project state
├── model/
│   ├── indexer.py            # PDF search and index generation
│   ├── tag_cloud.py          # Word cloud generation
│   ├── config.py             # Per-project configuration
│   └── app_config.py         # Application-wide settings
├── view/
│   ├── main_window.py        # Main three-pane window layout
│   ├── keyword_editor.py     # Keyword entry editor
│   ├── pdf_viewer.py         # Built-in PDF viewer
│   └── controls_output.py    # Output display and format controls
└── requirements.txt
```

## Tech Stack

- **PyQt6** -- Desktop GUI framework
- **PyMuPDF (fitz)** -- PDF text extraction
- **wordcloud** -- Word cloud generation
- **Pillow / NumPy** -- Image processing for word cloud rendering
