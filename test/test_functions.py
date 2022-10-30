import os, sys
currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.append(parentdir)

from functions import parse_date, parse_time
from constants import *
from datetime import datetime, timedelta

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
        assert parse_time("in 24 hrs") == False

    
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
        assert parse_time("29:59") == False

    def test_invalid_minutes(self):
        assert parse_time("12:60") == False
    
    def test_invalid_pototo(self):
        assert parse_time("I'm a potatooooo!") == False

class TestParseDate:
    now = datetime.now(PACIFIC_TZ).replace(microsecond=0)

    def test_tomorrow(self):
        assert parse_date("tomorrow") == self.now + timedelta(days=1)
    
    def test_monday(self):
        days = 1 
        while (self.now + timedelta(days=days)).strftime("%A").lower() != "monday":
            days += 1
        assert parse_date("monday") == self.now + timedelta(days=days)

    #TODO:def test_intl_date_one
    #TODO:def test_us_date_one
    #TODO:def test_previous_date
