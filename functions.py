#helper funtions
from constants import *
import json,re
from random import choice
from datetime import datetime
import pandas as pd

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

def generate_message(data: dict):
    words = data["words"]
    formats = data["formats"]
    the_message = str(choice(formats)) #pick a format
    now = datetime.now(PACIFIC_TZ)
    if now.hour < 12:   tod = "morning" 
    elif now.hour < 18: tod = "afternoon"
    else:               tod = "evening"

    vars_to_replace = re.findall(r'\%[a-z_]+\%',the_message) #get all variables
    for index, current_var in enumerate(vars_to_replace): #loop through and replace each one
        key = str(current_var).replace('%','')
        if key == 'reminder': #set the reminder to the first reminder if it's morning, else pick at random
            selected_word = words[key][0] if tod == 'morning' else str(choice(words[key][1:])).strip()
        else:
            selected_word = str(choice(words[key])).strip() #select random word for each variable
        if key == 'greeting' and index != 0: 
            selected_word = selected_word.lower()
        the_message = the_message.replace(current_var, selected_word, 1)

    return the_message.replace('%tod%', tod) #return message and replace %tod% if it exists

def get_job_name(chat_id: int, hours: int, minutes: int) -> str:
    return f"{chat_id}_{hours}_{minutes}"

def get_current_time_string() -> str:
    return datetime.now(PACIFIC_TZ).strftime("%H:%M:%S")

def match_time_string(time_string) -> tuple:
    matches = re.match(r'([0-2]?\d):??([0-5]\d)', time_string)
    if matches: return (int(matches[1]), int(matches[2]))
    else: return ()

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