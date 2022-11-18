# helper funtions
import json
import re
import sys
from datetime import datetime, timedelta
from random import choice

import pandas as pd
from telegram import Update

import models as db
from constants import *


def get_data_from_google() -> dict:
    formats_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Formats"
    words_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Words"
    formats_pd = pd.read_csv(formats_url).to_dict()
    words_pd = pd.read_csv(words_url).to_dict()
    data = {}
    new_formats = []
    for key in formats_pd["format"]:
        new_formats.append(formats_pd["format"][key])
    data["formats"] = tuple(new_formats)

    data["words"] = {}
    for key in [w for w in words_pd if w.find("Unnamed") == -1]:
        new_words = []
        for word_key in words_pd[key]:
            word = words_pd[key][word_key]
            if isinstance(word, str):
                new_words.append(word)
        data["words"][key] = new_words
    return data


def get_time_of_day() -> str:
    now = datetime.now(PACIFIC_TZ)
    if now.hour < 12:
        return "morning"
    elif now.hour < 18:
        return "afternoon"
    else:
        return "evening"


def generate_message(data: dict):
    words = data["words"]
    the_message = str(choice(data["formats"]))
    tod = get_time_of_day()
    vars_to_replace = re.findall(r'\%[a-z_]+\%', the_message)
    for index, current_var in enumerate(vars_to_replace):
        key = str(current_var).replace('%', '')
        if key == 'tod':
            selected_word = tod
        elif key == 'reminder':
            selected_word = words[key][0] if tod == 'morning' else str(choice(words[key][1:])).strip()
        else:
            selected_word = str(choice(words[key])).strip()
        if key == 'greeting' and index != 0: 
            selected_word = selected_word.lower()
        the_message = the_message.replace(current_var, selected_word, 1)

    return the_message.replace('%tod%', tod)


def get_current_time_string() -> str:
    return datetime.now(PACIFIC_TZ).strftime("%H:%M:%S")


def get_system_messages() -> dict[str]:
    with open(MESSAGES_FILE_PATH, "r") as msg_file:
        return json.load(msg_file)


def get_chats_from_file() -> dict:
    try:
        with open(CHATS_FILE_PATH, "r") as chat_file:
            chats = json.load(chat_file)
    except Exception:
        chats = {}
    
    new_chats = {}
    for chat_id in chats:
        # convert all chat_id dictionary keys saved as strings to numbers.
        if isinstance(chat_id, str) and chat_id.lstrip('-').isnumeric():
            new_chats[int(chat_id)] = chats[chat_id]
        else:
            new_chats[chat_id] = chats[chat_id]
    return new_chats


def parse_time(time_string: str) -> datetime:
    time_string = time_string.lower().strip()
    now = datetime.now(tz=PACIFIC_TZ).replace(microsecond=0)
    match_in = re.search(TIME_PATTERN_IN, time_string)
    match_12 = re.search(TIME_PATTERN_12H, time_string)
    match_24 = re.search(TIME_PATTERN_24H, time_string)
    seconds = 0
    if re.search(r"midnight", time_string):
        hours = 0
        minutes = 0
        am = True
    elif re.search(r"noon", time_string):
        hours = 12
        minutes = 0
        am = False
    elif match_in:
        how_many = int(match_in[1])
        if how_many < 1:
            return False
        units = match_in[2]
        if units.startswith("min"):
            now += timedelta(minutes=how_many)
        elif units.startswith("hour"):
            now += timedelta(hours=how_many)
        elif units.startswith("day"):
            now += timedelta(days=how_many)
        elif units.startswith("week"):
            now += timedelta(days=how_many*7)
        return now
    elif match_12: 
        hours = int(match_12[1])
        minutes = int(match_12[2] or 0)
        am = match_12[3][0] == "a"
        if hours == 12 and am: hours = 0
        elif hours < 12 and not am: hours += 12
    elif match_24: 
        hours = int(match_24[1])
        minutes = int(match_24[2])
    else:
        return False
    if hours > 23 or minutes > 59: return False
    add_days = 1 if (hours * 60 + minutes) < (now.hour * 60 + now.minute) else 0
    return now.replace(hour=hours, minute=minutes, second=seconds) + timedelta(days=add_days)


def parse_date(date_string:str) -> datetime:
    date_string = date_string.lower()
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)
    date_match_intl = re.search(DATE_PATTERN_INTL, date_string)
    date_match_us = re.search(DATE_PATTERN_US, date_string)
    if date_string.endswith("day"):
        for i in range(1,8):
            check_day = (now + timedelta(days=i))
            if date_string.lower() == check_day.strftime("%A").lower():
                return check_day
        return False
    elif date_string == "tomorrow":
        return now + timedelta(days=1)
    elif date_match_intl != None:
        y = int(date_match_intl[1])
        m = int(date_match_intl[2])
        d = int(date_match_intl[3])
    elif date_match_us:
        m = int(date_match_us[1])
        d = int(date_match_us[2])
        try: 
            y = int(date_match_us[3])
        except Exception: 
            y = now.year
            if now.replace(month=m, day=d) < now:
                y += 1
    try: return now.replace(year=y, month=m, day=d)
    except Exception: return False 


async def is_user_chat_admin(update: Update):
    if update.effective_chat.id >= 0: return True #private
    admins = await update.effective_chat.get_administrators()
    for admin in admins:
        if admin.user.id == update.effective_user.id: return True
    return False


def get_token():
    with open("token.txt", "r") as tkfile:
        token = tkfile.read().strip()
    if token: return token
    else: sys.exit("Create a file called token.txt and add your bot token to it.")


def parse_reminder(chat_id:int, from_user:str, args:tuple[str]) -> db.Reminder:
    now = datetime.now(tz=PACIFIC_TZ).replace(microsecond=0)
    reminder = db.Reminder(
        chat_id=chat_id,
        when=now,
        from_user=from_user,
        target_user=args[0],
        subject=""
    )
    indicies = {}
    when = now 
    keywords = {"at": 2,"in": 2,"on": 1,"tomorrow": 0}
    skip_next = False
    for index,word in enumerate([a.lower() for a in args]):
        #get ranges for each part of the sentence structure
        if skip_next:
            skip_next = False
            continue
        if word in keywords:
            cur_kw = word
            if not word in indicies:
                indicies[word] = {"index": index, "from": -1, "to": -1, "value": "", "finished": False}
            if word == "tomorrow":
                indicies[word] = {"index": index, "from": index, "to": index+1, "value": word, "finished": True}
                if when.date() == now.date():
                    when += timedelta(days=1)
        elif indicies and cur_kw in indicies:
            if indicies[cur_kw]["finished"]: continue

            if indicies[cur_kw]["from"] == -1: indicies[cur_kw]["from"] = index
            indicies[cur_kw]["to"] = index + 1
            cur_kw_args = args[indicies[cur_kw]["from"]:indicies[cur_kw]["to"]]
            value = " ".join(cur_kw_args)
            indicies[cur_kw]["value"] = value
            d,t = (parse_date(value), parse_time(value))
            greedy = False if index + 1 >= len(args) else parse_time(value + " " + args[index+1])
            if cur_kw in["at","in"] and (t or greedy):
                indicies[cur_kw]["finished"] = True
                if greedy:
                    t = greedy
                    skip_next = True
                    indicies[cur_kw]["to"] += 1 
                if t.date() != now.date() and when.date() == now.date(): 
                    #if parse_time modifies date, and the date hasn't been modified elsewhere
                    when = t                   
                else:
                    when = when.replace(hour=t.hour, minute=t.minute, second=t.second)
            elif cur_kw == "on" and d:
                indicies[cur_kw]["finished"] = True
                when = when.replace(year=d.year,  month=d.month, day=d.day)
            elif cur_kw == "in" and len(cur_kw_args) < 2:
                pass
            else: #couldn't parse kw, likely used in subject. i.e. yodel 'at' turtles
                indicies.pop(cur_kw)
    
    if not "at" in indicies and not "in" in indicies:
        return False
    
    if reminder.target_user.lower() == "me": reminder.target_user = reminder.from_user
    else: reminder.target_user = reminder.target_user.lstrip("@")

    subject_words = args.copy()
    for key in indicies:
        i = indicies[key]
        if i["from"] == -1: i["to"] = i["index"] + 1
        elif i["to"] == -1: i["to"] = i["from"] + 1
        for j in range(i["index"],i["to"]):
            subject_words[j] = ""
    reminder.subject = " ".join([w for w in subject_words[1:] if w != ""])
    reminder.when = when
    reminder.update_job_name()
    return reminder
