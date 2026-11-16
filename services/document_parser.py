from io import BytesIO
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedPage:
    text: str
    page_number: int | None


def parse_document(filename: str, content: bytes) -> list[ParsedPage]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in {"pdf", "txt", "md"}:
        raise DocumentParseError("Only PDF, TXT, and MD files are supported.")
    if not content:
        raise DocumentParseError("The uploaded file is empty.")

    if suffix in {"txt", "md"}:
        try:
            text = content.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise DocumentParseError("Text files must use UTF-8 encoding.") from exc
        if not text:
            raise DocumentParseError("The file contains no extractable text.")
        return [ParsedPage(text=text, page_number=None)]

    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise DocumentParseError("Password-protected PDFs are not supported.")
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(ParsedPage(text=text, page_number=page_number))
    except PdfReadError as exc:
        raise DocumentParseError("The PDF file is invalid or unreadable.") from exc

    if not pages:
        raise DocumentParseError(
            "The PDF contains no extractable text. Scanned PDFs require OCR, which is not supported."
        )
    return pages


def extract_text_from_txt(content: bytes) -> str:
    pages = parse_document("document.txt", content)
    return pages[0].text


def extract_text_from_pdf(content: bytes) -> str:
    return "\n".join(
        page.text for page in parse_document("document.pdf", content)
    )