# bot/utils/__init__.py
from .date_helpers import to_shamsi, format_relative_time, days_until_next_birthday
from .formatters import format_usage, format_currency, escape_markdown, create_progress_bar, bytes_to_gb
from .parsers import parse_user_agent, extract_country_code_from_flag, parse_volume_string
from .network import _safe_edit
from .v2ray import generate_user_subscription_configs, create_info_config

# تابعی برای مقداردهی اولیه (اگر نیاز بود)
def initialize_utils(bot_instance):
    from . import network
    network.bot = bot_instance