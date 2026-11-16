from models.database import Chunk, Document, User
from routers.auth import get_current_user
from services.embeddings import AIServiceError
import routers.documents as documents_router
import routers.questions as questions_router


def test_auth_register_login_and_invalid_password(client, fake_db, strong_password):
    invalid = client.post(
        "/auth/register",
        json={"username": "alice", "password": "x"},
    )
    assert invalid.status_code == 422

    registered = client.post(
        "/auth/register",
        json={"username": "alice", "password": strong_password},
    )
    assert registered.status_code == 200
    assert fake_db.users[0].hashed_password != strong_password

    login = client.post(
        "/auth/login",
        data={"username": "alice", "password": strong_password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "username"
    ] == "alice"

    bad_login = client.post(
        "/auth/login",
        data={"username": "alice", "password": strong_password[:-2]},
    )
    assert bad_login.status_code == 401
    assert client.get(
        "/auth/me", headers={"Authorization": "Bearer invalid"}
    ).status_code == 401


def test_missing_jwt_secret_is_reported(client, fake_db, monkeypatch, strong_password):
    client.post(
        "/auth/register",
        json={"username": "alice", "password": strong_password},
    )
    monkeypatch.setenv("SECRET_KEY", "short")

    response = client.post(
        "/auth/login",
        data={"username": "alice", "password": strong_password},
    )

    assert response.status_code == 503
    assert "SECRET_KEY" in response.json()["detail"]


def test_health_and_database_readiness(authenticated_client, fake_db):
    client, _ = authenticated_client
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}

    fake_db.fail_readiness = True
    response = client.get("/ready")
    assert response.status_code == 503


def test_upload_persists_embeddings_and_chunk_metadata(
    authenticated_client, fake_db, monkeypatch
):
    client, user = authenticated_client
    monkeypatch.setattr(
        documents_router,
        "create_embeddings",
        lambda texts: [[0.1] * 1536 for _ in texts],
    )

    response = client.post(
        "/documents/upload",
        files={"file": (r"C:\private\facts.txt", b"pgvector stores vectors.", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "facts.txt"
    assert len(fake_db.documents) == 1
    assert fake_db.documents[0].owner_id == user.id
    assert len(fake_db.chunks) == 1
    assert fake_db.chunks[0].embedding_1536 == [0.1] * 1536
    assert fake_db.chunks[0].page_number is None
    assert fake_db.chunks[0].chunk_index == 0


def test_upload_validation_and_provider_failure_leave_no_documents(
    authenticated_client, fake_db, monkeypatch
):
    client, _ = authenticated_client
    assert client.post(
        "/documents/upload", files={"file": ("bad.exe", b"x", "application/octet-stream")}
    ).status_code == 400
    assert client.post(
        "/documents/upload", files={"file": ("empty.txt", b"", "text/plain")}
    ).status_code == 400

    monkeypatch.setattr(
        documents_router,
        "create_embeddings",
        lambda texts: (_ for _ in ()).throw(AIServiceError("provider unavailable")),
    )
    failed = client.post(
        "/documents/upload",
        files={"file": ("facts.txt", b"some text", "text/plain")},
    )
    assert failed.status_code == 502
    assert fake_db.documents == []
    assert fake_db.chunks == []


def test_upload_size_limit_and_database_rollback(
    authenticated_client, fake_db, monkeypatch
):
    client, _ = authenticated_client
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "5")
    assert client.post(
        "/documents/upload",
        files={"file": ("facts.txt", b"more than five bytes", "text/plain")},
    ).status_code == 413
    monkeypatch.delenv("MAX_UPLOAD_SIZE_BYTES")
    monkeypatch.setattr(
        documents_router,
        "create_embeddings",
        lambda texts: [[0.1] * 1536 for _ in texts],
    )
    fake_db.fail_commit = True
    from fastapi.testclient import TestClient

    with TestClient(client.app, raise_server_exceptions=False) as no_raise_client:
        failed = no_raise_client.post(
            "/documents/upload",
            files={"file": ("facts.txt", b"transaction test", "text/plain")},
        )
    assert failed.status_code == 500
    assert fake_db.rollback_count == 1
    assert fake_db.documents == []
    assert fake_db.chunks == []


def test_documents_are_scoped_to_owner(authenticated_client, fake_db):
    client, owner = authenticated_client
    other_user = User(id=2, username="bob", hashed_password="unused")
    own_document = Document(id=1, title="own.txt", content="", owner_id=owner.id)
    other_document = Document(id=2, title="other.txt", content="", owner_id=other_user.id)
    fake_db.documents.extend([own_document, other_document])

    listed = client.get("/documents")
    assert [document["title"] for document in listed.json()] == ["own.txt"]
    assert client.delete("/documents/2").status_code == 404
    assert client.delete("/documents/1").status_code == 204
    assert [document.id for document in fake_db.documents] == [2]


def test_question_retrieval_cannot_return_another_users_chunks(
    authenticated_client, fake_db, monkeypatch
):
    client, owner = authenticated_client
    other_user = User(id=2, username="bob", hashed_password="unused")
    own_document = Document(id=1, title="alice.txt", content="", owner_id=owner.id)
    other_document = Document(id=2, title="bob.txt", content="", owner_id=other_user.id)
    fake_db.documents.extend([own_document, other_document])
    fake_db.chunks.extend(
        [
            Chunk(
                id=11, content="The blue sample device has a 10-day warranty.",
                embedding_1536=[0.1] * 1536, document_id=own_document.id,
            ),
            Chunk(
                id=22, content="The second test fixture has a separate example.",
                embedding_1536=[0.2] * 1536, document_id=other_document.id,
            ),
        ]
    )
    monkeypatch.setattr(questions_router, "create_embeddings", lambda texts: [[0.1] * 1536])
    captured = {}

    def answer(question, context):
        captured["context"] = context
        return "The blue sample device has a 10-day warranty."

    monkeypatch.setattr(questions_router, "generate_answer", answer)
    response = client.post("/questions/ask", json={"question": "How many vacation days?"})

    assert response.status_code == 200
    assert "second test fixture" not in captured["context"]
    assert [citation["chunk_id"] for citation in response.json()["citations"]] == [11]


def test_empty_search_returns_insufficient_context_without_generation(
    authenticated_client, monkeypatch
):
    client, _ = authenticated_client
    monkeypatch.setattr(questions_router, "create_embeddings", lambda texts: [[0.1] * 1536])
    monkeypatch.setattr(
        questions_router,
        "generate_answer",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not generate")),
    )

    response = client.post("/questions/ask", json={"question": "An unknown fact?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": questions_router.INSUFFICIENT_CONTEXT_ANSWER,
        "citations": [],
    }


def test_request_validation_and_missing_credentials(
    authenticated_client, fake_db, monkeypatch
):
    client, _ = authenticated_client
    assert client.post("/questions/ask", json={"question": "  "}).status_code == 422
    assert client.post(
        "/questions/ask", json={"question": "valid question", "top_k": 11}
    ).status_code == 422

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/questions/ask", json={"question": "valid question"})
    assert response.status_code == 503
    assert fake_db.chunks == []


def test_mocked_register_upload_ask_flow_and_insufficient_evidence(
    client, fake_db, monkeypatch, strong_password
):
    monkeypatch.setattr(
        documents_router,
        "create_embeddings",
        lambda texts: [[0.1] * 1536 for _ in texts],
    )
    monkeypatch.setattr(
        questions_router,
        "create_embeddings",
        lambda texts: [[0.1] * 1536 for _ in texts],
    )

    register = client.post(
        "/auth/register",
        json={"username": "alice", "password": strong_password},
    )
    assert register.status_code == 200
    login = client.post(
        "/auth/login",
        data={"username": "alice", "password": strong_password},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    upload = client.post(
        "/documents/upload",
        headers=headers,
        files={
            "file": (
                "facts.txt",
                b"The project uses pgvector with 1536-dimensional embeddings.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201

    def mock_answer(question, context):
        if "favorite color" in question:
            return questions_router.INSUFFICIENT_CONTEXT_ANSWER
        return "The project uses 1536-dimensional embeddings."

    monkeypatch.setattr(questions_router, "generate_answer", mock_answer)
    grounded = client.post(
        "/questions/ask",
        headers=headers,
        json={"question": "What embedding dimension does it use?"},
    )
    unknown = client.post(
        "/questions/ask",
        headers=headers,
        json={"question": "What is the CTO's favorite color?"},
    )

    assert grounded.status_code == 200
    assert grounded.json()["answer"] == "The project uses 1536-dimensional embeddings."
    assert grounded.json()["citations"][0]["document_title"] == "facts.txt"
    assert unknown.status_code == 200
    assert unknown.json()["answer"] == questions_router.INSUFFICIENT_CONTEXT_ANSWER
