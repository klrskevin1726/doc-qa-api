from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text
from pgvector.sqlalchemy import Vector

class Base(DeclarativeBase):
    pass

class User(Base):
        id: Mapped[int] = mapped_column(primary_key=True)
        __tablename__ = "users"
        username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
        hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)

class Document(Base):
        id: Mapped[int] = mapped_column(primary_key=True)
        __tablename__ = "documents"
        title: Mapped[str] = mapped_column(String(100), nullable=False)
        content: Mapped[str] = mapped_column(String, nullable=False)
        owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
        chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")

class Chunk(Base):
        id: Mapped[int] = mapped_column(primary_key=True)
        __tablename__ = "chunks"
        content: Mapped[str] = mapped_column(Text, nullable=False)
        embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
        document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
        document: Mapped["Document"] = relationship(back_populates="chunks")