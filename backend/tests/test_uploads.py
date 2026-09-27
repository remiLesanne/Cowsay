import asyncio
import io
import zipfile

import pytest
from fastapi import HTTPException
from pypdf import PdfWriter

import main
from pdf_extract import InvalidPdfError, extract_pdf_text


def _zip(entries: dict[str, bytes]) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def test_zip_keeps_source_files_and_skips_ignored_directories(tmp_path):
    archive = _zip({"app.py": b"print(1)", "notes.txt": b"x", "node_modules/lib.js": b"x"})
    assert main._write_zip_to_project(archive, tmp_path) == ["app.py"]
    assert not (tmp_path / "node_modules").exists()


def test_zip_path_traversal_is_rejected(tmp_path):
    with pytest.raises(HTTPException) as error:
        main._write_zip_to_project(_zip({"../evil.py": b"x"}), tmp_path)
    assert error.value.status_code == 400


def test_zip_file_limit_counts_non_source_files(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "MAX_ARCHIVE_FILES", 3)
    archive = _zip({f"data/{index}.txt": b"x" for index in range(5)})
    with pytest.raises(HTTPException) as error:
        main._write_zip_to_project(archive, tmp_path)
    assert error.value.status_code == 413


def test_code_only_fingerprint_is_unchanged_by_pdf_support():
    assert main._combined_fingerprint("abc", b"") == "abc"
    assert main._combined_fingerprint("abc", b"%PDF") != main._combined_fingerprint("", b"%PDF")


def test_concurrent_checks_beyond_the_limit_are_turned_away(monkeypatch):
    async def scenario():
        monkeypatch.setattr(main, "_check_slots", asyncio.Semaphore(1))
        async with main._check_slot():
            with pytest.raises(HTTPException) as error:
                async with main._check_slot():
                    pass
            assert error.value.status_code == 503
        async with main._check_slot():  # released once the first check is done
            pass

    asyncio.run(scenario())


def test_pdf_without_text_layer_reports_no_readable_page():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    extracted = extract_pdf_text(buffer.getvalue(), "scan.pdf")
    assert (extracted.pages_with_text, extracted.total_pages, extracted.text) == (0, 1, "")


def test_non_pdf_bytes_are_rejected():
    with pytest.raises(InvalidPdfError):
        extract_pdf_text(b"not a pdf", "fake.pdf")
