from commerce_backend.config import Settings


def test_comma_separated_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    configured = Settings(_env_file=None)
    assert configured.cors_origins == ["http://localhost:3000", "http://localhost:5173"]
