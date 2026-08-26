from io import BytesIO
from pypdf import PdfReader


def extract_text_from_txt(content: bytes) -> str:
    return content.decode("utf-8")


def extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)