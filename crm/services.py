"""Логика CRM без веба: права доступа, воронка, задачи, отчёты."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OPEN_STAGES, STAGE_TITLES, Client, Deal, DealEvent, Role, Stage, Task, User
from .security import hash_password, verify_password


class NotAllowed(Exception):
    """Нет прав или объекта не существует — для пользователя это одно и то же (404)."""


# ---------- пользователи ----------

def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


def create_user(db: Session, name: str, email: str, password: str, role: Role = Role.MANAGER) -> User:
    email = email.strip().lower()
    if len(password) < 8:
        raise ValueError("Пароль — минимум 8 символов")
    if db.scalar(select(User.id).where(User.email == email)):
        raise ValueError("Такой email уже есть")
    user = User(name=name.strip(), email=email, password_hash=hash_password(password), role=role.value)
    db.add(user)
    db.flush()
    return user


def managers(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)))


# ---------- доступ к сделкам ----------

def deals_query(user: User):
    q = select(Deal)
    if not user.is_admin:
        q = q.where(Deal.owner_id == user.id)
    return q


def get_deal(db: Session, user: User, deal_id: int) -> Deal:
    deal = db.get(Deal, deal_id)
    if deal is None or (not user.is_admin and deal.owner_id != user.id):
        raise NotAllowed
    return deal


def board(db: Session, user: User, owner_id: int | None = None) -> dict[str, list[Deal]]:
    q = deals_query(user).order_by(Deal.created_at.desc())
    if owner_id and user.is_admin:
        q = q.where(Deal.owner_id == owner_id)
    columns: dict[str, list[Deal]] = {s: [] for s in STAGE_TITLES}
    for deal in db.scalars(q):
        columns[deal.stage].append(deal)
    return columns


def create_deal(db: Session, user: User, title: str, client_id: int, amount: int, owner_id: int | None = None) -> Deal:
    if db.get(Client, client_id) is None:
        raise NotAllowed
    owner = owner_id if (user.is_admin and owner_id) else user.id      # менеджер создаёт только себе
    deal = Deal(title=title.strip(), client_id=client_id, owner_id=owner, amount=max(0, amount))
    db.add(deal)
    db.flush()
    db.add(DealEvent(deal_id=deal.id, user_id=user.id, text="Сделка создана"))
    return deal


def move_deal(db: Session, user: User, deal_id: int, stage: Stage) -> Deal:
    deal = get_deal(db, user, deal_id)
    if deal.stage == stage.value:
        return deal
    old = deal.stage
    deal.stage = stage.value
    deal.closed_at = datetime.now() if stage.value not in OPEN_STAGES else None
    db.add(DealEvent(deal_id=deal.id, user_id=user.id,
                     text=f"Этап: {STAGE_TITLES[old]} → {STAGE_TITLES[stage.value]}"))
    db.flush()
    return deal


def add_note(db: Session, user: User, deal_id: int, text: str) -> None:
    deal = get_deal(db, user, deal_id)
    text = text.strip()
    if text:
        db.add(DealEvent(deal_id=deal.id, user_id=user.id, text=text))


# ---------- клиенты ----------

def search_clients(db: Session, q: str = "") -> list[Client]:
    """Поиск без учёта регистра. Сравниваем в Python: SQLite понимает регистр
    только у латиницы, и «флор» не нашёл бы «Флора»."""
    clients = list(db.scalars(select(Client).order_by(Client.name)))
    needle = q.strip().casefold()
    if not needle:
        return clients
    return [c for c in clients
            if any(needle in (v or "").casefold() for v in (c.name, c.contact, c.phone, c.email))]


def client_deals(db: Session, user: User, client: Client) -> list[Deal]:
    return list(db.scalars(deals_query(user).where(Deal.client_id == client.id).order_by(Deal.created_at.desc())))


# ---------- задачи ----------

def tasks_for(db: Session, user: User, show_done: bool = False) -> list[Task]:
    q = select(Task).order_by(Task.done, Task.due)
    if not user.is_admin:
        q = q.where(Task.owner_id == user.id)
    if not show_done:
        q = q.where(Task.done.is_(False))
    return list(db.scalars(q))


def complete_task(db: Session, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None or (not user.is_admin and task.owner_id != user.id):
        raise NotAllowed
    task.done = True
    db.flush()
    return task


# ---------- отчёты ----------

def report(db: Session, user: User, today: date | None = None) -> dict:
    """Цифры для главной: воронка, выигранное за месяц, конверсия, по менеджерам."""
    today = today or date.today()
    month_start = datetime(today.year, today.month, 1)
    deals = list(db.scalars(deals_query(user)))

    funnel = {s: {"title": t, "count": 0, "amount": 0} for s, t in STAGE_TITLES.items()}
    for d in deals:
        funnel[d.stage]["count"] += 1
        funnel[d.stage]["amount"] += d.amount

    closed = [d for d in deals if d.stage in (Stage.WON.value, Stage.LOST.value)]
    won = [d for d in closed if d.stage == Stage.WON.value]
    won_month = [d for d in won if d.closed_at and d.closed_at >= month_start]

    per_manager: dict[int, dict] = defaultdict(lambda: {"name": "", "open": 0, "open_amount": 0, "won_month": 0,
                                                        "won_count": 0, "closed": 0})
    for d in deals:
        row = per_manager[d.owner_id]
        row["name"] = d.owner.name
        if d.stage in OPEN_STAGES:
            row["open"] += 1
            row["open_amount"] += d.amount
        else:
            row["closed"] += 1
            if d.stage == Stage.WON.value:
                row["won_count"] += 1
                if d.closed_at and d.closed_at >= month_start:
                    row["won_month"] += d.amount
    for row in per_manager.values():
        row["conversion"] = round(100 * row["won_count"] / row["closed"]) if row["closed"] else 0

    tasks = tasks_for(db, user)
    return {
        "funnel": funnel,
        "open_count": sum(funnel[s]["count"] for s in OPEN_STAGES),
        "open_amount": sum(funnel[s]["amount"] for s in OPEN_STAGES),
        "won_month_amount": sum(d.amount for d in won_month),
        "won_month_count": len(won_month),
        "conversion": round(100 * len(won) / len(closed)) if closed else 0,
        "overdue": sum(1 for t in tasks if t.overdue),
        "today_tasks": [t for t in tasks if t.due <= today][:6],
        "managers": sorted(per_manager.values(), key=lambda r: -r["won_month"]),
    }
