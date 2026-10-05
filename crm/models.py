from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    ADMIN = "admin"        # руководитель: видит всё, управляет сотрудниками
    MANAGER = "manager"    # менеджер: свои сделки и задачи


class Stage(str, Enum):
    NEW = "new"
    TALKS = "talks"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"


STAGE_TITLES = {
    Stage.NEW.value: "Новая",
    Stage.TALKS.value: "Переговоры",
    Stage.PROPOSAL.value: "КП отправлено",
    Stage.WON.value: "Выиграна",
    Stage.LOST.value: "Проиграна",
}
OPEN_STAGES = [Stage.NEW.value, Stage.TALKS.value, Stage.PROPOSAL.value]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10), default=Role.MANAGER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))              # компания или человек
    contact: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(50), default="")  # откуда пришёл
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    deals: Mapped[list["Deal"]] = relationship(back_populates="client")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(Integer, default=0)      # рубли
    stage: Mapped[str] = mapped_column(String(10), default=Stage.NEW.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    client: Mapped[Client] = relationship(back_populates="deals")
    owner: Mapped[User] = relationship()
    events: Mapped[list["DealEvent"]] = relationship(back_populates="deal", order_by="DealEvent.at.desc()",
                                                     cascade="all, delete-orphan")

    @property
    def stage_title(self) -> str:
        return STAGE_TITLES[self.stage]


class DealEvent(Base):
    """История сделки: создание, смена этапа, заметки."""

    __tablename__ = "deal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    text: Mapped[str] = mapped_column(Text)

    deal: Mapped[Deal] = relationship(back_populates="events")
    user: Mapped[User] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    due: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), nullable=True)

    owner: Mapped[User] = relationship()
    deal: Mapped[Deal | None] = relationship()

    @property
    def overdue(self) -> bool:
        return not self.done and self.due < date.today()
