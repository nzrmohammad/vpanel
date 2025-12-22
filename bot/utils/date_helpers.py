# bot/utils/date_helpers.py
import pytz
import jdatetime
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

def to_shamsi(dt, include_time=False, month_only=False):
    if not dt: return "نامشخص"
    try:
        gregorian_dt = None
        if isinstance(dt, datetime): gregorian_dt = dt
        elif isinstance(dt, date): gregorian_dt = datetime(dt.year, dt.month, dt.day)
        elif isinstance(dt, str):
            try: gregorian_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except ValueError:
                if '.' in dt: dt = dt.split('.')[0]
                gregorian_dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        if not gregorian_dt: return "نامشخص"
        if gregorian_dt.tzinfo is None: gregorian_dt = pytz.utc.localize(gregorian_dt)
        tehran_tz = pytz.timezone("Asia/Tehran")
        local_dt = gregorian_dt.astimezone(tehran_tz)
        dt_shamsi = jdatetime.datetime.fromgregorian(datetime=local_dt)
        if month_only: return f"{jdatetime.date.j_months_fa[dt_shamsi.month - 1]} {dt_shamsi.year}"
        if include_time: return dt_shamsi.strftime("%Y/%m/%d %H:%M:%S")
        return dt_shamsi.strftime("%Y/%m/%d")
    except Exception as e:
        logger.error(f"Error in to_shamsi: {e}")
        return "خطا"

def format_relative_time(dt):
    if not dt or not isinstance(dt, datetime): return "هرگز"
    now = datetime.now(pytz.utc)
    dt_utc = dt if dt.tzinfo else pytz.utc.localize(dt)
    delta = now - dt_utc
    seconds = delta.total_seconds()
    if seconds < 60: return "همین الان"
    if seconds < 3600: return f"{int(seconds / 60)} دقیقه پیش"
    if seconds < 86400: return f"{int(seconds / 3600)} ساعت پیش"
    if seconds < 172800: return "دیروز"
    return f"{delta.days} روز پیش"

def days_until_next_birthday(birth_date):
    if not birth_date: return None
    try:
        today = datetime.now().date()
        if isinstance(birth_date, datetime): birth_date = birth_date.date()
        next_birthday = birth_date.replace(year=today.year)
        if next_birthday < today: next_birthday = next_birthday.replace(year=today.year + 1)
        return (next_birthday - today).days
    except (ValueError, TypeError): return None