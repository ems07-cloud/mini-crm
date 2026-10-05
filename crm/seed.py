"""Демо-данные: отдел продаж веб-студии. Запуск: python -m crm.seed"""
import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Client, Deal, DealEvent, Role, Stage, STAGE_TITLES, Task, User
from .security import hash_password

DEMO_PASSWORD = "demo12345"

# контакты вымышленные: номера +7 999 000-…, почты на example.ru — заведомо ничьи
CLIENTS = [
    ("ООО «СтройМонтаж»", "Сергей Волков", "+7 999 000-01-07", "volkov@example.ru", "сайт"),
    ("Кофейня «Бодрость»", "Ольга Миронова", "+7 999 000-02-14", "olga@example.ru", "рекомендация"),
    ("ИП Карпов (автосервис)", "Дмитрий Карпов", "+7 999 000-03-21", "karpov@example.ru", "Авито"),
    ("Клиника «Здоровье+»", "Наталья Белова", "+7 999 000-04-28", "info@example.ru", "сайт"),
    ("Школа английского «Speak»", "Анастасия Ким", "+7 999 000-05-35", "hello@example.ru", "Telegram"),
    ("ТД «Металлпрофиль»", "Андрей Соколов", "+7 999 000-06-42", "sokolov@example.ru", "холодный звонок"),
    ("Агентство «Домострой»", "Ирина Лебедева", "+7 999 000-07-49", "lebedeva@example.ru", "выставка"),
    ("Фитнес-клуб «Пульс»", "Максим Орлов", "+7 999 000-08-56", "orlov@example.ru", "сайт"),
    ("ООО «ЛогистикПро»", "Елена Григорьева", "+7 999 000-09-63", "eg@example.ru", "рекомендация"),
    ("Цветочная студия «Флора»", "Мария Степанова", "+7 999 000-10-70", "flora@example.ru", "Instagram"),
    ("Юрфирма «Право и Ко»", "Павел Никитин", "+7 999 000-11-77", "nikitin@example.ru", "сайт"),
    ("Пекарня «Хлебный дом»", "Татьяна Зайцева", "+7 999 000-12-84", "hleb-dom@example.ru", "Telegram"),
]

DEALS = [  # (клиент, название, сумма, этап, менеджер, дней назад создана, дней назад закрыта)
    (0, "Корпоративный сайт", 280000, Stage.PROPOSAL, 1, 12, None),
    (1, "Telegram-бот для заказов", 95000, Stage.WON, 1, 30, 2),
    (2, "Сайт-визитка + запись онлайн", 60000, Stage.TALKS, 2, 6, None),
    (3, "Личный кабинет пациента", 450000, Stage.TALKS, 1, 15, None),
    (4, "Лендинг для набора групп", 70000, Stage.WON, 2, 25, 3),
    (5, "Интернет-магазин металлопроката", 620000, Stage.PROPOSAL, 2, 20, None),
    (6, "CRM для агентов", 380000, Stage.NEW, 1, 2, None),
    (7, "Приложение для записи на тренировки", 340000, Stage.LOST, 2, 40, 18),
    (8, "Интеграция сайта с 1С", 150000, Stage.WON, 1, 35, 1),
    (9, "Каталог букетов с оплатой", 120000, Stage.NEW, 2, 1, None),
    (10, "Сайт + блог для юрфирмы", 180000, Stage.TALKS, 1, 9, None),
    (11, "Бот предзаказа выпечки", 85000, Stage.WON, 2, 50, 35),
    (0, "Техподдержка сайта, год", 240000, Stage.NEW, 1, 1, None),
    (3, "Чат-бот записи к врачу", 160000, Stage.LOST, 1, 28, 10),
    (8, "Парсер тарифов перевозчиков", 110000, Stage.PROPOSAL, 2, 7, None),
]

TASKS = [  # (сделка, задача, срок: дней от сегодня, менеджер)
    (0, "Созвон по КП: ответить на вопросы по срокам", 0, 1),
    (3, "Отправить прототип личного кабинета", -2, 1),
    (5, "Уточнить объём каталога и выгрузку из 1С", 1, 2),
    (2, "Перезвонить: ждут смету", -1, 2),
    (6, "Подготовить вопросы к брифу", 2, 1),
    (10, "Отправить примеры блогов", 0, 1),
    (14, "Собрать список перевозчиков для парсинга", 3, 2),
    (9, "Первичная встреча в студии", 1, 2),
]


def seed(db: Session) -> bool:
    if db.scalar(select(User.id).limit(1)):
        return False
    rnd = random.Random(7)
    now = datetime.now().replace(second=0, microsecond=0)
    boss = User(name="Ерем Шахбазян", email="boss@demo.ru", password_hash=hash_password(DEMO_PASSWORD),
                role=Role.ADMIN.value)
    anna = User(name="Анна Ковалёва", email="anna@demo.ru", password_hash=hash_password(DEMO_PASSWORD))
    igor = User(name="Игорь Смирнов", email="igor@demo.ru", password_hash=hash_password(DEMO_PASSWORD))
    db.add_all([boss, anna, igor])
    db.flush()
    owners = {1: anna, 2: igor}

    clients = []
    for i, (name, contact, phone, email, source) in enumerate(CLIENTS):
        c = Client(name=name, contact=contact, phone=phone, email=email, source=source,
                   created_at=now - timedelta(days=60 - i * 3))
        db.add(c)
        clients.append(c)
    db.flush()

    deals = []
    for ci, title, amount, stage, owner, created_ago, closed_ago in DEALS:
        created = now - timedelta(days=created_ago, hours=rnd.randint(1, 8))
        d = Deal(title=title, client_id=clients[ci].id, owner_id=owners[owner].id, amount=amount, stage=stage.value,
                 created_at=created, closed_at=(now - timedelta(days=closed_ago)) if closed_ago is not None else None)
        db.add(d)
        db.flush()
        db.add(DealEvent(deal_id=d.id, user_id=owners[owner].id, at=created, text="Сделка создана"))
        path = [Stage.NEW, Stage.TALKS, Stage.PROPOSAL, Stage.WON]
        reached = path[:path.index(stage) + 1] if stage in path else [Stage.NEW, Stage.TALKS, Stage.LOST]
        for step, (a, b) in enumerate(zip(reached, reached[1:]), 1):
            db.add(DealEvent(deal_id=d.id, user_id=owners[owner].id, at=created + timedelta(days=step * 2),
                             text=f"Этап: {STAGE_TITLES[a.value]} → {STAGE_TITLES[b.value]}"))
        deals.append(d)
    db.add(DealEvent(deal_id=deals[0].id, user_id=anna.id, at=now - timedelta(days=1),
                     text="Отправили КП на 280 000 ₽, клиент сравнивает с двумя студиями. Важны сроки — до конца месяца."))

    for di, title, due_in, owner in TASKS:
        db.add(Task(title=title, due=date.today() + timedelta(days=due_in), owner_id=owners[owner].id,
                    deal_id=deals[di].id))
    db.add(Task(title="Обновить шаблон договора", due=date.today() - timedelta(days=5), owner_id=anna.id, done=True))
    db.flush()
    return True


if __name__ == "__main__":
    from .db import SessionLocal, init_db

    init_db()
    with SessionLocal() as s:
        print("демо-данные созданы" if seed(s) else "база уже заполнена")
        s.commit()
