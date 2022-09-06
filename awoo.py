import logging
import re
import sys
from datetime import time, timedelta
from random import choice

from telegram import Chat, Update
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from constants import *
from functions import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

data = {}
chats = {}
msg = get_system_messages()

def register_daily_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id, hours, minutes = 0):
    first_occurance = time(hour=hours, minute=minutes, tzinfo=PACIFIC_TZ)
    job_name = get_recurring_job_name(chat_id, hours, minutes)
    return context.job_queue.run_repeating(send_daily_reminder_job, interval=timedelta(days=1), 
        first=first_occurance, chat_id=chat_id, name=job_name)

def register_onetime_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id:int, reminder:dict):
    job_name = get_onetime_job_name(chat_id=chat_id, reminder=reminder)
    return context.job_queue.run_once(callback=send_onetime_reminder_job, when=dict_to_date(reminder['when']), 
        chat_id=chat_id, name=job_name, data=reminder)

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
            DAILY: [],
            ONETIME: {},
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

def load_chats(application):
    global chats
    chats = get_chats_from_file()
    for chat_id in chats: #load reminders
        logging.info(chat_id)
        set_stop_armed(chat_id=chat_id, armed=False)
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=chat_id)
        for daily_id in chats[chat_id][DAILY]:
            register_daily_reminder(context=context, chat_id=chat_id, 
                hours=int(daily_id.split("_")[1]), minutes=int(daily_id.split("_")[2]))
        purge_past_reminders(chat_id)
        for onetime_id in chats[chat_id][ONETIME]:
            register_onetime_reminder(context=context, chat_id=chat_id, reminder=chats[chat_id][ONETIME][onetime_id])

def purge_past_reminders(chat_id:int):
    if not chat_id in chats: return
    now = datetime.now(tz=PACIFIC_TZ)
    keys = dict(chats[chat_id][ONETIME]).copy().keys()
    for r_key in keys:
        reminder = chats[chat_id][ONETIME][r_key]
        r_time = dict_to_date(reminder['when'])
        if r_time < now:
            chats[chat_id][ONETIME].pop(r_key)
    save_chats_to_file(chats=chats)

async def send_daily_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None: #called by scheduled job
    job = context.job
    message = generate_message(data)
    logging.info(f"Sending message via job: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=job.chat_id, text=message)  

async def send_onetime_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None: #called by scheduled job
    job = context.job
    try:
        reminder = chats[job.chat_id][ONETIME][job.name]
        from_user = reminder['from'] if reminder['from'] != reminder['target'] else "You"
        message = f"{choice(data['words']['greeting']).replace('%tod%',get_time_of_day())} @{reminder['target']}! {from_user} asked me to remind you {reminder['subject']}."
        await context.bot.send_message(chat_id=job.chat_id, text=message)
    except Exception as e:
        logging.info(f"Failed sending job: {job.name} at {get_current_time_string()} with the following error: {str(e)}")
    finally:
        chats[job.chat_id][ONETIME].pop(job.name)
        save_chats_to_file(chats)

async def awoo_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.is_bot: return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=choice(data["words"]["awoo"]), 
        reply_to_message_id=update.message.id) 

async def get_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = generate_message(data)
    logging.info(f"Sending message: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    purge_past_reminders(chat_id)
    if chat_id in chats:
        reminders_list_msg = ""
        daily_reminders = chats[chat_id][DAILY]
        onetime_reminders = chats[chat_id][ONETIME]
        if daily_reminders:
            reminders_list_msg += "This chat has the following daily reminder messages set:\n"
            dailies = []
            for re_key in daily_reminders: 
                dailies.append({"h": int(re_key.split("_")[1]), "m": int(re_key.split("_")[2])})
            for d in sorted(dailies, key=lambda t:t["h"]*60+t["m"]):
                reminders_list_msg += f"{d['h']:02d}:{d['m']:02d}\n"
        if onetime_reminders:
            if reminders_list_msg: reminders_list_msg += "\n"
            reminders_list_msg += "This chat has the following one-time reminders set:\n"
            for re_key in sorted(onetime_reminders, key=lambda r:dict_to_date(onetime_reminders[r]["when"])): 
                reminder = onetime_reminders[re_key]
                reminders_list_msg += format_onetime_reminder(reminder=reminder) + "\n"    
        if daily_reminders or onetime_reminders:
            await context.bot.send_message(chat_id=chat_id, text=reminders_list_msg)       
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])         

async def set_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
        return
    if context.args:
        matches = parse_time(time_string=' '.join(context.args))
        if matches:
            hours,minutes = (matches.hour, matches.minute)
            add_chat_if_not_exist(update.effective_chat)
            job_name = get_recurring_job_name(chat_id, hours, minutes)
            if not job_name in chats[chat_id][DAILY]:
                job = register_daily_reminder(context=context, chat_id=chat_id, hours=hours, minutes=minutes)
                if job: 
                    chats[chat_id][DAILY].append(job_name)
                    save_chats_to_file(chats)
                    await context.bot.send_message(chat_id=chat_id, text=msg["cmd_set_daily_succcess"])
                else:
                    await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_schedule_jobs"])
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_already_exists"])
            return  
    await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])

async def stop_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
        return
    if context.args:
        matches = parse_time(time_string=' '.join(context.args))
        if matches:
            hours,minutes = (matches.hour,matches.minute)
            job_name = get_recurring_job_name(chat_id, hours=hours, minutes=minutes)
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            if current_jobs:
                job = current_jobs[0]
                job.schedule_removal()
                logging.info(f"Removing job: {job_name}")
                await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_daily_success"])
                if job_name in chats[chat_id][DAILY]:
                    chats[chat_id][DAILY].remove(job_name)
                    save_chats_to_file(chats)
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 4:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])
        return
    reminder = {
        "from": update.effective_user.username,
        "target": context.args[0],
        "subject": "",
        "when": {}
    }
    indicies = {}
    now = datetime.now(tz=PACIFIC_TZ)
    when = now 
    keywords = {"at": 2,"in": 2,"on": 1,"tomorrow": 0}
    skip_next = False
    for index,word in enumerate([a.lower() for a in context.args]):
        #get ranges for each part of the sentence structure
        if skip_next:
            skip_next = False
            continue
        if word in keywords:
            cur_kw = word
            if not word in indicies:
                indicies[word] = {"index": index, "from": -1, "to": -1, "value": "", "finished": False}
        elif indicies and cur_kw in indicies:
            if indicies[cur_kw]["finished"]: continue

            if indicies[cur_kw]["from"] == -1: indicies[cur_kw]["from"] = index
            indicies[cur_kw]["to"] = index + 1
            words = context.args[indicies[cur_kw]["from"]:indicies[cur_kw]["to"]]
            value = " ".join(words)
            indicies[cur_kw]["value"] = value
            d,t = (parse_date(value), parse_time(value))
            greedy = False if index + 1 >= len(context.args) else parse_time(value + context.args[index+1])
            if cur_kw in["at","in"] and (t or greedy):
                indicies[cur_kw]["finished"] = True
                if greedy and cur_kw == "at": 
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
            elif cur_kw == "tomorrow":
                indicies[cur_kw]["finished"] = True
                when += timedelta(days=1)
            elif cur_kw == "in" and len(words) < 2:
                pass
            else: #couldn't parse kw, likely used in subject
                indicies.pop(cur_kw)

    logging.info(indicies)

    if not "at" in indicies and not "in" in indicies:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])
        return
    
    if reminder["target"].lower() == "me": reminder["target"] = reminder['from']
    else: reminder["target"] = reminder["target"].lstrip("@")

    subject_words = context.args.copy()
    for key in indicies:
        i = indicies[key]
        if i["from"] == -1: i["to"] = i["index"] + 1
        elif i["to"] == -1: i["to"] = i["from"] + 1
        for j in range(i["index"],i["to"]):
            subject_words[j] = ""
    reminder["subject"] = " ".join([w for w in subject_words[1:] if w != ""])
    reminder["when"] = date_to_dict(when)
    
    logging.info(reminder)

    if not reminder["subject"]:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_no_subject"])
        return
    elif when < now:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_in_past"])
        return
    elif when > now + timedelta(days=365):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_too_far_out"])
        return
    elif when - now < timedelta(minutes=1):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_too_close"])
        return

    add_chat_if_not_exist(update.effective_chat)
    job_name = get_onetime_job_name(chat_id=chat_id, reminder=reminder)
    if not job_name in chats[chat_id][ONETIME]:
        job = register_onetime_reminder(context=context, chat_id=chat_id, reminder=reminder)
        if job: 
            chats[chat_id][ONETIME][job_name] = reminder
            save_chats_to_file(chats)
            await context.bot.send_message(chat_id=chat_id, 
                text=f"I've set your reminder!\n{format_onetime_reminder(reminder)}\n{msg['cmd_reminder_list']}")
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_schedule_jobs"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_already_exists"])

async def remove_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username.lower()
    reminders = dict(chats[chat_id][ONETIME])
    delete_arg_index,delete_reminder_num = (-1,-1)
    if not reminders:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])
        return
    if not await is_user_chat_admin(update=update):
        for key in reminders.copy():
            if not username in (reminders[key]["from"].lower(), reminders[key]["target"].lower()):
                reminders.pop(key)
        if not reminders:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_remove_permissions"])
            return
    if context.args:
        for index,arg in enumerate(context.args):
            if arg.startswith("#"): delete_arg_index = index
        if delete_arg_index != -1:
            time_args = context.args[0:delete_arg_index]
            if len(context.args[delete_arg_index]) > 1:
                try: delete_reminder_num = int(context.args[delete_arg_index].lstrip("#"))
                except: pass
            elif delete_arg_index + 1 < len(context.args):
                try: delete_reminder_num = int(context.args[delete_arg_index + 1])
                except: pass
            if delete_reminder_num == -1:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_remove_reminder"])
                return
        else:
            time_args = context.args
        t = parse_time(" ".join(time_args))
        if t:
            for key in reminders.copy():
                if not (reminders[key]["when"]["hour"] == t.hour and reminders[key]["when"]["minute"] == t.minute):
                    reminders.pop(key)
        elif delete_arg_index == -1:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])
            return
    if reminders:
        reminders_msg = f"You have access to remove the following reminders{' that match your search' if context.args else ''}:\n"
        r_sorted = sorted(reminders, key = lambda r: dict_to_date(reminders[r]["when"]).time())
        args = ' '.join(context.args)
        for i,key in enumerate(r_sorted):
            n = i+1
            reminder_str = f"#{n}: " + format_onetime_reminder(reminders[key])
            delete_str   = f"``` /removereminder {(args + ' ') if args else ''}#{n}```" 
            reminders_msg += reminder_str + delete_str
            if delete_reminder_num != -1 and n == delete_reminder_num: 
                remove_scheduled_job(context=context, job_name=key)
                chats[chat_id][ONETIME].pop(key)
                save_chats_to_file(chats)
                await context.bot.send_message(chat_id=chat_id, text=f"Removing reminder {reminder_str}")
                return
        if delete_reminder_num == -1:
            await context.bot.send_message(chat_id=chat_id, text=reminders_msg, parse_mode="markdown")
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_remove_reminder"])    
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])

async def remind_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args.insert(0,"me")
    await remind_command(update=update, context=context)

async def remind_examples_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_remind_examples"], parse_mode="markdown")

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["err_admin_required"])
        return
    global data
    data = get_data_from_google()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_update"])

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_help"])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    add_chat_if_not_exist(update.effective_message.chat)
    await context.bot.send_message(chat_id=chat_id, text=msg["cmd_start"])

async def stop_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
        return
    if chat_id in chats: 
        set_stop_armed(chat_id=chat_id,armed=True)
        await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])

async def stop_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
        return
    if chat_id in chats: 
        if chats[chat_id]["stop_armed"] == 1:
            for job_name in chats[chat_id][DAILY]:
                remove_scheduled_job(context=context, job_name=job_name)
            for job_name in chats[chat_id][ONETIME]:
                remove_scheduled_job(context=context, job_name=job_name)
            chats.pop(chat_id)
            save_chats_to_file(chats)
            await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_confirm"])
        else: 
            await context.bot.send_message(chat_id=chat_id, text=msg["err_stop_not_armed"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_unknown"])

async def parse_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stop_armed(chat_id=update.effective_message.chat_id, armed=False)
    if update.effective_user.is_bot: return
    if update.message:
        message = update.message.text

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
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('getmessage', get_message_command))
    application.add_handler(CommandHandler(['list','listdaily','listreminders'], list_reminders_command))
    application.add_handler(CommandHandler(['set','setdaily', 'setdailyreminder'], set_daily_reminder_command))
    application.add_handler(CommandHandler(['stopdaily','stopdailyreminder'], stop_daily_reminder_command))
    application.add_handler(CommandHandler('remind', remind_command))
    application.add_handler(CommandHandler('remindme', remind_me_command))
    application.add_handler(CommandHandler(['remindexamples','reminderexamples'], remind_examples_command))
    application.add_handler(CommandHandler('removereminder', remove_reminder_command))
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('stopall', stop_all_command))
    application.add_handler(CommandHandler('stopconfirm', stop_confirm_command))
    application.add_handler(CommandHandler('update', update_command))
    application.add_handler(MessageHandler(filters.Regex(re.compile(AWOO_PATTERN, re.I)), awoo_reply))
    application.add_handler(MessageHandler(filters.Regex(re.compile(BOT_NAME, re.I)), awoo_reply))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), parse_all_messages))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()
