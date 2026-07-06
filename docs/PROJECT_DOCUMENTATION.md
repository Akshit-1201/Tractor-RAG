# Tractor Maintenance Assistant — Project Documentation

**Document type:** Technical Design & Development Specification
**Status:** Approved for development
**Audience:** Engineers building the application in the development phase
**Companion artifact:** `docs/architecture.svg` (system architecture diagram)

---

## Table of Contents

1. [Purpose of This Document](#1-purpose-of-this-document)
2. [Project Overview](#2-project-overview)
3. [Requirements](#3-requirements)
4. [Evaluation Criteria → Design Decisions](#4-evaluation-criteria--design-decisions)
5. [System Architecture](#5-system-architecture)
6. [Technology Stack](#6-technology-stack)
7. [Data Model & Database Schema](#7-data-model--database-schema)
8. [The RAG Pipeline (Detailed Design)](#8-the-rag-pipeline-detailed-design)
9. [Image Handling — The Core Design](#9-image-handling--the-core-design)
10. [API Specification](#10-api-specification)
11. [Frontend Design](#11-frontend-design)
12. [Authentication & Authorization](#12-authentication--authorization)
13. [Analytics & Usage Statistics](#13-analytics--usage-statistics)
14. [Cost & Performance Strategy](#14-cost--performance-strategy)
15. [Security Considerations](#15-security-considerations)
16. [Repository Structure](#16-repository-structure)
17. [Configuration & Environment Variables](#17-configuration--environment-variables)
18. [Deployment (Local Docker Compose)](#18-deployment-local-docker-compose)
19. [Testing Strategy](#19-testing-strategy)
20. [Development Plan & Milestones](#20-development-plan--milestones)
21. [Future Enhancements (Deliberately Deferred)](#21-future-enhancements-deliberately-deferred)
22. [Appendix A — Worked Example Flows](#appendix-a--worked-example-flows)
23. [Appendix B — Glossary](#appendix-b--glossary)

---

## 1. Purpose of This Document

This document is the single source of truth for building the Tractor Maintenance Assistant. It captures every architectural decision made during the design phase, the reasoning behind each one, and the concrete specifications (schema, APIs, pipeline logic, folder layout) needed to start writing code without re-opening settled questions.

Every non-trivial decision here is tied back to the three things the assignment is scored on: **role separation, accuracy, and speed/cost efficiency**. Where we consciously chose *not* to build something, that is recorded too (Section 21), because a deliberate deferral is itself a design decision.

---

## 2. Project Overview

### 2.1 Background

A tractor manufacturer wants a self-service website so customers can maintain and troubleshoot their tractors without contacting support. Administrators curate the official reference material; customers ask a chatbot questions in plain language and receive answers grounded strictly in that material.

### 2.2 Goal

Build a web application with two clearly separated experiences:

- An **authenticated admin dashboard** to upload and manage reference material (manuals, parts catalogs, maintenance guides) and reference images (parts, engine layouts, dashboard warning lights), and to view basic usage statistics.
- A **public customer chat** that answers troubleshooting questions using only the admin-uploaded content, and explicitly says it does not know when an answer is not in that content.

### 2.3 Scope

**In scope**

- Admin auth, document upload, image upload, content management (list/delete), usage analytics.
- Document + image ingestion into a Retrieval-Augmented Generation (RAG) pipeline.
- Public, text-only chat with grounded answers, source citations, and inline reference images where relevant.
- Local deployment via Docker Compose, a README, a setup guide, and a demo video.

**Out of scope (for this build)**

- Customer accounts or customer file uploads (customers interact by text only — per the brief).
- Multi-tenant / multi-manufacturer separation.
- Fine-tuning of any model.
- Production hosting, autoscaling, or high-availability concerns.
- A cross-encoder reranker (see Section 21 — deferred by design).

---

## 3. Requirements

### 3.1 Functional Requirements — Administrator

| ID | Requirement |
|----|-------------|
| FR-A1 | Admin can log into a dashboard with credentials. |
| FR-A2 | Admin can upload documents (PDF: user manuals, parts catalogs, maintenance guides). |
| FR-A3 | Admin can upload reference images (parts, engine layouts, warning lights). |
| FR-A4 | Admin can view the list of uploaded documents and images with their ingestion status. |
| FR-A5 | Admin can delete an uploaded document or image (which removes its indexed chunks). |
| FR-A6 | Admin can view usage statistics: total questions asked, answered vs. "don't know" rate, and most common topics/issues. |
| FR-A7 | All admin routes are protected; unauthenticated requests are rejected. |

### 3.2 Functional Requirements — Customer

| ID | Requirement |
|----|-------------|
| FR-C1 | Customer can access a public chat screen without logging in. |
| FR-C2 | Customer can ask questions in natural language. |
| FR-C3 | Customer receives answers grounded only in admin-uploaded content. |
| FR-C4 | When no relevant content exists, the customer receives an explicit "I don't know" response — never a guess. |
| FR-C5 | When a relevant reference image exists and was used to answer, it is displayed alongside the answer. |
| FR-C6 | Customer cannot upload files or access any admin function. |
| FR-C7 | Answers show which sources they came from (documents / images). |

### 3.3 Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 (Accuracy) | Answers must be grounded; no hallucinated instructions. | 0 fabricated answers on out-of-scope test set |
| NFR-2 (Speed) | Chat responses should feel fast. | First token < ~1.5 s via streaming; typical full answer < ~5 s |
| NFR-3 (Cost) | Data-processing cost minimized. | No vision inference on the query path; cheap embedding + chat models |
| NFR-4 (Role separation) | Admin and customer surfaces physically distinct. | Separate route trees; no shared code path from customer to admin |
| NFR-5 (Reproducibility) | The whole system runs locally with one command. | `docker compose up` |

---

## 4. Evaluation Criteria → Design Decisions

This table is the connective tissue of the whole project. It maps each scored criterion to the concrete choices that satisfy it.

| Criterion | Design decisions that satisfy it |
|-----------|----------------------------------|
| **Role separation** | Separate FastAPI routers (`/admin/*` vs `/chat`); separate frontend route trees (`/admin/*` vs `/`); JWT guard on all admin routes; the public chat has no import path reaching admin components. |
| **Accuracy** | Strict grounding prompt ("answer only from context, else say I don't know"); LLM cites the chunk IDs it used; citations rendered in the UI; the "I don't know" path is first-class and tested. |
| **Speed & Cost** | Vision runs **once at upload**, never per query; cheap models (`gpt-4o-mini`, `text-embedding-3-small`); one Postgres + pgvector store instead of a separate vector service; hybrid search without a reranker at this scale; SSE streaming for perceived speed. |

---

## 5. System Architecture

### 5.1 High-Level Shape

Two frontend surfaces (admin, customer) talk to **one backend API**, which orchestrates a RAG pipeline over a single Postgres + pgvector store and calls the OpenAI APIs. See `docs/architecture.svg` for the annotated diagram.

The system is best understood as **two distinct paths**:

- **The upload / ingestion path (runs rarely).** Triggered by admin uploads. This is where all expensive work lives — PDF parsing, image → text via vision, embedding, indexing.
- **The query / hot path (runs constantly).** Triggered by every customer question. This path is deliberately cheap: embed the question, hybrid-retrieve, one grounded chat call, assemble the response. It never invokes vision.

Keeping expensive work on the rare path and the cheap work on the constant path is the central cost strategy of the entire system.

### 5.2 Backend Layering

```
API layer        thin FastAPI routers (admin router, customer router) — validation only
   │
Service layer    ingestion · retrieval · chat · analytics · vision · embeddings
   │
Store layer      PostgreSQL + pgvector (credentials, metadata, vectors, full-text, analytics)
```

The API layer does no business logic; it validates input and delegates to services. All RAG logic lives in the service layer so it is legible and testable in isolation.

### 5.3 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `ingestion` service | Route an uploaded file: PDF → parse + chunk; image → vision-to-text. Then embed and upsert. |
| `vision` service | Single call to the vision model to convert an image into a rich, structured text description at upload time. |
| `embeddings` service | Wrap the embedding model; used by both ingestion and query paths. |
| `retrieval` service | Hybrid query (dense + lexical), fuse, return top chunks with scores and IDs. |
| `chat` service | Build the grounded prompt, call the chat model, parse the answer and cited chunk IDs, apply the image gate. |
| `analytics` service | Log each question/answer event and compute usage statistics. |

---

## 6. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | **Python + FastAPI** | The RAG work (PDF parsing, embeddings, vector queries, vision) is Python-first and cleanest there; evaluators expect to read RAG logic in Python; async support suits streaming. |
| Frontend | **React + Vite (SPA)** | Backend is FastAPI, so Next.js's server features would be redundant. A Vite SPA is lighter and keeps the "React calls Python API" boundary clean. SSR/SEO are irrelevant for a dashboard and a chat widget. |
| Vector store | **PostgreSQL + pgvector** | One store holds vectors, relational data (credentials, metadata), and the lexical index for hybrid search — we need Postgres for analytics/metadata anyway, so this avoids a second service and directly serves the cost/simplicity criterion. |
| Embeddings | **OpenAI `text-embedding-3-small`** (1536-dim) | Cheap, strong, and the same model is reused across both paths for consistency. |
| Vision | **OpenAI `gpt-4o-mini`** (vision) | Cheap multimodal model; called once per image at upload only. |
| Chat | **OpenAI `gpt-4o-mini`** | Cheap, fast, sufficient for grounded synthesis over retrieved context. |
| PDF parsing | **PyMuPDF** (`fitz`) | Fast, robust text extraction. |
| Auth | **JWT** (python-jose) + **passlib/bcrypt** | Minimal but real; one seeded admin role. |
| Migrations | **Alembic** | Reproducible schema. |
| Packaging | **Docker Compose** | One-command local run of db + backend + frontend. |

> **Note:** `gpt-4o-mini` is named as the default for vision and chat. The model names are centralized in configuration (Section 17) so they can be swapped without code changes.

---

## 7. Data Model & Database Schema

All persistent state lives in one Postgres database with the `vector` extension enabled.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Admin accounts (seeded; no self-registration)
CREATE TABLE admins (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Uploaded source documents (PDFs)
CREATE TABLE documents (
    id           SERIAL PRIMARY KEY,
    filename     TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    file_type    TEXT NOT NULL DEFAULT 'pdf',
    status       TEXT NOT NULL DEFAULT 'processing', -- processing | indexed | failed
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Uploaded reference images
CREATE TABLE images (
    id                SERIAL PRIMARY KEY,
    filename          TEXT NOT NULL,
    file_path         TEXT NOT NULL,           -- on-disk path
    image_url         TEXT NOT NULL,           -- URL served to the frontend
    description       TEXT,                    -- vision-generated caption
    category          TEXT,                    -- warning_light | parts_diagram | engine_layout | other
    structured_fields JSONB,                   -- e.g. {colour, symbol, blink, severity, meaning}
    status            TEXT NOT NULL DEFAULT 'processing',
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unified chunk index: text chunks from documents AND descriptions from images
CREATE TABLE chunks (
    id          SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,                 -- 'document' | 'image'
    source_id   INTEGER NOT NULL,              -- FK to documents.id or images.id
    content     TEXT NOT NULL,                 -- chunk text, or the image description
    embedding   VECTOR(1536) NOT NULL,         -- dense vector (pgvector)
    tsv         TSVECTOR,                       -- lexical index for hybrid search
    metadata    JSONB NOT NULL DEFAULT '{}',   -- {image_url, page, source_name, ...}
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Analytics: one row per customer question
CREATE TABLE questions (
    id                 SERIAL PRIMARY KEY,
    question_text      TEXT NOT NULL,
    answer_text        TEXT NOT NULL,
    is_answered        BOOLEAN NOT NULL,        -- false = "I don't know"
    retrieved_chunk_ids INTEGER[] NOT NULL DEFAULT '{}',
    cited_chunk_ids    INTEGER[] NOT NULL DEFAULT '{}',
    image_shown        BOOLEAN NOT NULL DEFAULT false,
    topic              TEXT,                    -- coarse category for "common issues"
    latency_ms         INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX idx_chunks_source ON chunks (source_type, source_id);
CREATE INDEX idx_questions_created ON questions (created_at);
```

**Notes on the schema**

- The `chunks` table is the *unified index*. A document chunk and an image description are the same kind of row; the query path treats them identically. `source_type` + `metadata.image_url` is what lets the image gate later attach the picture.
- `tsv` is populated from `content` at insert time (trigger or application-side, always with the explicit `'english'` search config — the same config must be used on the query side) and powers the lexical half of hybrid search.
- The ANN index is **HNSW**, not ivfflat: ivfflat trains its centroids when the index is built, so creating it in the initial migration — on an empty table — silently degrades recall; HNSW needs no training data and handles incremental inserts. (At this corpus size an exact scan would also be fine; the index is kept for form.)
- Deleting a document or image cascades to deleting its `chunks` rows (enforced in the service layer or via triggers), keeping the index consistent with what the admin has uploaded — critical for the grounding guarantee.

---

## 8. The RAG Pipeline (Detailed Design)

### 8.1 Document Ingestion (upload path)

1. Admin uploads a PDF → saved to storage; a `documents` row is created with `status = 'processing'`.
2. **Parse** text with PyMuPDF, page by page.
3. **Chunk** the text: target ~500–800 tokens per chunk with ~10–15% overlap, splitting on paragraph/heading boundaries where possible. Each chunk carries metadata `{source_name, page}`.
4. **Embed** each chunk with `text-embedding-3-small`.
5. **Upsert** chunks into `chunks` (`source_type='document'`), populate `tsv`.
6. Update the document `status = 'indexed'` and `chunk_count`.

### 8.2 Image Ingestion (upload path)

Covered in detail in Section 9. In short: one vision call converts the image to a structured description at upload; that description is embedded and stored as a `chunks` row (`source_type='image'`) with the `image_url` in metadata.

### 8.3 Retrieval (query path) — Hybrid Search

We combine two retrieval signals and fuse them:

- **Dense** — cosine similarity over `embedding` (pgvector). Captures semantic meaning.
- **Lexical** — Postgres full-text (`tsvector` / `ts_rank_cd`). Captures exact tokens that dense retrieval blurs: **part numbers, error/fault codes, model names** (e.g. `E-047`, `part #AL120`).

Fusion uses **Reciprocal Rank Fusion (RRF)** — rank-based, so it needs no score normalization between the two very different scoring scales.

```python
def retrieve(query: str, k: int = 8) -> list[Chunk]:
    q_vec = embed(query)

    dense = db.query("""
        SELECT id, source_type, source_id, content, metadata,
               1 - (embedding <=> :qvec) AS score
        FROM chunks
        ORDER BY embedding <=> :qvec
        LIMIT :n
    """, qvec=q_vec, n=k * 3)

    lexical = db.query("""
        SELECT id, source_type, source_id, content, metadata,
               1 - (embedding <=> :qvec) AS score,   -- canonical score: dense cosine (see note below)
               ts_rank_cd(tsv, plainto_tsquery('english', :q)) AS lex_rank
        FROM chunks
        WHERE tsv @@ plainto_tsquery('english', :q)
        ORDER BY lex_rank DESC
        LIMIT :n
    """, q=query, qvec=q_vec, n=k * 3)

    return reciprocal_rank_fusion(dense, lexical)[:k]
```

**Score semantics (important).** RRF is used *only to order* the fused list. Every chunk keeps its **dense cosine similarity** (`1 - (embedding <=> qvec)`) as `score` — both SQL branches return it, which is why the lexical query computes it too. That cosine value is what Gate 3 of the image gate (Section 9.4) compares against `IMAGE_SIMILARITY_THRESHOLD`. RRF's own scores (≈ 0.03 at best with the standard k=60) must never be compared against that threshold — doing so would silently prevent any image from ever being shown.

> At the corpus size this project realistically runs at (a handful of manuals plus reference images), dense retrieval alone is nearly sufficient. Hybrid is added because the lexical half is essentially free in Postgres and specifically rescues part-number / error-code queries. A cross-encoder **reranker is deliberately not used** — see Section 21.

### 8.4 Grounded Answer Generation (query path)

The chat service builds a numbered context block from retrieved chunks and calls the chat model with a strict grounding instruction that also asks the model to declare which sources it used. That "which sources did you use" declaration is what powers both the citations feature and the image gate (Option A).

**System prompt (canonical — lives in `app/core/prompts.py`):**

```
You are a tractor maintenance assistant. Answer the user's question using ONLY the
numbered context sources provided below. Follow these rules exactly:

1. Use only information found in the context. Do not use outside knowledge.
2. If the answer is not present in the context, respond with exactly:
   "I don't have information about that in the available documents."
3. Be concise and practical.
4. After your answer, output a final line in the form:
   CITED: [comma-separated list of the source numbers you actually used]
   If you could not answer, output: CITED: []
5. Some context sources are text descriptions of reference images. Include an
   image source's number in CITED when it depicts the exact item or symptom the
   user is asking about (for example, the specific warning light they describe).
   Do not cite an image merely because it shows the location of parts mentioned
   in your answer.
```

> **Tuning note (Phase 5):** rule 5 was added after live testing showed a
> literal-minded model never citing image sources — a text chunk always "supplied
> the words," so worked example A.1 lost its image. The rule defines what "used"
> means for a picture (it depicts the exact subject of the question) and its second
> sentence explicitly protects the A.3 edge case (diagrams are not cited merely for
> showing part locations). Gates 1 and 3 are untouched; the conservative bias stands.

**Chat orchestration:**

```python
def answer_question(query: str) -> ChatResult:
    chunks = retrieve(query, k=RETRIEVAL_TOP_K)
    context = format_numbered_context(chunks)          # "[1] ...\n[2] ...\n"
    raw = llm.chat(system=SYSTEM_PROMPT,
                   user=f"{context}\n\nQuestion: {query}")

    answer_text, cited_source_numbers = parse_answer_and_citations(raw)
    cited_chunk_ids = map_numbers_to_chunk_ids(cited_source_numbers, chunks)
    is_answered = not is_idk(answer_text)
    if not is_answered:
        answer_text = IDK_MESSAGE   # always return the canonical string verbatim
        cited_chunk_ids = []        # an IDK response never carries sources or an image

    image = select_image(chunks, cited_chunk_ids, is_answered)   # Section 9.4
    sources = build_sources(chunks, cited_chunk_ids)

    analytics.log(query, answer_text, is_answered,
                  retrieved=[c.id for c in chunks],
                  cited=cited_chunk_ids, image_shown=bool(image))

    return ChatResult(answer_text, is_answered, sources, image)
```

### 8.5 The "I don't know" Guarantee

Two layers enforce it:

1. **Prompt-level.** The model is instructed to emit the exact "I don't have information…" string when context is insufficient.
2. **System-level.** `is_answered` is derived from the answer, and it gates downstream behavior (no image, no misleading sources) so an unsupported response can never be dressed up as a confident one. Concretely: when `is_idk` fires, the service replaces the model output with the canonical `IDK_MESSAGE` constant (defined in `app/core/prompts.py`) and forces `cited_chunk_ids = []` — even if the model emitted the IDK string *and* a non-empty `CITED:` list.

**Robust IDK detection.** `is_idk` must not be strict string equality: models drift on curly vs. straight apostrophes (`don’t` / `don't`), trailing periods, and whitespace. Detect via normalized `startswith` (strip whitespace, casefold, unify apostrophes), then canonicalize the outgoing answer to the exact constant.

This is the accuracy criterion, and it is explicitly tested (Section 19).

---

## 9. Image Handling — The Core Design

Images are flagged twice in the brief and interact directly with the cost criterion, so this is the most consequential part of the design. The full rationale was worked through in design; this section is the build spec.

### 9.1 Principle: describe images to text at upload time

The RAG pipeline is text-based. Rather than build a parallel image-retrieval system, each image is converted into a rich text description **once, at upload**, and embedded into the *same* index as documents. From retrieval's point of view an image description is just another chunk.

### 9.2 Vision ingestion

**Vision prompt (canonical — `app/core/prompts.py`):**

```
You are cataloguing a tractor reference image for a maintenance knowledge base.
Describe it in detail so it can be found by a text search later.
- If it shows a dashboard warning light: state its colour, symbol, blink behaviour,
  severity, and what it means for the operator, plus the recommended action.
- A still image cannot show motion: never claim a light is "solid" or "not
  blinking" unless the image makes that explicit. Radiating rays or motion marks
  around a symbol conventionally depict a flashing/active alert - describe them
  as a flashing indicator.
- If it shows a parts or engine diagram: enumerate every labelled component.
Return JSON:
{ "description": "...", "category": "warning_light|parts_diagram|engine_layout|other",
  "structured_fields": { ... } }
```

> **Tuning note (Phase 5):** the motion clause was added after live testing showed the
> vision model asserting "not blinking" for still images — a lossy description that
> blocked citation for flashing-light questions. Per §9.5, the remedy is exactly this:
> a richer ingestion prompt, paid once at upload — the hot path was never touched.

Flow:

1. Save the image; create an `images` row (`status='processing'`).
2. One vision call (`gpt-4o-mini`) → `{description, category, structured_fields}`.
3. Store these on the `images` row.
4. Embed `description`; insert one `chunks` row with `source_type='image'` and metadata `{image_url, source_name: <original filename>}` (`source_name` feeds the image caption and the sources list).
5. `status='indexed'`.

The expensive multimodal call happens exactly once per image, regardless of how many times it is later queried.

### 9.3 Displaying images (query path)

When the answer is generated, we may attach **one** reference image. The image URL is already in chunk metadata, so displaying it costs nothing at query time. What the customer sees: the grounded text answer, and — when appropriate — the actual reference image beside it (the highest-value moment in the demo).

### 9.4 The image gate (Option A) — three conditions

An image is attached **only if all three hold**. This is the decisive logic that prevents irrelevant or misleading images.

```python
def select_image(chunks, cited_chunk_ids, is_answered):
    # Gate 1 — never show an image alongside "I don't know"
    if not is_answered:
        return None

    candidates = [
        c for c in chunks
        if c.source_type == "image"
        and c.id in cited_chunk_ids          # Gate 2 (Option A): the LLM actually used it
        and c.score >= IMAGE_SIMILARITY_THRESHOLD  # Gate 3: confidence floor
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda c: c.score)
    return {"url": best.metadata["image_url"], "caption": best.metadata.get("source_name")}
```

- **Gate 1 (no image on "I don't know")** keeps an unanswered response coherent.
- **Gate 2 — Option A (citation)** is the primary defense. An image is shown only if the LLM *cited its chunk* in producing the answer. This is what stops the classic failure where a query like "how to change engine oil" retrieves an engine *diagram* (high lexical/semantic overlap) that the answer never actually used. Retrieved ≠ used; only *used* images are shown.
- **Gate 3 (confidence threshold)** is a backstop against weak matches sneaking through. The `score` it checks is the chunk's **dense cosine similarity** to the query, carried through fusion (Section 8.3) — never the RRF ordering score, which tops out near 0.03 and would fail this gate unconditionally.

The bias is intentional: **when in doubt, show no image.** A text-only answer is never wrong; a confidently displayed wrong image erodes trust more than a missing one.

### 9.5 Why not the alternatives (recorded for the README)

- **Query-time vision** (feed the real image to the model per query): re-introduces multimodal cost and latency on the constant hot path — exactly what the upload-time design removes — for marginal accuracy gain, since a warning light essentially *is* its caption. If descriptions ever prove lossy, the fix is a richer **ingestion** prompt (pay once), not query-time vision. Kept as a documented fallback only.
- **Multimodal / CLIP-style image-similarity retrieval**: adds a second embedding pipeline and a model dependency OpenAI doesn't host, and makes matching fuzzier for precise technical questions. Rejected.

---

## 10. API Specification

Base path: `/api`. All admin routes require a valid JWT (`Authorization: Bearer <token>`). The chat route is public.

### 10.1 Auth

**`POST /api/admin/login`**
```json
// request
{ "username": "admin", "password": "••••••" }
// response 200
{ "access_token": "eyJ...", "token_type": "bearer" }
// response 401 — invalid credentials
```

### 10.2 Documents (admin)

**`POST /api/admin/documents`** — multipart upload (`file`)
```json
// response 202
{ "id": 12, "filename": "maintenance_guide.pdf", "status": "processing" }
```

**`GET /api/admin/documents`**
```json
[ { "id": 12, "filename": "maintenance_guide.pdf", "status": "indexed",
    "chunk_count": 84, "uploaded_at": "2026-07-04T10:00:00Z" } ]
```

**`DELETE /api/admin/documents/{id}`** → `204` (also removes its chunks)

### 10.3 Images (admin)

**`POST /api/admin/images`** — multipart upload (`file`)
```json
// response 202
{ "id": 5, "filename": "red-battery-light.png", "status": "processing" }
```

**`GET /api/admin/images`**
```json
[ { "id": 5, "filename": "red-battery-light.png", "status": "indexed",
    "category": "warning_light", "image_url": "/storage/images/red-battery-light.png",
    "description": "A dashboard warning indicator showing a red battery symbol...",
    "uploaded_at": "2026-07-04T10:05:00Z" } ]
```

**`DELETE /api/admin/images/{id}`** → `204` (also removes its chunk)

### 10.4 Analytics (admin)

**`GET /api/admin/analytics`**
```json
{
  "total_questions": 128,
  "answered": 111,
  "unknown": 17,
  "answer_rate": 0.867,
  "top_topics": [
    { "topic": "warning lights", "count": 34 },
    { "topic": "transmission fluid", "count": 21 }
  ],
  "recent_questions": [
    { "question": "What does a flashing red battery light mean?",
      "is_answered": true, "created_at": "2026-07-04T11:59:00Z" }
  ]
}
```

### 10.5 Chat (public)

**`POST /api/chat`**
```json
// request
{ "question": "What does a flashing red battery light mean?" }
```

Two response modes:

**(a) JSON (simple mode)**
```json
{
  "answer": "A flashing red battery light indicates a charging system fault...",
  "is_answered": true,
  "sources": [
    { "type": "document", "name": "maintenance_guide.pdf", "chunk_id": 42 },
    { "type": "image", "name": "red-battery-light.png", "chunk_id": 88 }
  ],
  "image": { "url": "/storage/images/red-battery-light.png",
             "caption": "Red battery warning light" }
}
```

**(b) SSE stream (default for the UI)** — token events for the answer, then a final event carrying `is_answered`, `sources`, and `image`. Streaming is what makes answers feel instant (NFR-2). The server **strips the trailing `CITED: [...]` line from the token stream** (hold back a small tail buffer — tokens can split mid-word, e.g. `CIT` + `ED:`); citations reach the client only via the final metadata event. Clients consume the stream with `fetch` + `ReadableStream`, since `EventSource` cannot send a POST body.

**"I don't know" response:**
```json
{ "answer": "I don't have information about that in the available documents.",
  "is_answered": false, "sources": [], "image": null }
```

---

## 11. Frontend Design

Single React (Vite) app, two route trees. The physical separation *is* the role-separation criterion.

### 11.1 Admin (`/admin/*`, behind login)

| Screen | Contents |
|--------|----------|
| **Login** (`/admin/login`) | Username/password form → stores JWT; redirects to dashboard. |
| **Upload & Manage** (`/admin/content`) | Drag-drop upload for PDFs and images; two lists (documents, images) each showing ingestion status (`processing → indexed`) and a delete action. The status indicator makes the cost-saving vision-at-upload step visible. |
| **Analytics** (`/admin/analytics`) | Cards for total questions, answered vs. "don't know" rate; a list of most common topics; recent questions. |

An auth guard (route wrapper) redirects unauthenticated users to `/admin/login`. Admin API calls attach the JWT.

### 11.2 Customer (`/`, public)

A single chat screen: message list, input box, streaming answers. Conditional rendering driven entirely by the `/chat` response:

- `is_answered && image` → render the answer text **and** the image beneath it.
- `is_answered && !image` → render the answer text only, with **no** placeholder and no apology for a missing image ("no image" is the normal state of most answers).
- `!is_answered` → render the "I don't know" text plainly, no image.

Under each answered response, render the `sources` list (document name / image) so grounding is *visible* — turning the accuracy work into something the evaluator can see.

### 11.3 Component sketch

```
src/
├── admin/
│   ├── LoginPage.tsx
│   ├── ContentPage.tsx       # upload + lists + status
│   ├── AnalyticsPage.tsx
│   └── RequireAuth.tsx       # route guard
├── customer/
│   ├── ChatPage.tsx
│   ├── MessageList.tsx
│   ├── MessageBubble.tsx     # renders text + optional image + sources
│   └── ChatInput.tsx
├── api/ (client.ts, admin.ts, chat.ts)   # typed fetch wrappers, SSE handling
└── context/AuthContext.tsx
```

### 11.4 Backend access — the dev proxy (how relative URLs work)

The SPA uses **relative** URLs for both the API (`/api/...`) and stored files (`/storage/...`), but those are served by the backend on port 8000 while the SPA loads from port 5173. The Vite dev server bridges this with `server.proxy`: `/api` and `/storage` are forwarded to the backend (target from env — `http://localhost:8000` locally, `http://backend:8000` inside Docker Compose). This is what makes the spec's relative `image_url` values (e.g. `/storage/images/red-battery-light.png`) render correctly in `<img>` tags. CORS (Section 15) stays configured as defense-in-depth for any direct cross-origin calls.

---

## 12. Authentication & Authorization

Minimal but real — there is exactly one role that logs in.

- **Seeding.** One admin account is seeded from env vars (`ADMIN_USERNAME`, `ADMIN_PASSWORD`) via `backend/scripts/seed_admin.py` (it runs inside the backend container, where the app's models and config are importable); the password is stored **bcrypt-hashed**. No self-registration.
- **Login.** Verifies the password, returns a signed **JWT** (`JWT_SECRET`, expiry `JWT_EXPIRY_MINUTES`).
- **Guarding.** A FastAPI dependency (`get_current_admin`) validates the token and is attached to every `/admin/*` route. The public `/chat` route omits it by design.
- **Deliberately not built:** password reset, OAuth/SSO, multi-user roles. Over-building auth scores nothing here.

---

## 13. Analytics & Usage Statistics

Every call to `/api/chat` writes one `questions` row (Section 7). From that table the analytics endpoint computes:

- **Total questions** — row count.
- **Answered vs. "I don't know"** — `is_answered` split and rate. (This doubles as a content-gap signal: a high "don't know" rate flags material the admin should upload.)
- **Most common issues/topics** — grouped by `topic`. For v1, `topic` is a coarse label assigned cheaply at log time (keyword match against a small tag list, e.g. "warning lights", "transmission", "hydraulics", "engine", "brakes"); an optional lightweight LLM classification can replace it later without schema change. Queries matching no keyword get `topic = 'other'`, so `top_topics` never groups on NULL.
- **Recent questions** — latest N for a live feed.

---

## 14. Cost & Performance Strategy

Consolidated so it can be lifted directly into the README's cost section.

| Lever | Effect |
|-------|--------|
| **Vision at upload, not per query** | The one expensive (multimodal) operation runs once per image, then its text is reused for every future query. Cost scales with *uploads* (rare), not *traffic* (constant). |
| **Lean hot path** | Every query = one embedding + one hybrid SQL retrieval + one `gpt-4o-mini` chat call. No vision, no reranker. |
| **Cheap models** | `text-embedding-3-small` and `gpt-4o-mini` are inexpensive and fast, and sufficient for this task. |
| **Single store** | Postgres + pgvector holds vectors, relational data, and the lexical index — no separate vector-DB service to run or pay for. Analytics and metadata come "for free" in the same DB. |
| **Hybrid without rerank** | The lexical half is free in Postgres and fixes part-number/code queries; a cross-encoder is deferred (Section 21) to keep the hot path cheap. |
| **SSE streaming** | Total compute is unchanged, but first-token latency drops sharply, so answers *feel* instant (NFR-2). |

---

## 15. Security Considerations

- **Secrets** (OpenAI key, JWT secret, DB URL, admin password) come only from environment variables; never committed. `.env.example` documents them with placeholders.
- **Passwords** are bcrypt-hashed at rest.
- **Admin routes** are JWT-guarded; tokens expire.
- **Upload validation** — enforce allowed types (PDF for documents; common image types for images), size limits (`MAX_UPLOAD_MB`), and store uploads outside any executable path.
- **Public-endpoint abuse caps** — `/api/chat` fronts paid OpenAI calls with no auth, so it enforces a question-length cap (`MAX_QUESTION_CHARS` → 422) and a light per-IP rate limit (`CHAT_RATE_LIMIT`). Cost efficiency is a scored criterion; an uncapped public endpoint would undermine it. The admin login carries its own per-IP limit (`LOGIN_RATE_LIMIT`) as a brute-force guard.
- **Input handling** — parameterized SQL only (no string-built queries) to avoid injection; the vector/lexical queries use bound parameters.
- **Grounding as a safety property** — because answers are constrained to uploaded content and default to "I don't know," the customer surface has a small hallucination surface by construction.
- **CORS** — the API permits only the frontend origin.

---

## 16. Repository Structure

```
tractor-maintenance-assistant/
├── README.md                     # overview, architecture summary, run instructions
├── SETUP.md                      # project initiation / local setup guide
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── PROJECT_DOCUMENTATION.md  # this document
│   └── architecture.svg          # system architecture diagram
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                  # migrations
│   ├── app/
│   │   ├── main.py               # FastAPI app, router registration, CORS
│   │   ├── config.py             # env-driven settings (models, thresholds, secrets)
│   │   ├── database.py           # engine, session
│   │   ├── dependencies.py       # get_current_admin (JWT guard)
│   │   ├── models/               # SQLAlchemy: admin, document, image, chunk, question
│   │   ├── schemas/              # Pydantic request/response models
│   │   ├── routers/
│   │   │   ├── admin.py          # /admin/* (auth, documents, images, analytics)
│   │   │   └── chat.py           # /chat (public, streaming)
│   │   ├── services/
│   │   │   ├── ingestion.py
│   │   │   ├── vision.py
│   │   │   ├── embeddings.py
│   │   │   ├── retrieval.py      # hybrid + RRF
│   │   │   ├── chat.py           # grounding + citation parse + image gate
│   │   │   └── analytics.py
│   │   ├── core/
│   │   │   ├── security.py       # hashing, JWT
│   │   │   └── prompts.py        # SYSTEM_PROMPT, VISION_PROMPT, IDK_MESSAGE
│   │   └── utils/
│   │       ├── pdf_parser.py     # PyMuPDF extraction
│   │       └── chunking.py
│   ├── tests/                    # see Section 19
│   └── scripts/
│       └── seed_admin.py         # create the seeded admin from env vars (runs in the backend container)
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts            # dev proxy: /api + /storage → backend (Section 11.4)
    ├── index.html
    └── src/                      # see Section 11.3
```

---

## 17. Configuration & Environment Variables

Documented in `.env.example`:

```bash
# --- OpenAI ---
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o-mini

# --- Database ---
DATABASE_URL=postgresql://postgres:postgres@db:5432/tractor

# --- Auth ---
JWT_SECRET=change-me
JWT_EXPIRY_MINUTES=120
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me

# --- RAG tuning ---
RETRIEVAL_TOP_K=8
IMAGE_SIMILARITY_THRESHOLD=0.35      # Gate 3 — compared against dense cosine similarity (§8.3)
CHUNK_TARGET_TOKENS=650
CHUNK_OVERLAP_TOKENS=80

# --- Limits / abuse protection ---
MAX_QUESTION_CHARS=1000              # /api/chat rejects longer questions (422)
CHAT_RATE_LIMIT=20/minute            # per-IP limit on /api/chat
LOGIN_RATE_LIMIT=10/minute           # per-IP limit on /api/admin/login (brute-force guard)
MAX_UPLOAD_MB=50                     # per-file upload cap (documents & images)

# --- Storage / server ---
STORAGE_PATH=/data/storage
FRONTEND_ORIGIN=http://localhost:5173
```

Centralizing model names and thresholds here means retrieval/answer behavior can be tuned without touching code.

---

## 18. Deployment (Local Docker Compose)

Three services: `db` (Postgres + pgvector), `backend` (FastAPI), `frontend` (Vite build served statically or in dev).

```yaml
# docker-compose.yml (shape)
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: tractor
      POSTGRES_PASSWORD: postgres
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d tractor"]
      interval: 2s
      timeout: 3s
      retries: 20
    volumes: [ "pgdata:/var/lib/postgresql/data" ]

  backend:
    build: ./backend
    env_file: .env
    depends_on:
      db: { condition: service_healthy }   # never run migrations before Postgres is ready
    volumes: [ "storage:/data/storage" ]
    ports: [ "8000:8000" ]

  frontend:
    build: ./frontend
    depends_on: [ backend ]
    ports: [ "5173:5173" ]
    # dev server runs with --host 0.0.0.0; proxies /api + /storage → http://backend:8000 (§11.4)

volumes: { pgdata: {}, storage: {} }
```

**Startup sequence (documented fully in `SETUP.md`):**

1. `cp .env.example .env` and fill in `OPENAI_API_KEY` (and change secrets).
2. `docker compose up --build`.
3. Backend runs Alembic migrations and enables the `vector` extension on start.
4. `backend/scripts/seed_admin.py` seeds the admin account (invoked on first boot).
5. Open the customer chat at `http://localhost:5173/` and the admin dashboard at `http://localhost:5173/admin/login`.

---

## 19. Testing Strategy

The tests exist primarily to prove the **accuracy** criterion. The four image/answer cases and the grounding refusal are the priority.

| Test | What it verifies |
|------|------------------|
| Chunking unit test | Chunk sizes/overlap within bounds; metadata attached. |
| RRF fusion unit test | Fusion ranks a chunk high when both signals agree; lexical rescues an exact code match. |
| **Grounding refusal** | An out-of-scope question ("best fertilizer for wheat") → exactly the "I don't know" string; `is_answered=false`; no sources; no image. |
| **Image gate — happy path** | Battery-light question → image chunk cited → image attached. |
| **Image gate — retrieved-not-used** | "How to change engine oil" retrieves an engine diagram that is *not* cited → **no image** attached. |
| **Image gate — no image on IDK** | Unanswered question with a weakly-matching image present → no image. |
| Citation parse test | `CITED: [...]` line is parsed correctly; maps source numbers → chunk IDs. |
| Auth test | `/admin/*` without a token → 401; with a valid token → 200. |
| Delete-consistency test | Deleting a document/image removes its chunks (grounding stays consistent). |
| Chat abuse caps | Question over `MAX_QUESTION_CHARS` → 422; exceeding the per-IP rate limit → 429. |
| Ingestion integration | Upload a small PDF and an image → both reach `indexed`; a related question retrieves them. |

---

## 20. Development Plan & Milestones

A suggested build order that front-loads the risky, scored parts.

| Milestone | Deliverable |
|-----------|-------------|
| **M1 — Skeleton & infra** | Repo structure, Docker Compose, Postgres + pgvector up, migrations, seeded admin, health check. |
| **M2 — Admin auth + upload** | Login + JWT guard; document upload → parse → chunk → embed → index; upload status visible. |
| **M3 — Image ingestion** | Vision-to-text at upload; image chunk indexed with `image_url`; structured fields captured. |
| **M4 — Retrieval + grounded chat** | Hybrid retrieval + RRF; grounding prompt; citation parsing; **"I don't know"** working end to end. |
| **M5 — Image gate (Option A)** | The three-gate `select_image`; all four image/answer cases passing tests. |
| **M6 — Customer chat UI** | Streaming chat; conditional image/sources rendering. |
| **M7 — Analytics** | Question logging; analytics endpoint + dashboard screen. |
| **M8 — Polish & deliverables** | Threshold tuning, seed content, README, SETUP.md, demo video. |

---

## 21. Future Enhancements (Deliberately Deferred)

Recorded so the README can show these were considered and consciously scoped out — a deferral is a design decision.

- **Cross-encoder reranker.** Would improve precision as the corpus grows into thousands of documents, at the cost of an extra per-query model call (latency + cost on the hot path). Not justified at this corpus size; add only when retrieval quality — not cost — becomes the binding constraint.
- **Query-time vision (fallback).** For genuinely diagram-dense content where captions prove lossy. Preferred remedy is a richer *ingestion* prompt (pay once) before ever moving vision onto the hot path.
- **True BM25.** Postgres full-text (`ts_rank_cd`) is the pragmatic lexical signal; a `pg_search`/ParadeDB extension could provide true BM25 if lexical quality ever needs it — no architecture change.
- **Multi-image answers, richer topic clustering, session tracking, feedback capture (thumbs up/down)** to close the analytics loop. (A `session_id` was deliberately dropped from the v1 chat API — accepted-but-unused fields invite dead code.)

---

## Appendix A — Worked Example Flows

**A.1 Happy path with image.** Customer: *"What does a flashing red battery light mean?"* → question embedded → hybrid retrieval surfaces the battery-light image description (cited) plus a charging-system text chunk → grounded answer generated, image chunk **cited** → all three gates pass → **answer + battery-light photo + sources** returned.

**A.2 Text answer, no image.** Customer: *"How do I change the transmission fluid?"* → strong document chunks retrieved, no image chunk cited/relevant → **answer text only, no image, no apology**. This is the ordinary case.

**A.3 The engine-oil edge case.** Customer: *"How to change engine oil?"* → an engine *layout diagram* is retrieved (high overlap) but the answer comes from a maintenance-guide text chunk; the diagram is **not cited** → Gate 2 fails → **answer text only, no diagram** — correct, because the diagram doesn't actually answer the question.

**A.4 Out of scope.** Customer: *"What's the best fertilizer for wheat?"* → nothing relevant clears retrieval → model emits the exact **"I don't have information about that in the available documents."** → `is_answered=false`, no sources, no image.

---

## Appendix B — Glossary

| Term | Meaning |
|------|---------|
| **RAG** | Retrieval-Augmented Generation — retrieve relevant text, then have an LLM answer using only that text. |
| **Chunk** | A small unit of indexed text (a slice of a document, or an image's description). |
| **Embedding** | A vector capturing text meaning, used for semantic similarity search. |
| **Dense retrieval** | Similarity search over embeddings (pgvector). |
| **Lexical retrieval** | Keyword/token search (Postgres full-text) — catches exact strings like part numbers. |
| **Hybrid search** | Combining dense + lexical results. |
| **RRF** | Reciprocal Rank Fusion — merges two ranked lists without score normalization. |
| **Option A** | Gating image display on whether the LLM *cited* the image's chunk in its answer. |
| **The image gate** | The three conditions (answered, cited, above threshold) that must all hold to display an image. |
| **Grounding** | Constraining answers strictly to retrieved context; otherwise "I don't know." |
| **Hot path** | The per-query flow that must stay cheap and fast. |

---

*End of document.*
