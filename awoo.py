import logging, re, sys, json
from random import choice
from zoneinfo import ZoneInfo
from telegram import Update,Chat
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes
from datetime import time,timedelta,datetime
import pandas as pd

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

sheet_id = "1IfGrcY4ntE70fycFRAEtjAvb20ukVf9wTkPzdvtLLKg"
formats_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Formats"
words_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Words"
pacific_tz = ZoneInfo("America/Los_Angeles")
chats_file_path = "data/chats.json"
formats = ()
words = {}
chats = {}

def update_data_from_google():
    global formats
    formats_pd = pd.read_csv(formats_url).to_dict()
    words_pd = pd.read_csv(words_url).to_dict()

    new_formats = []
    for key in formats_pd["format"]:
        new_formats.append(formats_pd["format"][key])
    formats = tuple(new_formats)

    for key in [w for w in words_pd if w.find("Unnamed") == -1]:
        new_words = []
        for word_key in words_pd[key]:
            word = words_pd[key][word_key]
            if isinstance(word, str):
                new_words.append(word)
        words[key] = new_words

def generate_message():
    the_message = str(choice(formats)) #pick a format
    now = datetime.now(pacific_tz)
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

def register_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id):
    m = context.job_queue.run_repeating(send_reminder_job, interval=timedelta(days=1), first=time(hour=8, tzinfo=pacific_tz),chat_id=chat_id, name=f"morning{chat_id}")
    a = context.job_queue.run_repeating(send_reminder_job, interval=timedelta(days=1), first=time(hour=13, tzinfo=pacific_tz),chat_id=chat_id, name=f"afternoon{chat_id}")
    return m and a

def unregister_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id):
    removed_jobs = False
    for job_name in (f"morning{chat_id}",f"afternoon{chat_id}"):
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logging.info(f"Removing job: {job_name}")
            removed_jobs = True
    if removed_jobs:
        remove_chat(chat_id=chat_id)
    return removed_jobs

def save_chat(chat: Chat):
    #add the chat id to the current chats list if it doesn't exist 
    #append the file if the chat id doesn't currently exist in the file with the format <chatid>,<chatname>
    if not chat.id in chats:
        title = chat.title if chat.title else f"{chat.first_name} {chat.last_name}"
        chats[chat.id] = {"title": title}
        save_file()

def save_file():
    with open(chats_file_path, "w") as chat_file:
        chat_file.write(json.dumps(chats, indent=4))

def load_file():
    global chats
    try:
        with open(chats_file_path, "r") as chat_file:
            chats = json.load(chat_file)
    except FileNotFoundError:
        chats = {}
    new_chats = {}
    for chat_id in chats: #convert all chat_id dictionary keys saved as strings to numbers.
        if isinstance(chat_id, str) and chat_id.lstrip('-').isnumeric():
            new_chats[int(chat_id)] = chats[chat_id]
        else:
            new_chats[chat_id] = chats[chat_id]
    chats = new_chats.copy()
    print(chats)

def remove_chat(chat_id):
    chats.pop(chat_id)
    save_file()

def load_chats(application):
    load_file()
    for chat_id in chats:
        logging.info(chat_id)
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=chat_id)
        register_jobs(context=context, chat_id=chat_id)

def get_current_time_string():
    return datetime.now(pacific_tz).strftime("%H:%M:%S")

async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None: #called by scheduled job
    job = context.job
    message = generate_message()
    logging.info(f"Sending message via job: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=job.chat_id, text=message)  

async def send_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = generate_message()
    logging.info(f"Sending message: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def update_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_data_from_google()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I've updated the my database from the Google Sheet.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Available commands:\n/getmessage: gets a random message.\n/help: shows this message.\n/start: registers recurring messages.\n/stop: removes scheduled reminders for this chat.\n/update: updates the bot's data from the database.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    jobs_scheduled = register_jobs(context=context, chat_id=chat_id)
    if jobs_scheduled: 
        save_chat(update.effective_message.chat)
        await context.bot.send_message(chat_id=chat_id, text="Awo0o0o! I've registered morning and afternoon repeating reminders for you.\nUse /help to see a list of commands I respond to.")
    else:
        await context.bot.send_message(chat_id=chat_id, text="I had trouble scheduling the default jobs. 🥺 I'm sorry, please check the logs for more info.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    jobs_stopped = unregister_jobs(context=context, chat_id=chat_id)
    if jobs_stopped: await context.bot.send_message(chat_id=chat_id, text="I've removed the scheduled reminders from this chat.")
    else: await context.bot.send_message(chat_id=chat_id, text="I'm not seeing any scheduled reminders for this chat.")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

if __name__ == '__main__':
    update_data_from_google()
    
    #open token.txt
    token = ""
    with open("token.txt", "r") as tkfile:
        token = tkfile.read().strip()
    if token == "":
        sys.exit("Create a file called token.txt and add your bot token to it.")
    
    application = ApplicationBuilder().token(token).build()
    load_chats(application)
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('stop', stop_command))
    application.add_handler(CommandHandler('getmessage', send_message_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('update', update_data_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()
