from datetime import datetime
import random
import models as db


session = db.Session()
db.init_db()

# chat = db.Chat(random.randint(0,32000),"Test")
# session.add(chat)
# reminder = db.Reminder(chat_id=chat.id, datetime=datetime.now(), from_user="DFTBAhren",)
# session.add(reminder)
# reminder = db.Reminder(chat_id=chat.id, datetime=datetime.now(), from_user="DFTBAhren", 
#     target_user="Test", subject="Fuck some shit up, bruh")
# session.add(reminder)
# session.commit()

chats:list[db.Chat] = session.query(db.Chat).all()

for c in chats: 
    print(repr(c))
    print(c.onetime_reminders)
    print(c.daily_reminders)

