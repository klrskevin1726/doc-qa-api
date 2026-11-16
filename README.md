# Document Q&A API

A small, authenticated Retrieval-Augmented Generation (RAG) API built with
FastAPI, PostgreSQL, pgvector, SQLAlchemy, Alembic, and the OpenAI API. Users
upload PDF, TXT, or Markdown documents, then ask questions grounded in their
own documents.

## Architecture

1. The API validates an authenticated upload and extracts UTF-8 text. PDFs keep
   one-based page numbers; scanned PDFs without extractable text are rejected.
2. Text is split into bounded character chunks (default 1,000 characters with
   150 characters of overlap). `text-embedding-3-small` creates 1,536-value
   vectors, which are stored alongside chunks in PostgreSQL/pgvector.
3. Questions are embedded with that same model. PostgreSQL ranks chunks by
   cosine distance, and the query is constrained by the authenticated owner's
   document IDs through the document relationship.
4. The answer model receives only a bounded set of retrieved excerpts. The
   prompt treats document text as untrusted evidence and asks the model to
   acknowledge missing evidence. Citation objects are built by the API from
   the authorized retrieved rows, not from model-generated source claims.

The earlier schema used 384-dimensional vectors. The additive migration adds
a nullable 1,536-dimensional column and provenance fields without deleting
existing chunk or vector data. Existing 384-dimensional vectors are retained
but are not used in new retrievals.

## Requirements

- Docker Desktop with the Linux container engine enabled, or Python 3.12 and a
  PostgreSQL 16 database with the pgvector extension.
- An OpenAI API key for document embedding and generated answers. Registration,
  login, health checks, and tests do not require a live OpenAI request.
- `SECRET_KEY` with at least 32 characters.

The Docker image uses Python 3.12 rather than 3.14 to target a stable,
well-supported runtime for the pinned FastAPI, SQLAlchemy, and OpenAI packages.
The repository's existing Python 3.14 virtual environment can still run the
test suite.

## Configuration

Copy the safe template only when a local `.env` does not already exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set the placeholder values locally; never commit `.env`. Use URL-safe characters
for `POSTGRES_PASSWORD`, since Compose also uses it in `DATABASE_URL`. Compose
connects the API to the `db` service and overrides `DATABASE_URL`; the
`localhost` URL in the template is for running Alembic or Uvicorn directly from
the host.

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection URL | required outside Compose |
| `POSTGRES_USER` | Compose database user | `docqa` |
| `POSTGRES_PASSWORD` | Compose database password | required |
| `POSTGRES_DB` | Compose database name | `docqa` |
| `SECRET_KEY` | HS256 JWT signing key (minimum 32 characters) | required |
| `OPENAI_API_KEY` | OpenAI credential; required for embedding/answer requests | required for RAG |
| `OPENAI_CHAT_MODEL` | Text-generation model | `gpt-4o-mini` |
| `MAX_UPLOAD_SIZE_BYTES` | Upload limit | `10485760` (10 MiB) |
| `CHUNK_SIZE` | Chunk size in characters | `1000` |
| `CHUNK_OVERLAP` | Character overlap | `150` |
| `TOP_K` | Default number of retrieved chunks (1–10) | `4` |
| `MAX_CONTEXT_CHARS` | Maximum retrieved context size | `12000` |

An unset or weak JWT key, missing OpenAI key, invalid limits, and database
connection failures return explicit configuration/readiness errors; secret
values are not logged.

## Run with Docker Compose

Start Docker Desktop first, then from the repository root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/ready
```

Compose waits for PostgreSQL, applies `alembic upgrade head`, and starts the
API. The named `pgdata` volume preserves database data when containers stop.
To apply migrations explicitly after startup:

```powershell
docker compose exec api python -m alembic upgrade head
```

To run the API from the host instead, point `DATABASE_URL` at a running local
PostgreSQL/pgvector database, install dependencies, and migrate before starting:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

Swagger UI is at `http://localhost:8000/docs`; liveness and DB readiness are
`/health` and `/ready`.

## Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | No | Register username and password (12+ characters, at most 72 UTF-8 bytes) |
| `POST` | `/auth/login` | No | OAuth2 form login; returns a bearer token |
| `GET` | `/auth/me` | Yes | Current user |
| `POST` | `/documents/upload` | Yes | Upload PDF, TXT, or MD; embed and persist atomically |
| `GET` | `/documents` | Yes | List only the current user's documents |
| `DELETE` | `/documents/{document_id}` | Yes | Delete only the current user's document |
| `POST` | `/questions/ask` | Yes | Retrieve authorized chunks and answer with citations |

### Example PowerShell demo

Register and log in (the password is entered interactively and is not included
in the command text):

```powershell
$username = "alice"
$credential = Get-Credential -UserName $username -Message "Enter a new 12+ character demo password"
$password = $credential.GetNetworkCredential().Password
$registerBody = @{ username = $username; password = $password } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/register -ContentType "application/json" -Body $registerBody
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -ContentType "application/x-www-form-urlencoded" -Body @{ username = $username; password = $password }
$token = $login.access_token
$headers = @{ Authorization = "Bearer $token" }
```

Upload the included sample and ask a question:

```powershell
curl.exe -H "Authorization: Bearer $token" -F "file=@samples\rag-demo.txt" http://localhost:8000/documents/upload
$question = @{ question = "Which embedding model and vector dimension are used?"; top_k = 4 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/questions/ask -Headers $headers -ContentType "application/json" -Body $question
```

Ask for an unsupported fact to check insufficient-evidence behavior:

```powershell
$unknown = @{ question = "What is the CTO's favorite color?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/questions/ask -Headers $headers -ContentType "application/json" -Body $unknown
```

The sample intentionally contains no answer to that second question. The model
is instructed to say it does not have enough information. A successful answer
includes an array of citations with `document_id`, `document_title`, `chunk_id`,
optional `page_number`, and a short excerpt taken from a retrieved chunk. For
TXT/MD, `page_number` is `null`.

Illustrative response shape (answer text varies by model):

```json
{
  "answer": "The project uses text-embedding-3-small with 1,536 dimensions.",
  "citations": [
    {
      "document_id": 1,
      "document_title": "rag-demo.txt",
      "chunk_id": 1,
      "page_number": null,
      "excerpt": "The project uses text-embedding-3-small to create 1536-dimensional vectors."
    }
  ]
}
```

## Tests

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q main.py config models routers services alembic tests
```

Tests use a fake database session and mocked OpenAI calls, including a
cross-user retrieval regression; they do not require Docker or spend API
credits. A live demo still requires PostgreSQL/pgvector and a valid OpenAI API
key.

## Security and limitations

- Passwords are bcrypt-hashed. JWTs use HS256, expire after 30 minutes, and
  require a configured signing key. Invalid or missing bearer tokens return
  `401`.
- Document listing, deletion, and vector retrieval are scoped to the current
  user. Upload writes a document and its chunks in one database transaction;
  embedding failure occurs before persistence.
- Upload size, file extension, empty input, text encoding, and PDF extraction
  are validated. PDF pages without text are omitted; scanned PDFs need OCR,
  which is out of scope.
- Retrieved document text is untrusted and may contain prompt injection. The
  model is instructed to ignore embedded instructions and answer only from
  evidence; citations are independently built from retrieved authorized rows.
  Generation is not guaranteed factually correct.
- Retrieval uses a full cosine-distance scan (no ANN index), appropriate for
  this MVP's expected small collection. There is no reranker, OCR, streaming,
  or per-user rate limiting. API-key usage and external API costs are controlled
  by the OpenAI account.
- The database stores extracted document text, chunks, and vectors. Protect the
  PostgreSQL volume and use TLS/managed secrets in production.
