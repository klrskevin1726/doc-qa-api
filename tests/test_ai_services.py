from types import SimpleNamespace

import pytest

from services.embeddings import (
    AIConfigurationError,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    create_embeddings,
)
from services.generation import SYSTEM_INSTRUCTIONS, generate_answer


class FakeOpenAI:
    def __init__(self, embeddings=None, answer="A grounded answer."):
        self.embedding_request = None
        self.chat_request = None
        self.embeddings = SimpleNamespace(create=self._create_embeddings)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_completion)
        )
        self._embedding_data = embeddings
        self._answer = answer

    def _create_embeddings(self, **kwargs):
        self.embedding_request = kwargs
        data = self._embedding_data or [
            SimpleNamespace(index=index, embedding=[0.25] * EMBEDDING_DIMENSIONS)
            for index, _ in enumerate(kwargs["input"])
        ]
        return SimpleNamespace(data=data)

    def _create_completion(self, **kwargs):
        self.chat_request = kwargs
        message = SimpleNamespace(content=self._answer)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )


def test_embeddings_use_same_small_model_and_1536_dimensions():
    client = FakeOpenAI()
    embeddings = create_embeddings(["question", "passage"], client=client)

    assert len(embeddings) == 2
    assert all(len(embedding) == EMBEDDING_DIMENSIONS for embedding in embeddings)
    assert client.embedding_request["model"] == EMBEDDING_MODEL
    assert client.embedding_request["dimensions"] == 1536


def test_generation_uses_untrusted_context_instructions(monkeypatch):
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    client = FakeOpenAI(answer="The answer is in the excerpt.")
    answer = generate_answer("What is stated?", "[chunk_id=4] source text", client)

    assert answer == "The answer is in the excerpt."
    assert client.chat_request["messages"][0]["content"] == SYSTEM_INSTRUCTIONS
    assert "untrusted evidence" in client.chat_request["messages"][1]["content"]
    assert "gpt-4o-mini" == client.chat_request["model"]


def test_missing_openai_key_is_reported_without_network_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(AIConfigurationError, match="OPENAI_API_KEY"):
        create_embeddings(["question"])
