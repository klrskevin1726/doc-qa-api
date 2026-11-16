from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config.database import get_db
from config.settings import ConfigurationError, get_int_setting
from models.database import Chunk, Document, User
from models.schemas import AskRequest, AskResponse, Citation
from routers.auth import get_current_user
from services.embeddings import (
    AIConfigurationError,
    AIServiceError,
    create_embeddings,
)
from services.generation import generate_answer

router = APIRouter(prefix="/questions", tags=["questions"])
INSUFFICIENT_CONTEXT_ANSWER = (
    "I don't have enough information in your documents to answer that."
)


def _build_context(
    rows: list[tuple[Chunk, Document]], max_chars: int
) -> tuple[str, list[Citation]]:
    context_parts = []
    citations = []
    used_chars = 0
    for chunk, document in rows:
        page = f", page={chunk.page_number}" if chunk.page_number is not None else ""
        header = (
            f"[document_id={document.id}, title={document.title!r}, "
            f"chunk_id={chunk.id}{page}]\n"
        )
        available = max_chars - used_chars - len(header)
        if available <= 0:
            break
        excerpt = chunk.content.strip()[:available]
        if not excerpt:
            continue
        context_parts.append(header + excerpt)
        citations.append(
            Citation(
                document_id=document.id,
                document_title=document.title,
                chunk_id=chunk.id,
                page_number=chunk.page_number,
                excerpt=excerpt[:300],
            )
        )
        used_chars += len(header) + len(excerpt) + 1
    return "\n".join(context_parts), citations


@router.post("/ask", response_model=AskResponse)
def ask_question(
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    try:
        top_k = request.top_k or get_int_setting("TOP_K", 4, 1, 10)
        max_context_chars = get_int_setting(
            "MAX_CONTEXT_CHARS", 12000, 1000, 50000
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        query_embedding = create_embeddings([request.question])[0]
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(
            status_code=502, detail="Question embedding could not be generated."
        ) from exc

    distance = Chunk.embedding_1536.cosine_distance(query_embedding)
    rows = (
        db.query(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .filter(
            Document.owner_id == current_user.id,
            Chunk.embedding_1536.is_not(None),
        )
        .order_by(distance)
        .limit(top_k)
        .all()
    )
    if not rows:
        return AskResponse(answer=INSUFFICIENT_CONTEXT_ANSWER, citations=[])

    context, citations = _build_context(rows, max_context_chars)
    if not context:
        return AskResponse(answer=INSUFFICIENT_CONTEXT_ANSWER, citations=[])
    try:
        answer = generate_answer(request.question, context)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(
            status_code=502, detail="An answer could not be generated."
        ) from exc
    return AskResponse(answer=answer, citations=citations)
