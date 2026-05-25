"""End-to-end test for the bundle orchestrator. Generates a tiny PDF,
runs the synchronous entry point, and asserts the expected files and
content end up on disk."""
import json
import os
import time

import fitz

from model.web_bundle import generate_bundle_sync


def _tiny_pdf(path):
    doc = fitz.open()
    p1 = doc.new_page(width=200, height=300)
    p1.insert_text((20, 50), "Mozart", fontsize=14)
    p2 = doc.new_page(width=200, height=300)
    p2.insert_text((20, 50), "Beethoven", fontsize=14)
    doc.save(path)
    doc.close()


def test_generate_bundle_writes_html_and_images(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    raw_results = {
        "Mozart": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
        "Beethoven": [(1, "2", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    out_dir = str(tmp_path / "web")
    generate_bundle_sync(
        pdf_path=pdf,
        raw_results=raw_results,
        out_dir=out_dir,
        strategy="physical",
        offset=0,
        index_front_matter=False,
        capitalize_keys=False,
    )

    assert os.path.exists(os.path.join(out_dir, "index.html"))
    assert os.path.exists(os.path.join(out_dir, "images", "page-0001.png"))
    assert os.path.exists(os.path.join(out_dir, "images", "page-0002.png"))
    assert os.path.exists(os.path.join(out_dir, ".cache.json"))

    with open(os.path.join(out_dir, "index.html"), encoding="utf-8") as f:
        html_str = f.read()
    assert "Mozart" in html_str
    assert "Beethoven" in html_str


def test_generate_bundle_skips_image_regen_when_cache_matches(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    raw_results = {}
    out_dir = str(tmp_path / "web")

    generate_bundle_sync(pdf, raw_results, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)

    img = os.path.join(out_dir, "images", "page-0001.png")
    first_mtime = os.path.getmtime(img)

    time.sleep(0.05)
    generate_bundle_sync(pdf, raw_results, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)
    assert os.path.getmtime(img) == first_mtime


def test_generate_bundle_regenerates_when_pdf_changes(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    out_dir = str(tmp_path / "web")
    generate_bundle_sync(pdf, {}, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)
    img = os.path.join(out_dir, "images", "page-0001.png")
    first_mtime = os.path.getmtime(img)

    time.sleep(0.05)
    new_time = first_mtime + 10
    os.utime(pdf, (new_time, new_time))

    generate_bundle_sync(pdf, {}, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)
    assert os.path.getmtime(img) != first_mtime


def test_generate_bundle_handles_corrupt_cache(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    out_dir = str(tmp_path / "web")
    os.makedirs(out_dir)
    with open(os.path.join(out_dir, ".cache.json"), "w") as f:
        f.write("{not valid json")

    generate_bundle_sync(pdf, {}, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)

    with open(os.path.join(out_dir, ".cache.json")) as f:
        data = json.load(f)
    assert "pdf_mtime" in data
    assert data["page_count"] == 2
