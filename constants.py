from zoneinfo import ZoneInfo
GOOGLE_SHEET_ID = "1IfGrcY4ntE70fycFRAEtjAvb20ukVf9wTkPzdvtLLKg"
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
CHATS_FILE_PATH = "data/chats.json"
MESSAGES_FILE_PATH = "messages.json"
BOT_NAME = "AwooPackBot"
ONETIME = "onetime_reminders"
DAILY = "daily_reminders"
AWOO_PATTERN = r"\b[auo0]+w[u0o]+\b"
TIME_PATTERN_12H = r"([0-1]?\d):*([0-5]\d)*\s?([ap]\.?m?\.?)$"
TIME_PATTERN_24H = r"([0-2]?\d):??([0-5]\d)$"
TIME_PATTERN_IN = r"(\d+) (minute|hour|day|week)"
DATE_PATTERN_INTL = r"([12]\d{3})-([01]?\d)-([0-3]?\d)"
DATE_PATTERN_US = r"([01]?\d)\/([0-3]?\d)\/?([12]?\d?\d{2})?"