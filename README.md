# CSVLab Backend API ⚙️

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?style=flat&logo=python)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?style=flat&logo=postgresql)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red?style=flat&logo=sqlalchemy)](https://www.sqlalchemy.org/)
[![pytest](https://img.shields.io/badge/pytest-29%20passed-brightgreen?style=flat&logo=pytest)](https://docs.pytest.org/)
[![uv](https://img.shields.io/badge/uv-fast%20python-purple?style=flat)](https://github.com/astral-sh/uv)

The backend service for **CSVLab**, a production-ready asynchronous REST API. Learners upload messy CSV files up to 10MB, get automated data-quality reports (missing values, duplicate rows, inferred data types, column distributions), run sandboxed read-only SQL queries with AST-level safety guards, and receive privacy-preserving exploratory questions powered by Groq LLMs.

---

## 📁 Directory Structure

```text
backend/
├── alembic/                       # Database migration scripts
│   ├── versions/                  # Revision versions (initial schema)
│   ├── env.py                     # Alembic migration environment
│   └── script.py.mako             # Revision template
├── app/                           # Core FastAPI application package
│   ├── api/v1/                    # API v1 route handlers
│   │   ├── auth.py                # Registration, login, JWT refresh
│   │   ├── datasets.py            # Upload, list, status, profile, delete
│   │   ├── queries.py             # Sandboxed SQL query runner, save, list, delete, export
│   │   ├── shares.py              # Mentor share link generation & unauthenticated view
│   │   └── suggestions.py         # AI question generation (Groq LLM / heuristic)
│   ├── core/                      # Cross-cutting security & dependencies
│   │   ├── dependencies.py        # Database session & current user dependencies
│   │   └── security.py            # Password hashing (bcrypt) & JWT token handling
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── dataset.py             # Dataset entity & processing status
│   │   ├── query.py               # Saved query entity
│   │   ├── share.py               # Share link entity & tokens
│   │   └── user.py                # User entity
│   ├── schemas/                   # Pydantic validation & serialization schemas
│   │   ├── auth.py                # Token, user register & login schemas
│   │   ├── dataset.py             # Dataset detail, summary, and profile schemas
│   │   ├── query.py               # SQL execution request/response, save query schemas
│   │   ├── share.py               # Share link create and public response schemas
│   │   └── suggestion.py          # AI suggested questions schemas
│   ├── services/                  # Business logic services
│   │   ├── ai_suggestions.py      # Groq LLM caller with metadata-only privacy guard
│   │   ├── data_loader.py         # Asynchronous table creation & user schema loading
│   │   ├── profiler.py            # Pandas data-quality profiling engine
│   │   └── query_runner.py        # AST SQL validator, timeout & sandboxed executor
│   ├── config.py                  # Pydantic BaseSettings environment config
│   ├── database.py                # SQLAlchemy engine, sessionmaker, and Base
│   └── main.py                    # App entrypoint, middleware, exception handlers, routes
├── tests/                         # Pytest test suite (29 tests)
│   ├── conftest.py                # Test harness, SQLite isolated test DB fixtures
│   ├── test_ai_suggestions.py     # AI suggestions & privacy verification tests
│   ├── test_auth.py               # User registration, JWT login, token refresh tests
│   ├── test_datasets.py           # Datasets CRUD & pagination tests
│   ├── test_export.py             # CSV export tests
│   ├── test_isolation.py          # Multi-tenant user data isolation tests
│   ├── test_profiling.py          # Pandas data quality profiling tests
│   ├── test_query_safety.py       # SQL sandbox AST validation & safety tests
│   ├── test_sharing.py            # Mentor read-only share link tests
│   └── test_upload.py             # 202 Accepted upload contract & size validation tests
├── alembic.ini                    # Alembic configuration
├── demo.py                        # 12-step interactive terminal walkthrough script
├── Dockerfile                     # Container build file for backend
├── main.py                        # Uvicorn runner script
├── pyproject.toml                 # uv project configuration and dependencies
├── pytest.ini                     # Pytest runner settings
├── sample_sales.csv               # Sample test CSV file
├── uv.lock                        # Dependency lockfile
└── .env.example                   # Environment configuration template
```

---

## 🚀 Key Features & Capabilities

- **🔐 Stateless JWT Authentication**:
  - Passwords salted and hashed with `bcrypt`.
  - Issues 30-minute access tokens and 7-day refresh tokens.
  - Automatic token expiration and revocation handling.

- **⚡ Asynchronous CSV Upload (`202 Accepted`)**:
  - Immediately returns HTTP `202 Accepted` with a `dataset_id` to prevent client HTTP 504 timeouts.
  - Enforces a 10MB maximum file size limit.
  - Background task triggers data-quality profiling and loads records into the database.

- **📊 Pandas Data-Quality Profiler**:
  - Detects row and column counts, exact duplicate rows, and per-column missing/null percentages.
  - Infers clean data types (`integer`, `float`, `datetime`, `string`, `boolean`).
  - Calculates summary statistics (min, max, mean, std, quantiles for numeric columns; top frequent values for categorical columns).

- **🛡️ Sandboxed Read-Only SQL Engine**:
  - **AST & Keyword Verification**: Queries parsed with `sqlparse`. Strictly allows single `SELECT` statements; instantly rejects `DROP`, `ALTER`, `UPDATE`, `DELETE`, `INSERT`, `CREATE`, `TRUNCATE`, and chained statements.
  - **Schema Isolation**: Each user queries their own private schema (`user_{id}`).
  - **Internal Table Protection**: `search_path` excludes the public schema to prevent reading application tables (`users`, `datasets`).
  - **Resource Guards**: Maximum execution time capped at **5 seconds** and output truncated to **1,000 rows**.

- **🤖 Privacy-Preserving AI Suggestions (Groq LLM)**:
  - Generates 5 tailored exploration questions with starter SQL queries and pedagogical explanations.
  - **Strict Privacy Guarantee**: Sends *only* high-level metadata (column names, types, summary statistics) to the LLM. **Zero raw user records are ever exposed**.
  - Built-in heuristic rule engine acts as an instant fallback when Groq API keys are not supplied.

- **💾 Saved Queries, CSV Export & Mentor Sharing**:
  - Save, retrieve, and delete favorite queries.
  - Export query results directly to downloadable CSV files.
  - Create secure, unguessable read-only share links for mentors and peers without requiring them to log in.

---

## 🛠️ Setup & Installation

### 1. Prerequisites
- Python 3.12+ (or 3.14)
- [`uv`](https://github.com/astral-sh/uv) (recommended for 10x-100x faster package installations)

### 2. Environment Configuration
Copy the sample environment file to `.env`:
```bash
cp .env.example .env
```

Key environment options in `.env`:
```env
# Database (defaults to local SQLite if PostgreSQL is not running)
DATABASE_URL=sqlite:///./csvlab.db
# For PostgreSQL: postgresql+psycopg://postgres:postgres@localhost:5432/csvlab

# Security & JWT
SECRET_KEY=csvlab-super-secret-development-key-32bytes-minimum
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Upload & Query Constraints
MAX_UPLOAD_SIZE_BYTES=10485760  # 10 MB
QUERY_TIMEOUT_SECONDS=5
MAX_QUERY_ROWS=1000

# Optional: Groq AI Suggestions (falls back to heuristic engine if empty)
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
```

### 3. Install Dependencies
Using `uv`:
```bash
uv sync
```
*(On Windows systems on cloud storage folders like OneDrive, use `uv sync --link-mode=copy`)*

### 4. Run Database Migrations
Initialize the database schema:
```bash
uv run alembic upgrade head
```

### 5. Start the API Server
```bash
uv run uvicorn app.main:app --reload --port 8000
```

- **Swagger UI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs) (Browsing to `http://localhost:8000` automatically redirects here)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **API Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

## 📋 API Endpoints Reference

All endpoints are versioned under `/api/v1/`:

| Module | Method | Path | Description | Authentication |
|---|---|---|---|---|
| **Auth** | `POST` | `/auth/register` | Register new account (`email`, `password`) | None |
| | `POST` | `/auth/login` | Login, get access & refresh JWT tokens | None |
| | `POST` | `/auth/refresh` | Exchange refresh token for new access token | None |
| **Datasets** | `POST` | `/datasets/` | Upload CSV (up to 10MB), returns `202 Accepted` | Bearer JWT |
| | `GET` | `/datasets/` | List user's uploaded datasets (paginated) | Bearer JWT |
| | `GET` | `/datasets/{id}/` | Poll dataset status (`processing`, `ready`, `failed`) | Bearer JWT |
| | `GET` | `/datasets/{id}/profile/` | Fetch data-quality profile (nulls, types, stats) | Bearer JWT |
| | `DELETE`| `/datasets/{id}/` | Delete dataset and drop backing database table | Bearer JWT |
| **Queries** | `POST` | `/datasets/{id}/query/` | Execute sandboxed read-only SQL query | Bearer JWT |
| | `POST` | `/datasets/{id}/queries/` | Save a query with title and SQL text | Bearer JWT |
| | `GET` | `/datasets/{id}/queries/` | List saved queries for a dataset | Bearer JWT |
| | `GET` | `/queries/{id}/` | Retrieve saved query details | Bearer JWT |
| | `PUT` | `/queries/{id}/` | Update saved query title or SQL | Bearer JWT |
| | `DELETE`| `/queries/{id}/` | Delete a saved query | Bearer JWT |
| | `GET` | `/datasets/{id}/export/` | Stream query results as a CSV file | Bearer JWT |
| **AI** | `POST` | `/datasets/{id}/suggestions/` | Get 5 AI-recommended exploration questions | Bearer JWT |
| **Sharing** | `POST` | `/datasets/{id}/share/` | Generate a read-only share token | Bearer JWT |
| | `DELETE`| `/shares/{token}/` | Revoke an existing share token | Bearer JWT |
| | `GET` | `/shared/{token}/` | Unauthenticated read-only view for mentors | Public |

---

## 🧪 Testing & Verification

### Running the Pytest Suite
Run the full 29-test test suite against an isolated test database harness:
```bash
uv run pytest -v
```

**Test Coverage Summary:**
- `tests/test_auth.py` (10 tests): Registration validation, password complexity, duplicate emails, login credentials, token refresh, authorization headers.
- `tests/test_upload.py` (5 tests): File type verification, 10MB size limit, empty file rejection, `202 Accepted` async contract, dataset pagination.
- `tests/test_profiling.py` (1 test): Background profiler execution, row/column counts, duplicate detection, null %, type inference, statistics.
- `tests/test_query_safety.py` (8 tests): Single `SELECT` enforcement, rejection of `DROP`/`UPDATE`/`DELETE`/multi-statements, protected table access rejection, row cap enforcement, dry-run query validation before saving.
- `tests/test_isolation.py` (1 test): Multi-tenant isolation: User B cannot access, query, or delete User A's datasets.
- `tests/test_ai_suggestions.py` (2 tests): Groq API prompt privacy check (verifying 0 raw rows sent) and heuristic fallback.
- `tests/test_sharing.py` (1 test): Mentor read-only access, linked saved queries, revocation.
- `tests/test_export.py` (1 test): Streaming CSV export verification.

### Running the End-to-End Walkthrough Script
To test the complete learner journey in a single automated command:
```bash
uv run python demo.py
```
This runs all 12 stages: registration &rarr; login &rarr; CSV upload (`202`) &rarr; background profiling &rarr; data report retrieval &rarr; safe SQL query &rarr; attack rejection &rarr; AI suggestions &rarr; query save &rarr; share link creation &rarr; mentor view &rarr; CSV export.

---

## 🐳 Docker Deployment

To build and run the backend as a standalone container:
```bash
docker build -t csvlab-backend .
docker run -p 8000:8000 --env-file .env csvlab-backend
```
Or orchestrate the full stack with PostgreSQL using the root `docker-compose.yml`.
