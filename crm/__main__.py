"""Запуск: python -m crm  →  http://127.0.0.1:8000 (при пустой базе создаст демо-данные)."""
import os

import uvicorn

from .db import SessionLocal, init_db
from .seed import seed

if __name__ == "__main__":
    init_db()
    with SessionLocal() as s:
        if seed(s):
            s.commit()
            print("Создан демо-отдел продаж: boss@demo.ru / anna@demo.ru / igor@demo.ru, пароль demo12345")
    uvicorn.run("crm.app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
