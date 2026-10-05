from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_URL
from .models import Base

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    """Сессия на запрос; коммит делаем явно в обработчиках, которые что-то меняют."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
