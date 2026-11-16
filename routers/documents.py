from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config.database import get_db
from config.settings import ConfigurationError, get_int_setting
from models.database import Chunk, Document, User
from models.schemas import DocumentListItem, DocumentUploadResponse
from routers.auth import get_current_user
from services.chunker import chunk_text
from services.document_parser import DocumentParseError, parse_document
from services.embeddings import (
    AIConfigurationError,
    AIServiceError,
    create_embeddings,
)

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


def _upload_limit() -> int:
    try:
        return get_int_setting(
            "MAX_UPLOAD_SIZE_BYTES",
            default=10 * 1024 * 1024,
            minimum=1,
            maximum=50 * 1024 * 1024,
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _chunk_settings() -> tuple[int, int]:
    try:
        chunk_size = get_int_setting("CHUNK_SIZE", 1000, 100, 5000)
        overlap = get_int_setting("CHUNK_OVERLAP", 150, 0, 4999)
        if overlap >= chunk_size:
            raise ConfigurationError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        return chunk_size, overlap
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    original_filename = (
        (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    )
    suffix = PurePath(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only PDF, TXT, and MD files are allowed.",
        )
    if not original_filename or len(original_filename) > 100:
        raise HTTPException(
            status_code=400,
            detail="The filename must be between 1 and 100 characters.",
        )
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in original_filename
    ):
        raise HTTPException(
            status_code=400, detail="The filename contains invalid characters."
        )

    upload_limit = _upload_limit()
    content = file.file.read(upload_limit + 1)
    if len(content) > upload_limit:
        raise HTTPException(status_code=413, detail="The uploaded file is too large.")
    try:
        pages = parse_document(original_filename, content)
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    chunk_size, overlap = _chunk_settings()
    chunk_records = []
    for page in pages:
        for text in chunk_text(page.text, chunk_size, overlap):
            chunk_records.append(
                {"content": text, "page_number": page.page_number}
            )
    if not chunk_records:
        raise HTTPException(
            status_code=400, detail="The file contains no extractable text."
        )

    try:
        embeddings = create_embeddings([chunk["content"] for chunk in chunk_records])
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(
            status_code=502, detail="Document embeddings could not be generated."
        ) from exc

    document = Document(
        title=original_filename,
        content="\n\n".join(page.text for page in pages),
        owner_id=current_user.id,
    )
    try:
        db.add(document)
        db.flush()
        db.add_all(
            [
                Chunk(
                    content=chunk["content"],
                    embedding_1536=embedding,
                    page_number=chunk["page_number"],
                    chunk_index=index,
                    document_id=document.id,
                )
                for index, (chunk, embedding) in enumerate(
                    zip(chunk_records, embeddings, strict=True)
                )
            ]
        )
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        raise

    return DocumentUploadResponse(
        id=document.id,
        title=document.title,
        filename=document.title,
        owner_id=current_user.id,
        text_length=len(document.content),
        chunk_count=len(chunk_records),
        first_chunk_preview=chunk_records[0]["content"][:200],
    )


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentListItem]:
    documents = (
        db.query(Document)
        .filter(Document.owner_id == current_user.id)
        .order_by(Document.id)
        .all()
    )
    return [
        DocumentListItem(
            id=document.id,
            title=document.title,
            chunk_count=len(document.chunks),
        )
        for document in documents
    ]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        db.delete(document)
        db.commit()
    except Exception:
        db.rollback()
        raise
