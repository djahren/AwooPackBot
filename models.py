from datetime import datetime
from operator import and_
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, create_engine, and_
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

engine = create_engine('sqlite:///data/chats.db',)# echo=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False, index=True)
    datetime = Column(DateTime(timezone=True), nullable=False)
    chat = relationship("Chat", back_populates="reminders")
    from_user = Column(String(100))
    is_daily = Column(Boolean)
    target_user = Column(String(100), nullable=True)
    subject = Column(String(255), nullable=True)

    def __init__(self, chat_id:Integer, datetime, from_user:String, is_daily:bool=True, 
            target_user:String=None, subject:String=None):
        self.chat_id = chat_id
        self.datetime = datetime
        self.from_user = from_user
        self.target_user = target_user
        self.subject = subject
        self.is_daily = is_daily

        if subject and target_user: self.is_daily = False
    
    def __repr__(self):
        return f"Reminder({self.get_job_name()}, is_daily={self.is_daily})"

    def get_job_name(self):
        rt:datetime = self.datetime
        if self.is_daily: 
            return f"{self.chat_id}_{rt.hour}_{rt.minute}"
        else: 
            return f"{self.chat_id}_{self.from_user}_{rt.month}_{rt.day}_{rt.hour}_{rt.minute}"

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    time_zone = Column(String(100))
    stop_armed = Column(Boolean, default=False)
    reminders = relationship(
        "Reminder", back_populates="chat", cascade="all, delete-orphan"
    )
    daily_reminders : list[Reminder] = relationship(
        "Reminder",
        primaryjoin=and_(id == Reminder.chat_id, Reminder.is_daily == True),
        viewonly=True,
    )
    onetime_reminders: list[Reminder] = relationship(
        "Reminder",
        primaryjoin=and_(id == Reminder.chat_id, Reminder.is_daily == False),
        viewonly=True,
    )

    def __init__(self, chat_id:Integer, title:String, time_zone:String="America/Los_Angeles"):
        self.id = chat_id
        self.title = title
        self.time_zone = time_zone
    
    def __repr__(self):
        return f"Chat({self.title}, id={self.id})"