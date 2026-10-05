import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from crm import db as dbmod
from crm.app import app
from crm.db import get_db
from crm.models import Base
from crm.seed import DEMO_PASSWORD, seed


@pytest.fixture
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        seed(s)
        s.commit()
    return factory


@pytest.fixture
def db(Session):
    with Session() as s:
        yield s


@pytest.fixture
def client_for(Session, monkeypatch):
    """Веб-клиент, уже вошедший под нужным пользователем; база — в памяти с демо-данными."""
    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(dbmod, "init_db", lambda: None)

    def make(email: str | None):
        c = TestClient(app)
        if email:
            r = c.post("/login", data={"email": email, "password": DEMO_PASSWORD}, follow_redirects=False)
            assert r.status_code == 303
        return c

    yield make
    app.dependency_overrides.clear()
