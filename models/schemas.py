from pydantic import BaseModel, Field, field_validator


class StatusResponse(BaseModel):
    status: str


class DocumentUploadResponse(BaseModel):
    id: int
    title: str
    filename: str
    owner_id: int
    text_length: int
    chunk_count: int
    first_chunk_preview: str | None


class DocumentListItem(BaseModel):
    id: int
    title: str
    chunk_count: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("Question cannot be blank.")
        return question


class Citation(BaseModel):
    document_id: int
    document_title: str
    chunk_id: int
    page_number: int | None
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]