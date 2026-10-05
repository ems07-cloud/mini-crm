"""Веб-интерфейс CRM: FastAPI + шаблоны Jinja2, без сборки фронтенда."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import services
from .config import SECRET_KEY
from .db import get_db, init_db
from .export import deals_xlsx
from .models import OPEN_STAGES, STAGE_TITLES, Client, Deal, Role, Stage, Task, User
from .services import NotAllowed

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Мини-CRM", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", max_age=7 * 24 * 3600)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["rub"] = lambda v: f"{int(v or 0):,}".replace(",", " ") + " ₽"


def plural(n: int, one: str, few: str, many: str) -> str:
    """1 сделка, 2 сделки, 5 сделок."""
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


templates.env.filters["plural"] = plural
templates.env.globals.update(STAGE_TITLES=STAGE_TITLES, OPEN_STAGES=OPEN_STAGES, today=date.today)


class LoginRequired(Exception):
    pass


@app.exception_handler(LoginRequired)
async def _to_login(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(NotAllowed)
async def _not_found(request: Request, exc: NotAllowed):
    return templates.TemplateResponse(request, "404.html", {"user": None}, status_code=404)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        raise LoginRequired
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise NotAllowed
    return user


def render(request: Request, name: str, user: User, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, "page": name.split(".")[0], **ctx})


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ---------- вход ----------

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": None, "error": ""})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = services.authenticate(db, email, password)
    if user is None:
        return templates.TemplateResponse(request, "login.html", {"user": None, "error": "Неверный email или пароль"},
                                          status_code=401)
    request.session["uid"] = user.id
    return back("/")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return back("/login")


# ---------- главная ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "dashboard.html", user, r=services.report(db, user))


# ---------- клиенты ----------

@app.get("/clients", response_class=HTMLResponse)
def clients(request: Request, q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "clients.html", user, clients=services.search_clients(db, q), q=q)


@app.post("/clients")
def client_create(name: str = Form(...), contact: str = Form(""), phone: str = Form(""), email: str = Form(""),
                  source: str = Form(""), user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = Client(name=name.strip(), contact=contact.strip(), phone=phone.strip(), email=email.strip(),
                    source=source.strip())
    db.add(client)
    db.commit()
    return back(f"/clients/{client.id}")


@app.get("/clients/{client_id}", response_class=HTMLResponse)
def client_card(request: Request, client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if client is None:
        raise NotAllowed
    return render(request, "client.html", user, client=client, deals=services.client_deals(db, user, client),
                  managers=services.managers(db))


# ---------- сделки ----------

@app.get("/deals", response_class=HTMLResponse)
def deals_board(request: Request, owner: int | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    return render(request, "deals.html", user, columns=services.board(db, user, owner), owner=owner,
                  managers=services.managers(db), clients=services.search_clients(db))


@app.post("/deals")
def deal_create(title: str = Form(...), client_id: int = Form(...), amount: int = Form(0), owner_id: int = Form(0),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    deal = services.create_deal(db, user, title, client_id, amount, owner_id or None)
    db.commit()
    return back(f"/deals/{deal.id}")


@app.get("/deals/{deal_id}", response_class=HTMLResponse)
def deal_card(request: Request, deal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    deal = services.get_deal(db, user, deal_id)
    tasks = list(db.scalars(select(Task).where(Task.deal_id == deal.id).order_by(Task.done, Task.due)))
    return render(request, "deal.html", user, deal=deal, tasks=tasks)


@app.post("/deals/{deal_id}/stage")
def deal_stage(deal_id: int, stage: Stage = Form(...), user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    services.move_deal(db, user, deal_id, stage)
    db.commit()
    return back(f"/deals/{deal_id}")


@app.post("/deals/{deal_id}/note")
def deal_note(deal_id: int, text: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    services.add_note(db, user, deal_id, text)
    db.commit()
    return back(f"/deals/{deal_id}")


@app.get("/export/deals.xlsx")
def export_deals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    deals = list(db.scalars(services.deals_query(user).order_by(Deal.id)))
    return Response(deals_xlsx(deals),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="deals_{date.today()}.xlsx"'})


# ---------- задачи ----------

@app.get("/tasks", response_class=HTMLResponse)
def tasks(request: Request, done: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    deals = list(db.scalars(services.deals_query(user).where(Deal.stage.in_(OPEN_STAGES)).order_by(Deal.title)))
    return render(request, "tasks.html", user, tasks=services.tasks_for(db, user, done), show_done=done, deals=deals)


@app.post("/tasks")
def task_create(title: str = Form(...), due: date = Form(...), deal_id: int = Form(0),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if deal_id:
        services.get_deal(db, user, deal_id)          # к чужой сделке задачу не привязать
    db.add(Task(title=title.strip(), due=due, owner_id=user.id, deal_id=deal_id or None))
    db.commit()
    return back(f"/deals/{deal_id}" if deal_id else "/tasks")


@app.post("/tasks/{task_id}/done")
def task_done(task_id: int, next: str = Form("/tasks"), user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    services.complete_task(db, user, task_id)
    db.commit()
    return back(next if next.startswith("/") else "/tasks")


# ---------- сотрудники (руководитель) ----------

@app.get("/users", response_class=HTMLResponse)
def users(request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    return render(request, "users.html", user, users=list(db.scalars(select(User).order_by(User.name))), error="")


@app.post("/users")
def user_create(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...),
                role: Role = Form(Role.MANAGER), user: User = Depends(admin_only), db: Session = Depends(get_db)):
    try:
        services.create_user(db, name, email, password, role)
    except ValueError as exc:
        return render(request, "users.html", user, users=list(db.scalars(select(User).order_by(User.name))),
                      error=str(exc))
    db.commit()
    return back("/users")
