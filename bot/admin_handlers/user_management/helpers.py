# bot/admin_handlers/user_management/helpers.py

import asyncio
from telebot import types
from bot.bot_instance import bot

async def _delete_user_message(msg: types.Message):
    """حذف پیام کاربر جهت تمیز نگه داشتن چت"""
    try:
        if bot:
            await bot.delete_message(msg.chat.id, msg.message_id)
    except:
        pass

async def _auto_delete(msg, seconds):
    """پیام را بعد از چند ثانیه حذف می‌کند"""
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except:
        pass