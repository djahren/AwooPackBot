#helper funtions
import json
import re
from datetime import datetime, timedelta
from random import choice

import pandas as pd
from telegram import Update

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

def  get_time_of_day() -> str:
    now = datetime.now(PACIFIC_TZ)
    if now.hour < 12:   return "morning" 
    elif now.hour < 18: return "afternoon"
    else:               return "evening"

def generate_message(data: dict):
    words = data["words"]
    the_message = str(choice(data["formats"])) #pick a format
    tod = get_time_of_day()
    vars_to_replace = re.findall(r'\%[a-z_]+\%',the_message) #get all variables
    for index, current_var in enumerate(vars_to_replace): #loop through and replace each one
        key = str(current_var).replace('%','')
        if key == 'tod':
            selected_word = tod
        elif key == 'reminder': #set the reminder to the first reminder if it's morning, else pick at random
            selected_word = words[key][0] if tod == 'morning' else str(choice(words[key][1:])).strip()
        else:
            selected_word = str(choice(words[key])).strip() #select random word for each variable
        if key == 'greeting' and index != 0: 
            selected_word = selected_word.lower()
        the_message = the_message.replace(current_var, selected_word, 1)

    return the_message.replace('%tod%', tod) #return message and replace %tod% if it exists

def get_recurring_job_name(chat_id:int, hours:int, minutes:int) -> str:
    return f"{chat_id}_{hours}_{minutes}"

def get_onetime_job_name(chat_id:int, reminder:dict)->str:
    return f"{chat_id}_{reminder['from']}_{reminder['when']['month']}_{reminder['when']['day']}_{reminder['when']['hour']}_{reminder['when']['minute']}"

def get_current_time_string() -> str:
    return datetime.now(PACIFIC_TZ).strftime("%H:%M:%S")

def get_system_messages() -> dict:
    with open(MESSAGES_FILE_PATH, "r") as msg_file:
        return json.load(msg_file)

def save_chats_to_file(chats: dict):
    with open(CHATS_FILE_PATH, "w") as chat_file:
        chat_file.write(json.dumps(chats, indent=4))

def get_chats_from_file() -> dict:
    try:
        with open(CHATS_FILE_PATH, "r") as chat_file:
            chats = json.load(chat_file)
    except:
        chats = {}
    
    new_chats = {}
    for chat_id in chats: #convert all chat_id dictionary keys saved as strings to numbers.
        if isinstance(chat_id, str) and chat_id.lstrip('-').isnumeric():
            new_chats[int(chat_id)] = chats[chat_id]
        else:
            new_chats[chat_id] = chats[chat_id]
    return new_chats

def parse_time(time_string:str) -> datetime:
    time_string = time_string.lower().strip()
    now = datetime.now(tz=PACIFIC_TZ)
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
        if how_many < 1: return False
        units = match_in[2]
        if units.startswith("min"): now += timedelta(minutes=how_many)
        elif units.startswith("hour"): now += timedelta(hours=how_many)
        elif units.startswith("day"): now += timedelta(days=how_many)
        elif units.startswith("week"): now += timedelta(days=how_many*7)
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
    now = datetime.now()
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
        except: 
            y = now.year
            if now.replace(month=m, day=d) < now:
                y += 1
    try: return now.replace(year=y, month=m, day=d)
    except: return False 

def date_to_dict(datetime_object:datetime) -> dict:
    return {
        "year": datetime_object.year, "month": datetime_object.month, "day": datetime_object.day,
        "hour": datetime_object.hour, "minute": datetime_object.minute, "second": datetime_object.second,
    }

def dict_to_date(dict_object:dict) -> datetime:
    return datetime(year=dict_object["year"], month=dict_object["month"], day=dict_object["day"],
        hour=dict_object["hour"], minute=dict_object["minute"], second=dict_object["second"], tzinfo=PACIFIC_TZ)

async def is_user_chat_admin(update: Update):
    if update.effective_chat.id >= 0: return True #private
    admins = await update.effective_chat.get_administrators()
    for admin in admins:
        if admin.user.id == update.effective_user.id: return True
    return False

def format_onetime_reminder(reminder):
    when = dict_to_date(reminder['when'])
    current_year = datetime.now().year
    d = when.strftime("%m/%d") if when.year == current_year else when.strftime("%m/%d/%y") 
    t = when.strftime('%I:%M %p')
    return f"{d} @ {t} for {reminder['target']}: {reminder['subject']}"