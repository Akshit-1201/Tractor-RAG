from sqlalchemy import text

EXPECTED_TABLES = {"admins", "documents", "images", "chunks", "questions"}


def test_migration_creates_tables(db_engine):
    with db_engine.connect() as conn:
        vector_ext = conn.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        assert vector_ext == 1, "pgvector extension missing"

        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
        }
        assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"

        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        }
        for expected in (
            "idx_chunks_embedding",
            "idx_chunks_tsv",
            "idx_chunks_source",
            "idx_questions_created",
        ):
            assert expected in indexes, f"missing index: {expected}"
