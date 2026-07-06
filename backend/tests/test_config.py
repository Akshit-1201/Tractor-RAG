from app.config import Settings


def test_config_loads(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_TOP_K", "5")
    monkeypatch.setenv("ADMIN_USERNAME", "boss")
    monkeypatch.setenv("IMAGE_SIMILARITY_THRESHOLD", "0.5")

    s = Settings(_env_file=None)

    assert s.RETRIEVAL_TOP_K == 5
    assert s.ADMIN_USERNAME == "boss"
    assert s.IMAGE_SIMILARITY_THRESHOLD == 0.5
    # defaults survive when env is silent
    assert s.EMBEDDING_MODEL == "text-embedding-3-small"
