from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    DateTime,
    create_engine,
    and_)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

engine = create_engine('sqlite:///data/chats.db', echo=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


class Reminder(Base):
    __tablename__ = "reminder"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    chat_id: int = Column(
        Integer,
        ForeignKey("chat.id"),
        nullable=False,
        index=True)
    name: str = Column(String, nullable=False)
    when: datetime = Column(DateTime(timezone=True), nullable=False)
    chat = relationship("Chat", back_populates="reminders")
    from_user: str = Column(String(100))
    is_daily: bool = Column(Boolean)
    target_user: str = Column(String(100), nullable=True)
    subject: str = Column(String(255), nullable=True)

    def __init__(self, chat_id: Integer, when: datetime, from_user: String,
                 target_user: String = None, subject: String = None):
        self.chat_id = chat_id
        self.when = when
        self.from_user = from_user
        self.target_user = target_user
        self.subject = subject
        self.is_daily = not target_user and not subject
        self.name = self.get_job_name()

    def get_job_name(self):
        rt: datetime = self.when
        if self.is_daily:
            return f"{self.chat_id}_{rt.hour}_{rt.minute}"
        else:
            return f"{self.chat_id}_{self.from_user}_{rt.month}_{rt.day}_{rt.hour}_{rt.minute}"

    def update_job_name(self):
        self.name = self.get_job_name()

    def get_time(self):
        # BUG chat isn't populated
        return self.when.astimezone(tz=ZoneInfo(self.chat.time_zone))

    def format_string(self):
        when = self.when
        if self.is_daily:
            return f"{when.hour:02d}:{when.minute:02d}"
        else:
            current_year = datetime.now().year
            d = when.strftime("%m/%d") if when.year == current_year else when.strftime("%m/%d/%y")
            t = when.strftime('%I:%M %p')
            return f"{d} @ {t} for {self.target_user}: {self.subject}"

    def __repr__(self):
        if self.is_daily:
            more = f"is_daily={self.is_daily}"
        else:
            more = f"target={self.target_user}, subject={self.subject}"
        return f"Reminder({self.name}, {more})"

    def __lt__(self, other):
        if self.is_daily:
            return self.when.hour * 60 + self.when.minute < other.when.hour * 60 + other.when.minute
        else:
            return self.when < other.when

    def __eq__(self, other):
        if isinstance(other, Reminder):
            return self.name == other.name and self.target_user == other.target_user and self.subject == other.subject
        return False


class Chat(Base):
    __tablename__ = "chat"
    id: int = Column(Integer, primary_key=True)
    title: str = Column(String(255))
    time_zone: str = Column(String(100))
    stop_armed: bool = Column(Boolean, default=False)
    reminders: list[Reminder] = relationship(
        "Reminder", back_populates="chat", cascade="all, delete-orphan"
    )
    daily_reminders: list[Reminder] = relationship(
        "Reminder",
        primaryjoin=and_(id == Reminder.chat_id, Reminder.is_daily == True),  # noqa: E712
        viewonly=True,
    )
    onetime_reminders: list[Reminder] = relationship(
        "Reminder",
        primaryjoin=and_(id == Reminder.chat_id, Reminder.is_daily == False),  # noqa: E712
        viewonly=True,
    )

    def __init__(self, chat_id: Integer, title: String,
                 time_zone: String = "America/Los_Angeles"):
        self.id = chat_id
        self.title = title
        self.time_zone = time_zone

    def __repr__(self):
        return f"Chat({self.title}, id={self.id}"
