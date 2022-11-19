import models as db
from constants import CHATS_FILE_PATH, PACIFIC_TZ, DAILY, ONETIME
import json
from datetime import datetime
from os.path import exists
import sys

# import json
# create db connection
# loop through json chats to create chat objects
# loop through chats to create reminder objects


def get_chats_from_file() -> dict:
    try:
        with open(CHATS_FILE_PATH, "r") as chat_file:
            chats = json.load(chat_file)
    except Exception:
        chats = {}

    new_chats = {}
    for chat_id in chats:  # convert all chat_id dictionary keys saved as strings to numbers.
        if isinstance(chat_id, str) and chat_id.lstrip('-').isnumeric():
            new_chats[int(chat_id)] = chats[chat_id]
        else:
            new_chats[chat_id] = chats[chat_id]
    return new_chats


def dict_to_date(dict_object: dict) -> datetime:
    return datetime(
        year=dict_object["year"],
        month=dict_object["month"],
        day=dict_object["day"],
        hour=dict_object["hour"],
        minute=dict_object["minute"],
        second=dict_object["second"],
        tzinfo=PACIFIC_TZ
    )


if exists("data/chats.db"):
    sys.exit("data/chats.db already exists. Please rename or remove it before running this importer.")
chats = get_chats_from_file()
session = db.Session()
db.init_db()
for chat_id in chats:
    chat_json = chats[chat_id]
    chat = db.Chat(
        chat_id=chat_id,
        title=chat_json["title"],
    )
    session.add(chat)
    for daily in chat_json[DAILY]:
        (cid, h, m) = str(daily).split("_")
        reminder = db.Reminder(
            chat_id=chat_id,
            when=datetime.now(tz=PACIFIC_TZ).replace(
                hour=int(h),
                minute=int(m),
                second=0,
                microsecond=0
            ),
            from_user="Imported"
        )
        session.add(reminder)
    for onetime_id in chat_json[ONETIME]:
        r = chat_json[ONETIME][onetime_id]
        reminder = db.Reminder(
            chat_id=chat_id,
            from_user=r["from"],
            target_user=r["target"],
            subject=r["subject"],
            when=dict_to_date(r["when"])
        )
        session.add(reminder)
    session.commit()
