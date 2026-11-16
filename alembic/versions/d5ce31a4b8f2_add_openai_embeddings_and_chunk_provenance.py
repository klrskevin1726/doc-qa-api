"""Add 1536-dimensional embeddings and chunk provenance.

Revision ID: d5ce31a4b8f2
Revises: 742a35d258ac
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa


revision: str = "d5ce31a4b8f2"
down_revision: Union[str, Sequence[str], None] = "742a35d258ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "embedding_1536",
            pgvector.sqlalchemy.vector.VECTOR(dim=1536),
            nullable=True,
        ),
    )
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=384),
        nullable=True,
    )
    op.add_column("chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("chunk_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "chunk_index")
    op.drop_column("chunks", "page_number")
    op.drop_column("chunks", "embedding_1536")
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=384),
        nullable=False,
    )
