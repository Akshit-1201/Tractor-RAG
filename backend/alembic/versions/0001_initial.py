"""Initial schema: vector extension, five tables, indexes, tsv trigger (spec §7).

Revision ID: 0001
Revises:
Create Date: 2026-07-05

"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The extension must exist before any VECTOR column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE admins (
            id            SERIAL PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE documents (
            id           SERIAL PRIMARY KEY,
            filename     TEXT NOT NULL,
            file_path    TEXT NOT NULL,
            file_type    TEXT NOT NULL DEFAULT 'pdf',
            status       TEXT NOT NULL DEFAULT 'processing',
            chunk_count  INTEGER NOT NULL DEFAULT 0,
            uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE images (
            id                SERIAL PRIMARY KEY,
            filename          TEXT NOT NULL,
            file_path         TEXT NOT NULL,
            image_url         TEXT NOT NULL,
            description       TEXT,
            category          TEXT,
            structured_fields JSONB,
            status            TEXT NOT NULL DEFAULT 'processing',
            uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE chunks (
            id          SERIAL PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id   INTEGER NOT NULL,
            content     TEXT NOT NULL,
            embedding   VECTOR(1536) NOT NULL,
            tsv         TSVECTOR,
            metadata    JSONB NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE questions (
            id                  SERIAL PRIMARY KEY,
            question_text       TEXT NOT NULL,
            answer_text         TEXT NOT NULL,
            is_answered         BOOLEAN NOT NULL,
            retrieved_chunk_ids INTEGER[] NOT NULL DEFAULT '{}',
            cited_chunk_ids     INTEGER[] NOT NULL DEFAULT '{}',
            image_shown         BOOLEAN NOT NULL DEFAULT false,
            topic               TEXT,
            latency_ms          INTEGER,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # HNSW, not ivfflat: ivfflat trains centroids at build time and degrades
    # when created on an empty table (spec §7 notes).
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX idx_chunks_tsv ON chunks USING gin (tsv)")
    op.execute("CREATE INDEX idx_chunks_source ON chunks (source_type, source_id)")
    op.execute("CREATE INDEX idx_questions_created ON questions (created_at)")

    # Keep tsv in sync with content, always with the explicit 'english' config —
    # the query side (spec §8.3) uses plainto_tsquery('english', ...).
    op.execute(
        """
        CREATE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.tsv := to_tsvector('english', NEW.content);
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_chunks_tsv
        BEFORE INSERT OR UPDATE OF content ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_update()")
    op.execute("DROP TABLE IF EXISTS questions")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS images")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS admins")
