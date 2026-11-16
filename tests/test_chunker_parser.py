from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from services.chunker import chunk_text
from services.document_parser import DocumentParseError, parse_document


def _text_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_chunker_bounds_and_overlap():
    source = "alpha beta gamma delta epsilon zeta eta theta"
    chunks = chunk_text(source, chunk_size=18, overlap=5)

    assert len(chunks) > 1
    assert all(len(chunk) <= 18 for chunk in chunks)
    assert all(
        set(chunks[index].split()) & set(chunks[index + 1].split())
        for index in range(len(chunks) - 1)
    )


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (10, -1), (10, 10)],
)
def test_chunker_rejects_invalid_bounds(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=chunk_size, overlap=overlap)


def test_text_parser_handles_utf8_markdown():
    pages = parse_document("notes.md", b"\xef\xbb\xbfRAG uses UTF-8.")

    assert len(pages) == 1
    assert pages[0].page_number is None
    assert pages[0].text == "RAG uses UTF-8."


def test_pdf_parser_preserves_page_number():
    pages = parse_document("facts.pdf", _text_pdf("Page one citation"))

    assert [(page.page_number, page.text) for page in pages] == [
        (1, "Page one citation")
    ]


def test_parser_rejects_empty_invalid_and_scanned_documents():
    with pytest.raises(DocumentParseError, match="empty"):
        parse_document("empty.txt", b"")
    with pytest.raises(DocumentParseError, match="UTF-8"):
        parse_document("invalid.txt", b"\xff")
    with pytest.raises(DocumentParseError, match="OCR"):
        parse_document("scanned.pdf", _text_pdf(""))
    with pytest.raises(DocumentParseError, match="invalid or unreadable"):
        parse_document("broken.pdf", b"not a pdf")
