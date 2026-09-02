import importlib


def test_database_uses_environment_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./bookservice.db")

    import src.database as database_module

    reloaded_module = importlib.reload(database_module)

    assert reloaded_module.SQLALCHEMY_DATABASE_URL == "sqlite+aiosqlite:///./bookservice.db"
