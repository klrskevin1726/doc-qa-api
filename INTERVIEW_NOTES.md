# Interview Notes: Document Q&A API

## Design walkthrough

- **API and storage:** FastAPI handles request validation and bearer-token
  authentication. SQLAlchemy persists users, documents, and chunks in
  PostgreSQL. Alembic evolves the schema. pgvector stores and compares vectors.
- **Embedding model:** `text-embedding-3-small` is used for both document and
  question embeddings. Both vectors are 1,536 dimensions; using the same model
  and dimensions makes cosine-distance comparison meaningful.
- **Chunking:** The default is 1,000 characters with 150 characters of overlap.
  This is a simple, bounded MVP choice that keeps context manageable while
  reducing the chance that a fact near a chunk boundary is split away from its
  context. These are characters, not tokens; a production system could tune
  token-based boundaries against a representative evaluation set.
- **Provenance:** Each chunk stores an index and optional PDF page number.
  Citation excerpts are made from exactly the retrieved chunk text. The model
  never chooses citation IDs, and retrieval filters on the owning user's
  document before any text enters the prompt.
- **Retrieval:** The API embeds the question, orders eligible chunks by
  pgvector cosine distance, and applies a bounded top-k. For small MVP datasets
  an exact scan is straightforward and avoids ANN-index tuning; at larger scale
  an HNSW or IVFFlat index and retrieval-quality evaluation would be reasonable.
- **Grounding:** The system message says to use only retrieved excerpts, treat
  them as untrusted data rather than instructions, and acknowledge insufficient
  evidence. Empty search results bypass generation and return an explicit
  insufficient-context answer. The model can still make mistakes, so this is a
  mitigation rather than a correctness proof.
- **Atomic ingestion:** Embeddings are generated before database writes. The
  document row and all chunks are then committed in one transaction. If the
  provider fails, no document is created; if the database write fails, the
  transaction is rolled back.
- **Dimension migration:** Existing vectors used 384 dimensions. The new
  migration adds a separate nullable 1,536-dimensional column instead of
  rewriting or deleting old vectors. Legacy chunks remain stored but are not
  eligible for current retrieval.

## Tradeoffs and limits

- Character chunks are easy to inspect but do not align exactly to model
  tokens. Chunk size/overlap should be tuned with a small retrieval benchmark.
- Top-k can return irrelevant material. The prompt asks the model to decline
  unsupported questions, but a similarity threshold or reranker should only be
  added after evaluating precision/recall on representative questions.
- All matching vectors are searched exactly. Add an ANN index after the corpus
  justifies the recall/latency tradeoff.
- OCR, file malware scanning, rate limiting, deletion auditing, TLS policy,
  and production secrets management are not implemented.
- The server does not persist conversational history; each ask is independent.

## Likely interview questions

**Why use cosine distance?** It compares vector direction and is a common
semantic-similarity measure for normalized embedding spaces. pgvector exposes
the `<=>` operator through SQLAlchemy's `cosine_distance`.

**Why overlap chunks?** A small overlap preserves local context when an
important sentence crosses a boundary. Too much overlap increases storage,
embedding cost, and duplicate retrieval.

**How do you prevent cross-user data leakage?** Every retrieval joins chunks to
their document and filters by the authenticated user's ID in the SQL query.
Document list and delete use the same ownership predicate. A regression test
checks that another user's chunk does not appear in the prompt or citations.

**How are citations kept honest?** The API creates citations from rows selected
by the authorized vector query; it does not accept model-generated document,
chunk, or page IDs. The excerpt is copied from that retrieved chunk.

**What if the document contains a prompt injection?** The prompt explicitly
labels retrieved text as untrusted evidence and instructs the model to ignore
instructions in it. Retrieval still needs robust evaluation, and prompt
injection cannot be eliminated solely by wording.

**Why generate embeddings before opening the write transaction?** Network
latency should not hold database locks. If embedding fails, there is nothing to
roll back; after embeddings succeed, document and chunks are persisted
atomically.

**What would you improve next?** Add a retrieval evaluation set, token-aware
chunking, a measured relevance threshold or reranker, async/batched provider
calls, an ANN index when data grows, and operational rate limits/metrics.

## 90-second explanation

I built a small RAG API with FastAPI, PostgreSQL, SQLAlchemy, and pgvector.
Users authenticate with short-lived JWTs and can upload PDF, text, or Markdown
documents. The service extracts text, preserves PDF page numbers, chunks the
text with overlap, calls `text-embedding-3-small`, then stores document and
chunks in one transaction. For a question, it creates an embedding with that
same model and searches by cosine distance. Crucially, retrieval joins through
the document table and filters by the authenticated owner's ID, so another
user's chunks never reach the prompt. The answer model receives a bounded
context that is explicitly marked as untrusted data and is told to decline if
the evidence is insufficient. Citations are built by the API directly from the
retrieved authorized chunks, not from source IDs invented by the model. I chose
simple character chunks and exact vector search for a clear MVP; at larger
scale I would evaluate token-aware chunking, an ANN index, and a reranker.
