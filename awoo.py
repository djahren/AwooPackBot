import logging
import re
from datetime import time, timedelta, datetime
from random import choice

from telegram import Chat, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

import models as db
from constants import PACIFIC_TZ, AWOO_PATTERN, BOT_NAME
from functions import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

data = {}
chats = {}
msg = get_system_messages()
session = db.Session()


def register_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int, reminder: db.Reminder):
    if reminder.is_daily:
        return context.job_queue.run_repeating(
            send_daily_reminder_job,
            interval=timedelta(days=1),
            first=time(hour=reminder.when.hour, minute=reminder.when.minute, tzinfo=PACIFIC_TZ),
            chat_id=chat_id,
            name=reminder.name,
            data=reminder
        )
    else:
        return context.job_queue.run_once(
            callback=send_onetime_reminder_job,
            when=reminder.when.astimezone(tz=PACIFIC_TZ),
            chat_id=chat_id,
            name=reminder.name,
            data=reminder
        )


def remove_scheduled_job(context: ContextTypes.DEFAULT_TYPE, job_name: str):
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        logging.info(f"Removing job: {job_name}")


def add_chat_if_not_exist(chat: Chat):
    the_chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat.id).first()
    if not the_chat:
        title = chat.title if chat.title else f"{chat.first_name} {chat.last_name}"
        the_chat = db.Chat(
            chat_id=chat.id,
            title=title,
            time_zone="America/Los_Angeles"
        )
        session.add(the_chat)
        session.commit()


def set_stop_armed(chat_id, armed):
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    if chat:
        chat.stop_armed = armed
        session.commit()
        return True
    else: return False


def load_chats(application):
    chats: list[db.Chat] = session.query(db.Chat).all()
    for chat in chats:
        logging.info(repr(chat))
        set_stop_armed(chat_id=chat.id, armed=False)
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=chat.id)
        purge_past_reminders(chat.id)
        for reminder in chat.reminders:
            register_reminder(context=context, chat_id=chat.id, reminder=reminder)


def purge_past_reminders(chat_id: int):
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    if not chat: return
    now = datetime.now(tz=PACIFIC_TZ)
    for reminder in chat.onetime_reminders:
        if reminder.when.astimezone(tz=PACIFIC_TZ) < now:
            session.delete(reminder)
    session.commit()


async def send_daily_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    # called by scheduled job
    job = context.job
    message = generate_message(data)
    logging.info(f"Sending message via job: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=job.chat_id, text=message)


async def send_onetime_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    # called by scheduled job
    job = context.job
    try:
        reminder: db.Reminder = job.data
        from_user = reminder.from_user if reminder.from_user != reminder.target_user else "You"
        message = f"""{choice(data['words']['greeting']).replace('%tod%',get_time_of_day())}
 @{reminder.target_user}! {from_user} asked me to remind you {reminder.subject}."""
        await context.bot.send_message(chat_id=job.chat_id, text=message)
    except Exception as e:
        logging.info(f"""Failed sending job: {job.name} at {get_current_time_string()} with the following error: {str(e)}""")
    finally:
        session.delete(reminder)
        session.commit()


async def awoo_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.is_bot:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=choice(data["words"]["awoo"]),
        reply_to_message_id=update.message.id
    )


async def get_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = generate_message(data)
    logging.info(f"Sending message: {message} at {get_current_time_string()}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    purge_past_reminders(chat_id)
    if chat:
        reminders_list_msg = ""
        if chat.daily_reminders:
            reminders_list_msg += "This chat has the following daily reminder messages set:\n"
            for reminder in sorted(chat.daily_reminders):
                reminders_list_msg += reminder.format_string() + "\n"
        if chat.onetime_reminders:
            if reminders_list_msg:
                reminders_list_msg += "\n"
            reminders_list_msg += "This chat has the following one-time reminders set:\n"
            for reminder in sorted(chat.onetime_reminders):
                reminders_list_msg += reminder.format_string() + "\n"
        if chat.reminders:
            await context.bot.send_message(chat_id=chat_id, text=reminders_list_msg)
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])


async def set_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
        return
    if context.args:
        parsed_time = parse_time(time_string=' '.join(context.args))
        if parsed_time:
            add_chat_if_not_exist(update.effective_chat)
            reminder = db.Reminder(
                chat_id=chat_id,
                when=parsed_time,
                from_user=update.effective_user.username
            )
            job_exists_db = session.query(db.Reminder).filter(db.Reminder.name == reminder.name).first()
            job_exists_queue = context.job_queue.get_jobs_by_name(reminder.name)
            if not job_exists_db and not job_exists_queue:
                job = register_reminder(context=context, chat_id=chat_id, reminder=reminder)
                if job:
                    session.add(reminder)
                    session.commit()
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
        parsed_time = parse_time(time_string=' '.join(context.args))
        if parsed_time:
            reminder = db.Reminder(
                chat_id=chat_id,
                when=parsed_time,
                from_user=update.effective_user.username
            )
            job_exists_queue = context.job_queue.get_jobs_by_name(reminder.name)
            job_exists_db = session.query(db.Reminder).filter(db.Reminder.name == reminder.name).first()
            if job_exists_queue:
                job = job_exists_queue[0]
                job.schedule_removal()
                logging.info(f"Removing job: {reminder.name}")
                await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_daily_success"])
                if job_exists_db:
                    session.delete(job_exists_db)
                    session.commit()
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 4:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])
        return

    now = datetime.now(tz=PACIFIC_TZ).replace(microsecond=0)
    reminder = parse_reminder(
        chat_id=chat_id,
        from_user=update.effective_user.username,
        args=context.args
    )

    if not reminder:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])
        return
    if not reminder.subject:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_no_subject"])
        return
    elif reminder.when < now:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_in_past"])
        return
    elif reminder.when > now + timedelta(days=365):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_too_far_out"])
        return
    elif reminder.when - now < timedelta(minutes=1):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_too_close"])
        return

    add_chat_if_not_exist(update.effective_chat)
    job_exists = session.query(db.Reminder).filter(db.Reminder.name == reminder.name).first()
    if not job_exists:
        job = register_reminder(context=context, chat_id=chat_id, reminder=reminder)
        if job:
            session.add(reminder)
            session.commit()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"I've set your reminder!\n{reminder.format_string()}\n{msg['cmd_reminder_list']}"
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_schedule_jobs"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_already_exists"])


# [ ] remove_reminder_command
async def remove_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    username = update.effective_user.username.lower()
    delete_arg_index, delete_reminder_num = (-1, -1)
    reminders_to_show: list[db.Reminder] = []
    user_is_admin = await is_user_chat_admin(update=update)
    num_possible_matched_reminders = 0
    if not chat:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])
        return
    if not chat.reminders:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])
        return
    if context.args:
        for index, arg in enumerate(context.args):
            if arg.startswith("#"):
                delete_arg_index = index
        if delete_arg_index == -1:
            time_args = context.args
        else:
            time_args = context.args[0:delete_arg_index]
            if len(context.args[delete_arg_index]) > 1:
                try:
                    delete_reminder_num = int(context.args[delete_arg_index].lstrip("#"))
                except Exception:
                    pass
            elif delete_arg_index + 1 < len(context.args):
                try:
                    delete_reminder_num = int(context.args[delete_arg_index + 1])
                except Exception:
                    pass
            if delete_reminder_num == -1:
                await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_remove_reminder"])
                return
        t = parse_time(" ".join(time_args))
        if not t and delete_arg_index == -1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg["err_cant_parse_time"])
            return

    for reminder in chat.onetime_reminders:
        if not context.args or (delete_arg_index != -1 and not t) or (t and reminder.when.hour == t.hour and reminder.when.minute == t.minute):
            num_possible_matched_reminders += 1
            if username == reminder.from_user.lower() or username == reminder.target_user.lower() or user_is_admin:
                reminders_to_show.append(reminder)

    if not reminders_to_show and num_possible_matched_reminders == 0 and not user_is_admin:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_remove_permissions"])
        return

    if reminders_to_show or (user_is_admin and chat.daily_reminders):
        reminders_msg = f"""You have access to remove the following
reminders{' that match your search' if context.args else ''}:\n"""
        args = ' '.join(context.args)
        for i, reminder in enumerate(sorted(reminders_to_show)):
            n = i+1
            reminder_str = f"#{n}: " + reminder.format_string()
            delete_str = f"``` /removereminder {(args + ' ') if args else ''}#{n}```"
            reminders_msg += reminder_str + delete_str
            if n == delete_reminder_num and delete_reminder_num != -1:
                remove_scheduled_job(context=context, job_name=reminder.name)
                session.delete(reminder)
                session.commit()
                await context.bot.send_message(chat_id=chat_id, text=f"Removing reminder {reminder_str}")
                return
        if delete_reminder_num == -1:
            await context.bot.send_message(chat_id=chat_id, text=reminders_msg, parse_mode="markdown")
            return
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_remove_reminder"])
            return
    await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])


async def remind_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args.insert(0, "me")
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
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    if chat:
        set_stop_armed(chat_id=chat_id, armed=True)
        await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])


async def stop_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not await is_user_chat_admin(update=update):
        await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
        return
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    if chat:
        if chat.stop_armed:
            session.delete(chat)
            session.commit()
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


if __name__ == '__main__':
    data = get_data_from_google()
    db.init_db()
    token = get_token()
    application = ApplicationBuilder().token(token).build()
    load_chats(application)

    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('getmessage', get_message_command))
    application.add_handler(CommandHandler(['list', 'listdaily', 'listreminders'], list_reminders_command))
    application.add_handler(CommandHandler(['set', 'setdaily', 'setdailyreminder'], set_daily_reminder_command))
    application.add_handler(CommandHandler(['stopdaily', 'stopdailyreminder'], stop_daily_reminder_command))
    application.add_handler(CommandHandler('remind', remind_command))
    application.add_handler(CommandHandler('remindme', remind_me_command))
    application.add_handler(CommandHandler(['remindexamples', 'reminderexamples'], remind_examples_command))
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
