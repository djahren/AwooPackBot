import logging
import re
from datetime import time, timedelta, datetime
from random import choice, randrange

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


def register_reminder(context: ContextTypes.DEFAULT_TYPE, reminder: db.Reminder):
    if reminder.is_daily:
        chat = get_chat_from_db(chat_id=reminder.chat_id)
        offset = reminder.when
        if chat:
            if chat.reminder_offset:
                offset -= timedelta(minutes=chat.reminder_offset)
        return context.job_queue.run_repeating(
            send_daily_reminder_job,
            interval=timedelta(days=1),
            first=time(hour=offset.hour, minute=offset.minute, tzinfo=PACIFIC_TZ),
            chat_id=reminder.chat_id,
            name=reminder.name,
            data=reminder
        )
    else:
        return context.job_queue.run_once(
            callback=send_onetime_reminder_job,
            when=reminder.when.astimezone(tz=PACIFIC_TZ),
            chat_id=reminder.chat_id,
            name=reminder.name,
            data=reminder
        )


def remove_scheduled_job(context: ContextTypes.DEFAULT_TYPE, job_name: str):
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        logging.info(f"Removing job: {job_name}")


def reregister_scheduled_daily_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    chat = get_chat_from_db(chat_id=chat_id)
    if chat:
        for reminder in chat.daily_reminders:
            remove_scheduled_job(context=context, job_name=reminder.name)
            register_reminder(context=context, reminder=reminder)


def get_chat_from_db(chat_id: int) -> db.Chat:
    return session.query(db.Chat).filter(db.Chat.id == chat_id).first()


def add_chat_if_not_exist(chat: Chat) -> db.Chat:
    the_chat = get_chat_from_db(chat_id=chat.id)
    if not the_chat:
        title = chat.title if chat.title else f"{chat.first_name} {chat.last_name}"
        the_chat = db.Chat(
            chat_id=chat.id,
            title=title,
            time_zone="America/Los_Angeles"
        )
        session.add(the_chat)
        session.commit()
    return the_chat


def set_stop_armed(chat_id, armed):
    chat = get_chat_from_db(chat_id=chat_id)
    if chat:
        chat.stop_armed = armed
        session.commit()
    return chat


def load_chats(application):
    chats: list[db.Chat] = session.query(db.Chat).all()
    for chat in chats:
        logging.info(repr(chat))
        set_stop_armed(chat_id=chat.id, armed=False)
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=chat.id)
        purge_past_reminders(chat.id)
        for reminder in chat.reminders:
            register_reminder(context=context, reminder=reminder)


def purge_past_reminders(chat_id: int):
    chat = get_chat_from_db(chat_id=chat_id)
    if chat:
        now = datetime.now(tz=PACIFIC_TZ)
        for reminder in chat.onetime_reminders:
            if reminder.when.astimezone(tz=PACIFIC_TZ) < now:
                session.delete(reminder)
        session.commit()


async def send_daily_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    logging.info(job.name)
    chat = get_chat_from_db(job.chat_id)
    if chat and not job.name.endswith("_delayed"):
        if chat.reminder_offset:
            offset = timedelta(
                minutes=randrange(0, chat.reminder_offset * 2),
                seconds=randrange(0, 60)
            )
            delayed = datetime.now(tz=PACIFIC_TZ) + offset
            logging.info(f"Delaying job until: {delayed}")
            return context.job_queue.run_once(
                callback=send_daily_reminder_job,
                when=delayed,
                chat_id=job.chat_id,
                name=job.name + "_delayed",
                data=job.data
            )
    message = generate_message(data)
    logging.info(f"Sending message via job: {message} at {get_current_time_string()}")
    return await context.bot.send_message(chat_id=job.chat_id, text=message)


async def send_onetime_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    try:
        reminder: db.Reminder = job.data
        from_user = reminder.from_user if reminder.from_user != reminder.target_user else "You"
        message = f"""{choice(data['words']['greeting']).replace('%tod%',get_time_of_day())}
 @{reminder.target_user}! {from_user} asked me to remind you {reminder.subject}."""
        return await context.bot.send_message(chat_id=job.chat_id, text=message)
    except Exception as e:
        logging.info(f"""Failed sending job: {job.name} at {get_current_time_string()} with the following error: {str(e)}""")
    finally:
        session.delete(reminder)
        session.commit()


async def awoo_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.is_bot:
        return
    return await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=choice(data["words"]["awoo"]),
        reply_to_message_id=update.message.id
    )


async def get_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = generate_message(data)
    logging.info(f"Sending message: {message} at {get_current_time_string()}")
    return await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    purge_past_reminders(chat_id)
    if chat:
        reminders_list_msg = ""
        if chat.daily_reminders:
            minutes_str = "minute" if chat.reminder_offset == 1 else "minutes"
            reminders_list_msg += "This chat has the following daily reminder messages set{}:\n".format(
                f" (with an offset of +/- {chat.reminder_offset} {minutes_str})" if chat.reminder_offset else ""
            )
            for reminder in sorted(chat.daily_reminders):
                reminders_list_msg += reminder.format_string() + "\n"
        if chat.onetime_reminders:
            if reminders_list_msg:
                reminders_list_msg += "\n"
            reminders_list_msg += "This chat has the following one-time reminders set:\n"
            for reminder in sorted(chat.onetime_reminders):
                reminders_list_msg += reminder.format_string() + "\n"
        if chat.reminders:
            return await context.bot.send_message(chat_id=chat_id, text=reminders_list_msg)
    return await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])


async def set_random_offset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_user_chat_admin(update=update):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
    if context.args:
        try:
            offset = int(context.args[0])
            if 0 <= offset <= 60:
                chat = add_chat_if_not_exist(update.effective_chat)
                if offset == chat.reminder_offset:
                    return await context.bot.send_message(chat_id=chat_id, text=msg["err_set_random_same"])
                chat.reminder_offset = offset
                session.commit()
                reregister_scheduled_daily_jobs(context=context, chat_id=chat_id)
                if offset > 0:
                    msg_text = str(msg["cmd_set_random_set"]).format(offset)
                else:
                    msg_text = msg["cmd_set_random_removed"]
                return await context.bot.send_message(chat_id=chat_id, text=msg_text)
        except Exception:
            pass
    return await context.bot.send_message(chat_id=chat_id, text=msg["err_set_random"])


async def set_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_user_chat_admin(update=update):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
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
                job = register_reminder(context=context, reminder=reminder)
                if job:
                    session.add(reminder)
                    session.commit()
                    return await context.bot.send_message(chat_id=chat_id, text=msg["cmd_set_daily_succcess"])
                else:
                    return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_schedule_jobs"])
            else:
                return await context.bot.send_message(chat_id=chat_id, text=msg["err_already_exists"])
    return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])


async def stop_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_user_chat_admin(update=update):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
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
                if job_exists_db:
                    session.delete(job_exists_db)
                    session.commit()
                return await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_daily_success"])
            else:
                return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])
    return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_parse_time"])


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 4:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])

    now = datetime.now(tz=PACIFIC_TZ).replace(microsecond=0)
    reminder = parse_reminder(
        chat_id=chat_id,
        from_user=update.effective_user.username,
        args=context.args
    )

    if not reminder:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_need_at"])
    if not reminder.subject:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_no_subject"])
    elif reminder.when < now:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_in_past"])
    elif reminder.when > now + timedelta(days=365):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_too_far_out"])
    elif reminder.when - now < timedelta(minutes=1):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_reminder_too_close"])

    add_chat_if_not_exist(update.effective_chat)
    job_exists = session.query(db.Reminder).filter(db.Reminder.name == reminder.name).first()
    if not job_exists:
        job = register_reminder(context=context, reminder=reminder)
        if job:
            session.add(reminder)
            session.commit()
            return await context.bot.send_message(
                chat_id=chat_id,
                text="I've set your reminder!\n{}\n{}".format(
                    reminder.format_string(),
                    msg['cmd_reminder_list']
                )
            )
        else:
            return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_schedule_jobs"])
    else:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_already_exists"])


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
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])
    if not chat.reminders:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_no_reminders"])
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
                return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_remove_reminder"])
        t = parse_time(" ".join(time_args))
        if not t and delete_arg_index == -1:
            return await context.bot.send_message(
                chat_id=chat_id,
                text=msg["err_cant_parse_time"]
            )

    for reminder in chat.onetime_reminders:
        time_match = False if 't' not in locals() else reminder.when.hour == t.hour and reminder.when.minute == t.minute
        delete_but_not_time_is_set = delete_arg_index != -1 and not t
        if not context.args or delete_but_not_time_is_set or time_match:
            num_possible_matched_reminders += 1
            if username == reminder.from_user.lower() or username == reminder.target_user.lower() or user_is_admin:
                reminders_to_show.append(reminder)

    if not reminders_to_show and num_possible_matched_reminders == 0 and not user_is_admin:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_remove_permissions"])

    if reminders_to_show or (user_is_admin and chat.daily_reminders):
        reminders_msg = "You have access to remove the following reminders{}:\n".format(
            ' that match your search' if context.args else ''
        )
        args = ' '.join(context.args)
        for i, reminder in enumerate(sorted(reminders_to_show)):
            n = i + 1
            reminder_str = f"#{n}: " + reminder.format_string()
            delete_str = f"``` /removereminder {(args + ' ') if args else ''}#{n}```"
            reminders_msg += reminder_str + delete_str
            if n == delete_reminder_num and delete_reminder_num != -1:
                remove_scheduled_job(context=context, job_name=reminder.name)
                session.delete(reminder)
                session.commit()
                return await context.bot.send_message(chat_id=chat_id, text=f"Removing reminder {reminder_str}")
        if delete_reminder_num == -1:
            return await context.bot.send_message(chat_id=chat_id, text=reminders_msg, parse_mode="markdown")
        else:
            return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_remove_reminder"])
    return await context.bot.send_message(chat_id=chat_id, text=msg["err_cant_find_reminder"])


async def remind_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args.insert(0, "me")
    await remind_command(update=update, context=context)


async def remind_examples_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg["cmd_remind_examples"],
        parse_mode="markdown"
    )


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_chat_admin(update=update):
        return await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["err_admin_required"])
    global data
    data = get_data_from_google()
    return await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_update"])


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_help"])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    add_chat_if_not_exist(update.effective_message.chat)
    return await context.bot.send_message(chat_id=chat_id, text=msg["cmd_start"])


async def stop_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not await is_user_chat_admin(update=update):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    if chat:
        set_stop_armed(chat_id=chat_id, armed=True)
        return await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop"])
    else:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])


async def stop_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if not await is_user_chat_admin(update=update):
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_admin_required"])
    chat: db.Chat = session.query(db.Chat).filter(db.Chat.id == chat_id).first()
    if chat:
        if chat.stop_armed:
            session.delete(chat)
            session.commit()
            return await context.bot.send_message(chat_id=chat_id, text=msg["cmd_stop_confirm"])
        else:
            return await context.bot.send_message(chat_id=chat_id, text=msg["err_stop_not_armed"])
    else:
        return await context.bot.send_message(chat_id=chat_id, text=msg["err_chat_not_in_db"])


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await context.bot.send_message(chat_id=update.effective_chat.id, text=msg["cmd_unknown"])


async def parse_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stop_armed(chat_id=update.effective_message.chat_id, armed=False)
    if update.effective_user.is_bot:
        return


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
    application.add_handler(CommandHandler(['setrandom', 'setoffset'], set_random_offset))
    application.add_handler(CommandHandler(['stopdaily', 'stopreminder', 'stopdailyreminder'], stop_daily_reminder_command))
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
