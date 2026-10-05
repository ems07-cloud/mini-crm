from datetime import date, datetime

import pytest
from sqlalchemy import select

from crm import services
from crm.models import Deal, Stage, Task, User
from crm.security import hash_password, verify_password
from crm.services import NotAllowed


def user(db, email):
    return db.scalar(select(User).where(User.email == email))


def test_password_hashing():
    h = hash_password("secret-pass")
    assert h.startswith("pbkdf2$") and "secret-pass" not in h
    assert verify_password("secret-pass", h)
    assert not verify_password("wrong", h)
    assert hash_password("secret-pass") != h                      # у каждого пароля своя соль


def test_authenticate(db):
    assert services.authenticate(db, " Anna@Demo.ru ", "demo12345").name == "Анна Ковалёва"
    assert services.authenticate(db, "anna@demo.ru", "nope") is None
    user(db, "anna@demo.ru").is_active = False
    assert services.authenticate(db, "anna@demo.ru", "demo12345") is None   # отключённый не войдёт


def test_manager_sees_only_own_deals_admin_sees_all(db):
    anna, boss = user(db, "anna@demo.ru"), user(db, "boss@demo.ru")
    anna_deals = list(db.scalars(services.deals_query(anna)))
    assert anna_deals and all(d.owner_id == anna.id for d in anna_deals)
    assert len(list(db.scalars(services.deals_query(boss)))) == 15
    igor_deal = db.scalar(select(Deal).where(Deal.owner_id == user(db, "igor@demo.ru").id))
    with pytest.raises(NotAllowed):
        services.get_deal(db, anna, igor_deal.id)
    assert services.get_deal(db, boss, igor_deal.id) is igor_deal


def test_moving_deal_logs_history_and_closing_date(db):
    anna = user(db, "anna@demo.ru")
    deal = db.scalar(select(Deal).where(Deal.owner_id == anna.id, Deal.stage == Stage.TALKS.value))
    services.move_deal(db, anna, deal.id, Stage.WON)
    assert deal.stage == "won" and deal.closed_at is not None
    assert deal.events[0].text == "Этап: Переговоры → Выиграна"
    services.move_deal(db, anna, deal.id, Stage.TALKS)            # вернули в работу — дата закрытия сбрасывается
    assert deal.closed_at is None


def test_manager_creates_deal_only_for_himself(db):
    anna, igor = user(db, "anna@demo.ru"), user(db, "igor@demo.ru")
    deal = services.create_deal(db, anna, "Новый сайт", client_id=1, amount=100000, owner_id=igor.id)
    assert deal.owner_id == anna.id
    boss_deal = services.create_deal(db, user(db, "boss@demo.ru"), "Для Игоря", client_id=1, amount=5, owner_id=igor.id)
    assert boss_deal.owner_id == igor.id


def test_tasks_visibility_and_completion(db):
    anna, igor = user(db, "anna@demo.ru"), user(db, "igor@demo.ru")
    assert all(t.owner_id == anna.id for t in services.tasks_for(db, anna))
    igor_task = db.scalar(select(Task).where(Task.owner_id == igor.id))
    with pytest.raises(NotAllowed):
        services.complete_task(db, anna, igor_task.id)
    assert services.complete_task(db, igor, igor_task.id).done


def test_report_numbers(db):
    boss = user(db, "boss@demo.ru")
    r = services.report(db, boss, today=date.today())
    assert r["open_count"] == 9                                   # 3 новых + 3 в переговорах + 3 с КП
    assert r["open_amount"] == 2_440_000
    assert r["funnel"]["won"]["amount"] == 95000 + 70000 + 150000 + 85000
    assert r["conversion"] == round(100 * 4 / 6)                  # 4 выиграно из 6 закрытых
    assert r["overdue"] == 2
    names = [m["name"] for m in r["managers"]]
    assert set(names) == {"Анна Ковалёва", "Игорь Смирнов"}


def test_client_search(db):
    assert [c.name for c in services.search_clients(db, "флор")] == ["Цветочная студия «Флора»"]
    assert [c.name for c in services.search_clients(db, "000-03")] == ["ИП Карпов (автосервис)"]   # по телефону
    assert [c.contact for c in services.search_clients(db, "VOLKOV@")] == ["Сергей Волков"]      # по email
    assert len(services.search_clients(db, "")) == 12


def test_create_user_validation(db):
    with pytest.raises(ValueError, match="минимум 8"):
        services.create_user(db, "Тест", "t@demo.ru", "short")
    with pytest.raises(ValueError, match="уже есть"):
        services.create_user(db, "Тест", "ANNA@demo.ru", "longpassword")


def test_plural():
    from crm.app import plural
    forms = ("сделка", "сделки", "сделок")
    assert [plural(n, *forms) for n in (0, 1, 2, 5, 11, 21, 22, 112)] == \
        ["сделок", "сделка", "сделки", "сделок", "сделок", "сделка", "сделки", "сделок"]
