import os
import sys

currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.append(parentdir)

from datetime import datetime, timedelta

import models as db
from constants import PACIFIC_TZ
from functions import parse_date, parse_reminder, parse_time


class TestParseTime:
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)
    noon = now.replace(hour=12, minute=0, second=0) + timedelta(days=0 if now.hour < 12 else 1)
    midnight = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)

    def test_midnight(self):
        assert parse_time("midnight") == self.midnight

    def test_noon(self):
        assert parse_time("noon") == self.noon

    def test_in_5minutes(self):
        assert parse_time("in 5 minutes") == self.now + timedelta(minutes=5)

    def test_in_2hours(self):
        assert parse_time("in 2 hours") == self.now + timedelta(hours=2)

    def test_in_4days(self):
        assert parse_time("in 4 days") == self.now + timedelta(days=4)

    def test_in_365days(self):
        assert parse_time("in 365 days") == self.now + timedelta(days=365)

    def test_in_3weeks(self):
        assert parse_time("in 3 weeks") == self.now + timedelta(days=21)

    def test_in_invalid(self):
        assert parse_time("in 24 hrs") is False

    def test_12h_midnight(self):
        assert parse_time("12a") == self.midnight

    def test_12h_midnight_two(self):
        assert parse_time("12:00 A.M.") == self.midnight

    def test_12h_noon(self):
        assert parse_time("12p") == self.noon

    def test_12h_noon_two(self):
        assert parse_time("12:00 P.M.") == self.noon

    def test_24h_midnight_one(self):
        assert parse_time("0000") == self.midnight

    def test_24h_midnight_two(self):
        assert parse_time("00:00") == self.midnight

    def test_24h_noon_one(self):
        assert parse_time("1200") == self.noon

    def test_24h_noon_two(self):
        assert parse_time("12:00") == self.noon

    def test_24h_before_now(self):
        previous_hour = self.now - timedelta(hours=1)
        assert parse_time(f"{previous_hour.hour}:59") == previous_hour.replace(minute=59, second=0) + timedelta(days=1)

    def test_invalid_hours(self):
        assert parse_time("29:59") is False

    def test_invalid_minutes(self):
        assert parse_time("12:60") is False

    def test_invalid_pototo(self):
        assert parse_time("I'm a potatooooo!") is False

    def test_invalid_extra(self):
        assert parse_time("4:20 on") is False


class TestParseDate:
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)

    def test_tomorrow(self):
        assert parse_date("tomorrow") == self.now + timedelta(days=1)

    def test_monday(self):
        days = 1
        while (self.now + timedelta(days=days)).strftime("%A").lower() != "monday":
            days += 1
        assert parse_date("monday") == self.now + timedelta(days=days)

    def test_intl_date(self):
        assert parse_date("2021-01-06") == self.now.replace(year=2021, month=1, day=6)

    def test_us_date_full(self):
        assert parse_date("12/31/1999") == self.now.replace(year=1999, month=12, day=31)

    def test_us_date_partial(self):
        assert parse_date("12/31") == self.now.replace(month=12, day=31)

    def test_date_next_year(self):
        when = self.now - timedelta(days=1)
        assert parse_date(when.strftime("%m/%d")) == when.replace(year=when.year + 1)


class TestParseReminder:
    chat_id = 1234
    from_user = "Test"

    def test_time_and_date(self):
        reminder_text = "@Everyone to freak out at 11:59 pm on 12/31/1999".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=datetime(year=1999, month=12, day=31, hour=23, minute=59, second=0, microsecond=0, tzinfo=PACIFIC_TZ),
            target_user="Everyone",
            subject="to freak out"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_at(self):
        reminder_text = "me to drink some water at 2pm".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_time("2pm"),
            target_user=self.from_user,
            subject="to drink some water"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_tomorrow(self):
        reminder_text = "me at 1900 tomorrow to nom nom nom".split(" ")
        tomorrow_1900 = datetime.now(tz=PACIFIC_TZ).replace(hour=19, minute=0, second=0, microsecond=0) + timedelta(days=1)
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=tomorrow_1900,
            target_user=self.from_user,
            subject="to nom nom nom"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_tomorrow_two(self):
        reminder_text = "me at 0001 tomorrow to nom nom nom".split(" ")
        tomorrow_0001 = datetime.now(tz=PACIFIC_TZ).replace(hour=0, minute=1, second=0, microsecond=0) + timedelta(days=1)
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=tomorrow_0001,
            target_user=self.from_user,
            subject="to nom nom nom"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_tomorrow_three(self):
        reminder_text = "me tomorrow at 2359 to nom nom nom".split(" ")
        tomorrow_2359 = datetime.now(tz=PACIFIC_TZ).replace(hour=23, minute=59, second=0, microsecond=0) + timedelta(days=1)
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=tomorrow_2359,
            target_user=self.from_user,
            subject="to nom nom nom"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_tomorrow_four(self):
        reminder_text = "me at 2359 tomorrow to nom nom nom".split(" ")
        tomorrow_2359 = datetime.now(tz=PACIFIC_TZ).replace(hour=23, minute=59, second=0, microsecond=0) + timedelta(days=1)
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=tomorrow_2359,
            target_user=self.from_user,
            subject="to nom nom nom"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_weekday_and_midnight(self):
        reminder_text = "@AwooPackBot on Thursday to howl at the moon at midnight".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_date("Thursday").replace(hour=0, minute=0, second=0, microsecond=0),
            target_user="AwooPackBot",
            subject="to howl at the moon"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_reminder_12h_snacks(self):
        reminder_text = "me that you should get some snacks at 3a".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_time("3a"),
            target_user=self.from_user,
            subject="that you should get some snacks"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_in_5_minutes(self):
        reminder_text = "me to do a little dance in 5 minutes".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_time("in 5 minutes"),
            target_user=self.from_user,
            subject="to do a little dance"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_yodel_at_turtles(self):
        reminder_text = "me to yodel at turtles in 1 week at 4:20 p.m.".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_time("in 1 week").replace(hour=16, minute=20, second=0),
            target_user=self.from_user,
            subject="to yodel at turtles"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_yodel_at_turtles_two(self):
        reminder_text = "me to yodel at turtles at 4:20 on 12/31".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_date("12/31").replace(hour=4, minute=20, second=0),
            target_user=self.from_user,
            subject="to yodel at turtles"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_yodel_at_turtles_loudly(self):
        reminder_text = "me to yodel at turtles at 4:20 loudly on 12/31".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_date("12/31").replace(hour=4, minute=20, second=0),
            target_user=self.from_user,
            subject="to yodel at turtles loudly"
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_no_subject(self):
        reminder_text = "me in 5 minutes".split(" ")
        reminder_object = db.Reminder(
            chat_id=self.chat_id,
            from_user=self.from_user,
            when=parse_time("in 5 minutes"),
            target_user=self.from_user,
            subject=""
        )
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) == reminder_object

    def test_invalid_seconds(self):
        reminder_text = "me that I just ran this command in 5 seconds".split(" ")
        assert parse_reminder(chat_id=self.chat_id, from_user=self.from_user, args=reminder_text) is False
