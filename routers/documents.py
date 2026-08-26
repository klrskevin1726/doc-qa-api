from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from models.database import Document, User
from routers.auth import get_current_user
from services.document_parser import extract_text_from_pdf, extract_text_from_txt
from services.chunker import chunk_text


router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    filename = (file.filename or "").lower()

    if not any(filename.endswith(extension) for extension in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only PDF, TXT, and MD files are allowed."
        )

    content = await file.read()

    if filename.endswith(".pdf"):
        text = extract_text_from_pdf(content)
    else:
        text = extract_text_from_txt(content)

    document = Document(
        title=file.filename,
        content=text,
        owner_id=current_user.id
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    chunks = chunk_text(text)

    return {
        "id": document.id,
        "filename": file.filename,
        "text_length": len(text),
        "owner_id": current_user.id,
        "chunk_count": len(chunks),
        "first_chunk_preview": chunks[0][:200] if chunks else None
    }