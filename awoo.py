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
        set_stop_armed(chat_id=chat_id, armed=False)
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=chat_id)
        for daily_id in chats[chat_id]["daily_reminders"]:
            register_daily_reminder(context=context, chat_id=chat_id, 
                hours=int(daily_id.split("_")[1]), minutes=int(daily_id.split("_")[2]))

async def awoo_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.is_bot: return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=choice(data["words"]["awoo"]), 
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
            if hours > 23 or minutes > 59:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_too_much_time"])
                return
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

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_more_info"])
        return
    
    print(context.args)
    reminder = {
        "from": update.effective_user.username,
        "target": context.args[0],
        "subject": "",
        "when": {}
    }
    indicies = {}
    indicies_order = []
    keys = ["to","at","on","in","tomorrow"]
    for index,arg in enumerate([a.lower() for a in context.args]):
        #get ranges for each part of the sentence structure
        if arg in keys:
            indicies[arg] = {
                "index": index,
                "from": -1,
                "to": -1,
                "value": ""
            }
            indicies_order.append(arg)
        else:
            if indicies:
                i = indicies_order[len(indicies)-1]
                if indicies[i]["from"] == -1:
                    indicies[i]["from"] = index
                else: indicies[i]["to"] = index

    if not indicies:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_more_info"])
        return

    def get_end_index(item:dict):
        if item["to"] == -1: return item["from"] + 1
        else: return item["to"] + 1

    for key in indicies:
        i = indicies[key]
        indicies[key]["value"] = " ".join(context.args[i["from"]:get_end_index(i)])

    if reminder["target"].lower() == "me": reminder["target"] = f"{reminder['from']}"
    else: reminder["target"] = reminder["target"].lstrip("@")

    if "to" in indicies:
        # reminder["subject"] = " ".join(context.args[indicies["to"]["index"]:get_end_index(indicies["to"])])
        reminder["subject"] = f"to {indicies['to']['value']}"
    else: 
        first_key = indicies_order[0]
        subject_end_index = indicies[first_key]["index"]
        reminder["subject"] = " ".join(context.args[1:subject_end_index])
    
    when = datetime.now()
    if "in" in indicies:
        try: 
            how_many = int(context.args[indicies["in"]["from"]])
            units = context.args[indicies["in"]["from"] + 1].lower()
            if units.startswith("min"):
                when += timedelta(minutes=how_many)
            elif units.startswith("hour"):
                when += timedelta(hours=how_many)
            elif units.startswith("day"):
                when += timedelta(days=how_many)
        except:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])
            return
    elif "at" in indicies:
        when = parse_time(indicies["at"]["value"])
        if not when:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])
            return
        if "on" in indicies:
            on_date = parse_date(indicies["on"]["value"])
            if not on_date:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_date"])
                return
            when = when.replace(year=on_date.year, month=on_date.month, day=on_date.day)
        elif "tomorrow" in indicies:
            when += timedelta(days=1)
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])
        return
    if when < datetime.now():
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_in_past"])
        return

    reminder["when"] = date_to_dict(when)
    await context.bot.send_message(chat_id=chat_id, text=json.dumps(reminder, indent=4))

    # print(indicies)
    print(reminder)

async def remind_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args.insert(0,"me")
    await remind_command(update=update, context=context)

async def time_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        time_string = " ".join(context.args)
        parsed = parse_time(time_string)
        print(parsed)
        if parsed: parsed = parsed.isoformat()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=parsed)

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
    application.add_handler(CommandHandler('remind', remind_command))
    application.add_handler(CommandHandler('remindme', remind_me_command))
    application.add_handler(CommandHandler('time', time_test_command))
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('stop', stop_command))
    application.add_handler(CommandHandler('stopconfirm', stop_confirm_command))
    application.add_handler(CommandHandler('update', update_data_command))
    application.add_handler(MessageHandler(filters.Regex(re.compile(AWOO_PATTERN, re.I)), awoo_reply))
    application.add_handler(MessageHandler(filters.Regex(re.compile(BOT_NAME, re.I)), awoo_reply))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), parse_all_messages))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()
