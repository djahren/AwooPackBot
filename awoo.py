import logging, re, sys
from constants import *
from functions import *
from telegram import Update,Chat
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes
from datetime import time,timedelta
from random import choice

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

data = {}
chats = {}
msg = get_system_messages()

def register_daily_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id, hours, minutes = 0):
    first_occurance = time(hour=hours, minute=minutes, tzinfo=PACIFIC_TZ)
    job_name = get_job_name(chat_id, hours, minutes)
    return context.job_queue.run_repeating(send_reminder_job, interval=timedelta(days=1), 
        first=first_occurance, chat_id=chat_id, name=job_name)

def remove_scheduled_job(context: ContextTypes.DEFAULT_TYPE, job_name: str):
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        logging.info(f"Removing job: {job_name}")

def add_chat_if_not_exist(chat: Chat):
    if not chat.id in chats:
        title = chat.title if chat.title else f"{chat.first_name} {chat.last_name}"
        chats[chat.id] = {
            "title": title,
            "daily_reminders": [],
            "onetime_reminders": [],
            "time_zone": "America/Los_Angeles",
            "stop_armed": 0
        }
        save_chats_to_file(chats)

def set_stop_armed(chat_id, armed):
    global chats
    if chat_id in chats: 
        chats[chat_id]["stop_armed"] = 1 if armed else 0
        return True
    else: return False

def remove_chat(chat_id: int):
    chats.pop(chat_id)
    save_chats_to_file(chats)

def load_chats(application):
    global chats
    chats = get_chats_from_file()
    for chat_id in chats: #load reminders
        logging.info(chat_id)
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=chat_id)
        for daily_id in chats[chat_id]["daily_reminders"]:
            register_daily_reminder(context=context, chat_id=chat_id, 
                hours=int(daily_id.split("_")[1]), minutes=int(daily_id.split("_")[2]))

async def awoo_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.is_bot: return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=choice(msg["awoo"]), 
        reply_to_message_id=update.message.id) 

async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None: #called by scheduled job
    job = context.job
    message = generate_message(data)
    logging.info(f"Sending message via job: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=job.chat_id, text=message)  

async def send_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = generate_message(data)
    logging.info(f"Sending message: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def list_daily_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chats:
        reminders = chats[chat_id]["daily_reminders"]
        if reminders:
            reminders_list_msg = "This chat has the following reminders set:\n"
            for re_key in reminders: 
                hours = int(re_key.split("_")[1])
                minutes = int(re_key.split("_")[2])
                reminders_list_msg += f"{hours:02d}:{minutes:02d}\n"
            await context.bot.send_message(chat_id=chat_id, text=reminders_list_msg)       
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])        

async def set_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.args:
        matches = match_time_string(time_string=context.args[0])
        if matches:
            hours,minutes = matches
            add_chat_if_not_exist(update.effective_chat)
            job_name = get_job_name(chat_id, hours, minutes)
            if not job_name in chats[chat_id]["daily_reminders"]:
                job = register_daily_reminder(context=context, chat_id=chat_id, hours=hours, minutes=minutes)
                if job: 
                    chats[chat_id]["daily_reminders"].append(job_name)
                    save_chats_to_file(chats)
                    await context.bot.send_message(chat_id=chat_id, text=msg["cmd_set_daily_succcess"])
                else:
                    await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_schedule_jobs"])
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_already_exists"])
            return  
    await context.bot.send_message(chat_id=chat_id, text=msg["err_24h_format"])

async def stop_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.args:
        matches = match_time_string(time_string=context.args[0])
        if matches:
            hours,minutes = matches
            job_name = get_job_name(chat_id, hours=hours, minutes=minutes)
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            if current_jobs:
                job = current_jobs[0]
                job.schedule_removal()
                logging.info(f"Removing job: {job_name}")
                await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_daily_success"])
                if job_name in chats[chat_id]["daily_reminders"]:
                    chats[chat_id]["daily_reminders"].remove(job_name)
                    save_chats_to_file(chats)
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_24h_format"])

async def update_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global data
    data = get_data_from_google()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_update"])

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_help"])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    add_chat_if_not_exist(update.effective_message.chat)
    await context.bot.send_message(chat_id=chat_id, text=msg["cmd_start"])

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if chat_id in chats: 
        set_stop_armed(chat_id=chat_id,armed=True)
        await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])

async def stop_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if chat_id in chats: 
        if chats[chat_id]["stop_armed"] == 1:
            for job_name in chats[chat_id]["daily_reminders"]:
                remove_scheduled_job(context=context, job_name=job_name)
            remove_chat(chat_id=chat_id)
            await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_confirm"])
        else: 
            await context.bot.send_message(chat_id=chat_id, text=msg["err_stop_not_armed"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_unknown"])

async def parse_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stop_armed(chat_id=update.effective_message.chat_id, armed=False)
    message = update.message.text
    if update.effective_user.is_bot: return

if __name__ == '__main__':
    data = get_data_from_google()
    #open token.txt
    token = ""
    with open("token.txt", "r") as tkfile:
        token = tkfile.read().strip()
    if token == "":
        sys.exit("Create a file called token.txt and add your bot token to it.")
    
    application = ApplicationBuilder().token(token).build()
    load_chats(application)
    application.add_handler(CommandHandler('awoo', awoo_reply))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('getmessage', send_message_command))
    application.add_handler(CommandHandler('listdailyreminders', list_daily_reminders_command))
    application.add_handler(CommandHandler('setdailyreminder', set_daily_reminder_command))
    application.add_handler(CommandHandler('stopdailyreminder', stop_daily_reminder_command))
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('stop', stop_command))
    application.add_handler(CommandHandler('stopconfirm', stop_confirm_command))
    application.add_handler(CommandHandler('update', update_data_command))
    application.add_handler(MessageHandler(filters.Regex(re.compile(AWOO_PATTERN, re.I)), awoo_reply))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), parse_all_messages))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()
