"""Integration tests for the PyMuPDF-touching helpers in
model/web_bundle.py. Uses a small in-memory PDF rather than the bundled
test.pdf so the test stays hermetic and fast."""
import os
import fitz  # PyMuPDF

from model.web_bundle import collect_page_data, render_page_image


def _make_test_pdf(path):
    """Two-page PDF with the text 'Mozart' on page 1 and 'Beethoven'
    on page 2."""
    doc = fitz.open()
    p1 = doc.new_page(width=200, height=300)
    p1.insert_text((20, 50), "Mozart", fontsize=14)
    p2 = doc.new_page(width=200, height=300)
    p2.insert_text((20, 50), "Beethoven", fontsize=14)
    doc.save(path)
    doc.close()


def test_collect_page_data_labels_and_dims(tmp_path):
    pdf_path = str(tmp_path / "tiny.pdf")
    _make_test_pdf(pdf_path)
    raw_results = {
        "Mozart": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    labels, dims, highlights = collect_page_data(
        pdf_path, raw_results,
        strategy="physical", offset=0, index_front_matter=False,
    )
    assert labels == ["1", "2"]
    assert dims == [(200, 300), (200, 300)]
    # Mozart should be matched on page 0
    page0_hls = highlights.get(0, [])
    assert any(h["term_key"] == "mozart" for h in page0_hls)
    rect_pct = next(h["rect_pct"] for h in page0_hls if h["term_key"] == "mozart")
    assert all(0 <= v <= 100 for v in rect_pct)
    assert rect_pct[2] > 0


def test_collect_page_data_inverted_name(tmp_path):
    """Index entry 'Smith, John' should still match 'John Smith' in PDF."""
    pdf_path = str(tmp_path / "name.pdf")
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 50), "John Smith", fontsize=14)
    doc.save(pdf_path)
    doc.close()

    raw_results = {
        "Smith, John": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    labels, dims, highlights = collect_page_data(
        pdf_path, raw_results,
        strategy="physical", offset=0, index_front_matter=False,
    )
    assert any(h["term_key"] == "smith, john" for h in highlights.get(0, []))


def test_render_page_image_writes_png(tmp_path):
    pdf_path = str(tmp_path / "tiny.pdf")
    _make_test_pdf(pdf_path)
    out_path = str(tmp_path / "page-0001.png")
    render_page_image(pdf_path, 0, out_path, zoom=1.5)
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    with open(out_path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
