import os
import secrets

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://localhost/test"
)
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from fastapi.testclient import TestClient

from main import app
from models.database import Chunk, Document, User
from routers.auth import get_current_user
from config.database import get_db


class FakeQuery:
    def __init__(self, db, entities):
        self.db = db
        self.entities = entities
        self.criteria = []
        self.limit_value = None

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def _value_for_column(self, key):
        for clause in self.criteria:
            left = getattr(clause, "left", None)
            right = getattr(clause, "right", None)
            if getattr(left, "key", None) == key and hasattr(right, "value"):
                return right.value
        return None

    def first(self):
        if self.entities == (User,):
            username = self._value_for_column("username")
            user_id = self._value_for_column("id")
            return next(
                (
                    user
                    for user in self.db.users
                    if (username is None or user.username == username)
                    and (user_id is None or user.id == user_id)
                ),
                None,
            )
        if self.entities == (Document,):
            document_id = self._value_for_column("id")
            owner_id = self._value_for_column("owner_id")
            return next(
                (
                    document
                    for document in self.db.documents
                    if document.id == document_id
                    and (owner_id is None or document.owner_id == owner_id)
                ),
                None,
            )
        return None

    def all(self):
        if self.entities == (Document,):
            owner_id = self._value_for_column("owner_id")
            documents = [
                document
                for document in self.db.documents
                if owner_id is None or document.owner_id == owner_id
            ]
            return documents[: self.limit_value]
        if self.entities == (Chunk, Document):
            owner_id = self._value_for_column("owner_id")
            rows = []
            for chunk in self.db.chunks:
                document = next(
                    (
                        document
                        for document in self.db.documents
                        if document.id == chunk.document_id
                    ),
                    None,
                )
                if document and (owner_id is None or document.owner_id == owner_id):
                    if chunk.embedding_1536 is not None:
                        rows.append((chunk, document))
            return rows[: self.limit_value]
        return []


class FakeSession:
    def __init__(self):
        self.users = []
        self.documents = []
        self.chunks = []
        self.pending = []
        self.rollback_count = 0
        self.fail_commit = False

    def query(self, *entities):
        return FakeQuery(self, entities)

    def add(self, item):
        if isinstance(item, User) and item.id is None:
            item.id = max((user.id for user in self.users), default=0) + 1
            self.users.append(item)
        elif isinstance(item, Document) and item.id is None:
            item.id = max((document.id for document in self.documents), default=0) + 1
            self.documents.append(item)
        self.pending.append(item)

    def add_all(self, items):
        for item in items:
            if item.id is None:
                item.id = max((chunk.id for chunk in self.chunks), default=0) + 1
            self.chunks.append(item)
            self.pending.append(item)

    def flush(self):
        return None

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("Simulated database commit failure.")
        self.pending.clear()

    def refresh(self, item):
        return None

    def execute(self, statement):
        if getattr(self, "fail_readiness", False):
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("Simulated database readiness failure.")
        return 1

    def delete(self, document):
        self.documents.remove(document)
        self.chunks = [
            chunk for chunk in self.chunks if chunk.document_id != document.id
        ]

    def rollback(self):
        self.rollback_count += 1
        for item in self.pending:
            if item in self.chunks:
                self.chunks.remove(item)
            if item in self.documents:
                self.documents.remove(item)
            if item in self.users:
                self.users.remove(item)
        self.pending.clear()


@pytest.fixture
def fake_db():
    return FakeSession()


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client):
    user = User(id=1, username="alice", hashed_password="unused")
    client.app.dependency_overrides[get_current_user] = lambda: user
    return client, user


@pytest.fixture
def strong_password():
    return f"P7!{secrets.token_urlsafe(24)}"
