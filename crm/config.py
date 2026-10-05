import os

DATABASE_URL = os.getenv("CRM_DATABASE_URL", "sqlite:///./crm.db")
# секрет для подписи cookie сессии — на сервере обязательно свой
SECRET_KEY = os.getenv("CRM_SECRET_KEY", "dev-secret-change-me")
