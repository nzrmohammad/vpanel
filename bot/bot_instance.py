# bot/bot_instance.py
import os
from telebot.async_telebot import AsyncTeleBot
from bot.config import BOT_TOKEN

if not BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN is not set in .env file!")

bot = AsyncTeleBot(BOT_TOKEN)