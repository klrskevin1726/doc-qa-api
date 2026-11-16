from openai import OpenAI
from openai import OpenAIError

from config.settings import ConfigurationError, get_openai_api_key

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 100


class AIConfigurationError(RuntimeError):
    pass


class AIServiceError(RuntimeError):
    pass


def _client() -> OpenAI:
    try:
        return OpenAI(api_key=get_openai_api_key(), timeout=30.0, max_retries=2)
    except ConfigurationError as exc:
        raise AIConfigurationError(str(exc)) from exc


def create_embeddings(texts: list[str], client: OpenAI | None = None) -> list[list[float]]:
    if not texts:
        return []

    client = client or _client()
    embeddings = []
    try:
        for offset in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[offset : offset + EMBEDDING_BATCH_SIZE]
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            data = sorted(response.data, key=lambda item: item.index)
            if len(data) != len(batch) or [
                item.index for item in data
            ] != list(range(len(batch))):
                raise AIServiceError("The embedding service returned an incomplete batch.")
            for item in data:
                if len(item.embedding) != EMBEDDING_DIMENSIONS:
                    raise AIServiceError(
                        "The embedding service returned an unexpected vector dimension."
                    )
                embeddings.append(item.embedding)
    except OpenAIError as exc:
        raise AIServiceError("The embedding service request failed.") from exc
    return embeddings
