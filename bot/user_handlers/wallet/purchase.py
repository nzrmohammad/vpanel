# bot/user_handlers/wallet/purchase.py

import logging
import uuid as uuid_lib
import time
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select

from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.formatters import user_formatter
from bot.database import db
from bot.db.base import UserUUID, Panel
from bot.language import get_string
from bot.services.panels import PanelFactory
from bot.formatters.admin import AdminFormatter
from bot.utils.formatters import escape_markdown
from bot import combined_handler

logger = logging.getLogger(__name__)

@bot.callback_query_handler(func=lambda call: call.data == "view_plans")
async def view_plans_categories(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    markup = await user_menu.plan_categories_menu(lang)
    await bot.edit_message_text(get_string('prompt_select_plan_category', lang), user_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("show_plans:"))
async def show_plans_list(call: types.CallbackQuery):
    category = call.data.split(":")[1]
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    categories = await db.get_server_categories()
    selected_cat = next((c for c in categories if c['code'] == category), None)
    
    cat_name = selected_cat['name'] if selected_cat else category
    cat_desc = selected_cat.get('description') if selected_cat else None
    
    if cat_desc:
        await bot.answer_callback_query(call.id, cat_desc, show_alert=True)
    
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0)
    all_plans = await db.get_all_plans(active_only=True)
    
    filtered_plans = []
    for plan in all_plans:
        cats = plan.get('allowed_categories') or []
        if category == 'combined':
            if len(cats) > 1 or not cats: filtered_plans.append(plan)
        else:
            if category in cats and len(cats) == 1: filtered_plans.append(plan)
    
    if not filtered_plans:
        try: await bot.answer_callback_query(call.id, "❌ پلنی یافت نشد", show_alert=True)
        except: pass
        return

    text = f"🚀 *پلن‌های فروش سرویس ({escape_markdown(cat_name)})*\n"
    if cat_desc:
        text += f"💡 {escape_markdown(cat_desc)}\n"
    text += "────────────────────\n"

    for plan in filtered_plans:
        price = f"{int(plan['price']):,}"
        text += f"{escape_markdown(plan['name'])}\nحجم: {plan['volume_gb']} GB\nزمان: {plan['days']} روز\nقیمت: {price} تومان\n────────────────────\n"

    markup = await user_menu.plan_category_menu(lang, balance, filtered_plans)
    try:
        await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='MarkdownV2')
    except:
        await bot.edit_message_text(text.replace('*',''), user_id, call.message.message_id, reply_markup=markup)


# --- مرحله ۱: انتخاب مقصد ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:buy_confirm:'))
async def select_service_destination(call: types.CallbackQuery):
    plan_id = int(call.data.split(':')[2])
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    await bot.edit_message_text("⏳ در حال دریافت لیست سرویس‌ها...", user_id, call.message.message_id)
    
    async with db.get_session() as session:
        stmt = select(UserUUID).where(UserUUID.user_id == user_id, UserUUID.is_active == True)
        result = await session.execute(stmt)
        user_services = result.scalars().all()

    if not user_services:
        await _show_new_service_preview(call, plan_id, user_id)
        return

    # --- شروع تغییرات (ریفکتور) ---
    
    # ۱. آماده‌سازی لیست داده‌ها برای ارسال به کیبورد
    services_data = []
    
    for srv in user_services:
        uuid_str = str(srv.uuid)
        srv_name = srv.name if srv.name else "Service"
        percent = 0
        days_str = "?"
        
        try:
            info = await combined_handler.get_combined_user_info(uuid_str)
            if info:
                percent = int(info.get('usage_percentage', 0))
                raw_expire = info.get('expire')
                if isinstance(raw_expire, (int, float)) and raw_expire > 100_000_000:
                    try:
                        expire_dt = datetime.fromtimestamp(raw_expire)
                        now = datetime.now()
                        rem_days = (expire_dt - now).days
                        days_str = str(max(0, rem_days))
                    except:
                        days_str = "?"
                elif isinstance(raw_expire, (int, float)):
                    days_str = str(int(raw_expire))
                else: days_str = "∞"
        except: pass
        
        # ساخت متن دکمه
        btn_text = f"📊 {srv_name} ({percent}% - {days_str} روز)"
        
        # اضافه کردن به لیست
        services_data.append({
            'id': srv.id,
            'text': btn_text
        })
    
    # ۲. فراخوانی کیبورد جدید
    markup = await user_menu.select_destination_menu(
        service_list=services_data,
        plan_id=plan_id,
        lang_code=lang
    )
    
    # --- پایان تغییرات ---
    
    await bot.edit_message_text(
        "🤔 شما سرویس‌های فعالی دارید.\nبرای این خرید، می‌خواهید سرویس جدید بسازید یا یکی از سرویس‌های موجود را تمدید کنید؟",
        user_id, call.message.message_id, reply_markup=markup
    )

# --- مرحله ۲: پیش‌نمایش خرید جدید ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:preview_new:'))
async def handler_preview_new(call: types.CallbackQuery):
    plan_id = int(call.data.split(':')[2])
    await _show_new_service_preview(call, plan_id, call.from_user.id)

async def _show_new_service_preview(call, plan_id, user_id):
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return

    lang = await db.get_user_language(user_id)
    categories = await db.get_server_categories()
    plan_cat_code = plan['allowed_categories'][0] if plan['allowed_categories'] else None
    plan_cat_info = next((c for c in categories if c['code'] == plan_cat_code), None)
    
    text = user_formatter.generate_new_preview_text(plan, plan_cat_info)
    
    markup = await user_menu.confirm_payment_menu(confirm_callback=f"wallet:do_buy_new:{plan_id}",lang_code=lang)
    
    try:
        await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='MarkdownV2')
    except:
        await bot.edit_message_text(text.replace('*',''), user_id, call.message.message_id, reply_markup=markup)

# --- مرحله ۳: پیش‌نمایش تمدید ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:preview_renew:'))
async def handler_preview_renew(call: types.CallbackQuery):
    parts = call.data.split(':')
    uuid_id = int(parts[2])
    plan_id = int(parts[3])
    user_id = call.from_user.id
    
    plan = await db.get_plan_by_id(plan_id)
    
    async with db.get_session() as session:
        uuid_obj = await session.get(UserUUID, uuid_id)
        if not uuid_obj: return
        
        # --- اصلاح: دریافت اطلاعات زنده (اول پنل، بعد دیتابیس) ---
        lang = await db.get_user_language(user_id)
        current_stats = {}
        fetched_from_panel = False
        
        # 1. تلاش اول: اتصال مستقیم به پنل (برای دقت ۱۰۰٪)
        try:
            if uuid_obj.allowed_panels:
                # گرفتن پنل کاربر
                target_panel = uuid_obj.allowed_panels[0]
                panel_api = await PanelFactory.get_panel(target_panel.name)
                
                if panel_api:
                    # درخواست مستقیم به API پنل
                    raw_user = await panel_api.get_user(str(uuid_obj.uuid))
                    if raw_user:
                        # تبدیل بایت به گیگابایت (چون اکثر پنل‌ها بایت برمی‌گردانند)
                        limit_bytes = 0
                        if 'data_limit' in raw_user and raw_user['data_limit']: 
                            limit_bytes = float(raw_user['data_limit'])
                        elif 'usage_limit_GB' in raw_user: 
                            limit_bytes = float(raw_user['usage_limit_GB']) * (1024**3)
                        
                        used_bytes = 0
                        if 'used_traffic' in raw_user and raw_user['used_traffic']: 
                            used_bytes = float(raw_user['used_traffic'])
                        
                        expire_ts = 0
                        if 'expire_date' in raw_user: expire_ts = raw_user['expire_date']
                        elif 'expire' in raw_user: expire_ts = raw_user['expire']
                        
                        current_stats = {
                            'traffic_limit': limit_bytes / (1024**3),
                            'traffic_used': used_bytes / (1024**3),
                            'expire_date': expire_ts
                        }
                        fetched_from_panel = True
        except Exception as e:
            logger.error(f"Live panel fetch failed (Fallback to cache): {e}")

        # 2. تلاش دوم: اگر پنل جواب نداد، دریافت از کش (Combined Handler)
        if not fetched_from_panel:
            try:
                info = await combined_handler.get_combined_user_info(str(uuid_obj.uuid))
                if info:
                    # پشتیبانی از ساختارهای مختلف کش
                    limit = info.get('usage_limit_GB', 0)
                    used = info.get('current_usage_GB', 0)
                    
                    # اگر ساختار قدیمی بود
                    if limit == 0 and 'usage' in info and isinstance(info['usage'], dict):
                        limit = info['usage'].get('data_limit_GB', 0)
                        used = info['usage'].get('total_usage_GB', 0)
                        
                    current_stats = {
                        'traffic_limit': limit, 
                        'traffic_used': used, 
                        'expire_date': info.get('expire')
                    }
            except Exception as e:
                logger.error(f"Cache fetch failed: {e}")

        # دریافت اطلاعات کتگوری و پلن
        categories = await db.get_server_categories()
        plan_cat_code = plan['allowed_categories'][0] if plan['allowed_categories'] else None
        plan_cat_info = next((c for c in categories if c['code'] == plan_cat_code), None)
        
        # تولید متن پیش‌نمایش
        text = await user_formatter.generate_renewal_preview_text(uuid_obj, plan, plan_cat_info, categories, current_stats)
        
        markup = await user_menu.confirm_payment_menu(confirm_callback=f"wallet:do_renew:{uuid_id}:{plan_id}",cancel_callback="view_plans",lang_code=lang)
        
        try:
            await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='MarkdownV2')
        except:
             await bot.edit_message_text(text.replace('*',''), user_id, call.message.message_id, reply_markup=markup)


# ---------------------------------------------------------
# 3. اجرای عملیات (خرید جدید یا تمدید)
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:do_buy_new:'))
async def execute_purchase_new(call: types.CallbackQuery):
    user_id = call.from_user.id
    msg_id = call.message.message_id
    plan_id = int(call.data.split(':')[2])
    
    await bot.edit_message_text("⏳ در حال انتخاب سرور و ایجاد اکانت...", user_id, msg_id)
    
    try:
        plan = await db.get_plan_by_id(plan_id)
        user_data = await db.user(user_id)
        if user_data.get('wallet_balance', 0) < plan['price']:
            await bot.edit_message_text("❌ موجودی کافی نیست.", user_id, msg_id)
            return

        target_panel_name = None
        async with db.get_session() as session:
            # انتخاب هوشمند پنل
            if plan.get('allowed_categories'):
                target_cat = plan['allowed_categories'][0]
                stmt = select(Panel).where(Panel.category == target_cat, Panel.is_active == True)
            else:
                stmt = select(Panel).where(Panel.is_active == True)
            res = await session.execute(stmt)
            panel_obj = res.scalars().first()
            if panel_obj: target_panel_name = panel_obj.name

        if not target_panel_name:
            await bot.edit_message_text("❌ سرور فعالی یافت نشد.", user_id, msg_id)
            return

        panel_api = await PanelFactory.get_panel(target_panel_name)
        if not panel_api:
            await bot.edit_message_text("❌ خطا در درایور پنل.", user_id, msg_id)
            return
            
        username = f"u{user_id}_{str(uuid_lib.uuid4())[:8]}"
        new_service = await panel_api.add_user(username, plan['volume_gb'], plan['days'])
        
        if new_service:
            await _finalize_transaction(user_id, plan, username, new_service, target_panel_name, is_renewal=False, msg_id=msg_id)
        else:
            await bot.edit_message_text("❌ خطا در ساخت سرویس.", user_id, msg_id)

    except Exception as e:
        logger.error(f"New Purchase Error: {e}")
        await bot.edit_message_text("❌ خطای غیرمنتظره.", user_id, msg_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:do_renew:'))
async def execute_purchase_renew(call: types.CallbackQuery):
    parts = call.data.split(':')
    uuid_id = int(parts[2])
    plan_id = int(parts[3])
    user_id = call.from_user.id
    msg_id = call.message.message_id
    
    await bot.edit_message_text("⏳ در حال اعمال تمدید روی سرور...", user_id, msg_id)

    try:
        plan = await db.get_plan_by_id(plan_id)
        user_data = await db.user(user_id)
        if user_data.get('wallet_balance', 0) < plan['price']:
            await bot.edit_message_text("❌ موجودی کافی نیست.", user_id, msg_id)
            return

        async with db.get_session() as session:
            uuid_obj = await session.get(UserUUID, uuid_id)
            if not uuid_obj or not uuid_obj.allowed_panels:
                await bot.edit_message_text("❌ سرویس یا پنل مربوطه یافت نشد.", user_id, msg_id)
                return
            
            target_panel = uuid_obj.allowed_panels[0]
            panel_name = target_panel.name
            panel_api = await PanelFactory.get_panel(panel_name)
            if not panel_api:
                await bot.edit_message_text("❌ خطا در اتصال به پنل.", user_id, msg_id)
                return
            
            # --- دریافت وضعیت فعلی ---
            user_in_panel = await panel_api.get_user(str(uuid_obj.uuid))
            
            current_limit_gb = 0
            current_expire_ts = 0
            current_usage = 0
            
            if user_in_panel:
                if 'data_limit' in user_in_panel: current_limit_gb = float(user_in_panel['data_limit']) / (1024**3)
                elif 'usage_limit_GB' in user_in_panel: current_limit_gb = float(user_in_panel['usage_limit_GB'])
                
                if 'used_traffic' in user_in_panel: current_usage = float(user_in_panel['used_traffic'])
                
                if 'expire_date' in user_in_panel: current_expire_ts = user_in_panel['expire_date']
                elif 'expire' in user_in_panel: current_expire_ts = user_in_panel['expire']
            
            # --- منطق هوشمند ۳ روز ---
            reset_mode = False
            now_ts = time.time()
            cutoff_ts = now_ts - (3 * 86400) # 3 روز پیش
            
            # اگر تاریخ انقضا وجود دارد و قدیمی‌تر از ۳ روز پیش است (یعنی ۳ روزه که منقضی شده)
            if current_expire_ts and current_expire_ts < cutoff_ts:
                reset_mode = True

            if reset_mode:
                # حالت ریست: حجم قبلی می‌سوزد، فقط حجم پلن جدید اعمال می‌شود
                new_limit_gb = plan['volume_gb']
                new_usage_to_set = 0 # ریست کردن مصرف (بسته به قابلیت پنل)
                new_expire_date = datetime.now() + timedelta(days=plan['days'])
                
                # نکته: برخی پنل‌ها api برای ریست مصرف ندارند، در این صورت مجبوریم لیمیت را با مصرف فعلی جمع بزنیم
                # اما اگر پنل reset_usage دارد باید اینجا صدا زده شود.
                # ما فرض می‌کنیم با ست کردن لیمیت جدید و انقضا کار راه می‌افتد یا پنل هوشمند است.
                # برای اطمینان، اگر پنل Marzban/Hiddify است معمولا متد reset_user_traffic دارد.
                try:
                    if hasattr(panel_api, 'reset_user_traffic'):
                        await panel_api.reset_user_traffic(str(uuid_obj.uuid))
                except: pass

            else:
                # حالت عادی: جمع کردن
                new_limit_gb = current_limit_gb + plan['volume_gb']
                if not current_expire_ts or current_expire_ts < now_ts:
                    new_expire_date = datetime.now() + timedelta(days=plan['days'])
                else:
                    new_expire_date = datetime.fromtimestamp(current_expire_ts) + timedelta(days=plan['days'])
            
            new_expire_ts_final = int(new_expire_date.timestamp())

            # اعمال تغییرات
            result = await panel_api.edit_user(
                str(uuid_obj.uuid),
                usage_limit_GB=new_limit_gb,
                expire_date=new_expire_ts_final
            )
            
            if result:
                await _finalize_transaction(user_id, plan, uuid_obj.name, {'uuid': str(uuid_obj.uuid)}, panel_name, is_renewal=True, msg_id=msg_id)
                
                uuid_obj.traffic_limit = new_limit_gb
                uuid_obj.expire_date = new_expire_date
                await session.commit()
            else:
                await bot.edit_message_text("❌ خطا در ویرایش کاربر در پنل.", user_id, msg_id)

    except Exception as e:
        logger.error(f"Renew Error: {e}")
        await bot.edit_message_text("❌ خطای غیرمنتظره در تمدید.", user_id, msg_id)

async def _finalize_transaction(user_id, plan, username, service_data, panel_name, is_renewal=False, msg_id=None):
    # 1. کسر موجودی و ثبت تراکنش
    desc_prefix = "تمدید سرویس" if is_renewal else "خرید پلن"
    full_desc = f"{desc_prefix} {plan['name']}"
    await db.update_wallet_balance(user_id, -plan['price'], 'purchase', full_desc)
    
    # دریافت موجودی جدید برای گزارش
    user_data = await db.user(user_id)
    current_balance = user_data.get('wallet_balance', 0)

    # 2. ثبت سرویس در دیتابیس (بدون تغییر)
    if not is_renewal:
        service_uuid = service_data.get('uuid') or username
        await db.add_uuid(user_id=user_id, uuid_str=service_uuid, name=username)
        
        uuid_id = await db.get_uuid_id_by_uuid(service_uuid)
        if uuid_id:
            if plan.get('allowed_categories'):
                await db.grant_access_by_category(uuid_id, plan['allowed_categories'])
            
            async with db.get_session() as session:
                stmt = select(Panel).where(Panel.name == panel_name)
                res = await session.execute(stmt)
                db_panel = res.scalar_one_or_none()
                if db_panel:
                    await db.update_user_panel_access_by_id(uuid_id, db_panel.id, allow=True)
                    stmt_u = select(UserUUID).where(UserUUID.id == uuid_id)
                    u = (await session.execute(stmt_u)).scalar_one_or_none()
                    if u:
                        u.traffic_limit = plan['volume_gb']
                        u.traffic_used = 0
                        u.expire_date = datetime.now() + timedelta(days=plan['days'])
                        await session.commit()

    # 3. ارسال پیام موفقیت به کاربر (با استفاده از متد جدید در UserFormatter)
    lang = await db.get_user_language(user_id)
    markup = await user_menu.post_charge_menu(lang)
    
    # ✅ استفاده از متد جدید purchase_receipt
    success_text = user_formatter.purchase_receipt(
        plan_name=plan['name'],
        limit_gb=int(plan['volume_gb']),
        days=plan['days'],
        service_name=username,
        server_name=panel_name
    )
    
    if msg_id:
        await bot.edit_message_text(success_text, user_id, msg_id, reply_markup=markup, parse_mode='HTML')
    else:
        await bot.send_message(user_id, success_text, reply_markup=markup, parse_mode='HTML')

    try:
        main_group_id = await db.get_config('main_group_id')
        shop_topic_id = await db.get_config('topic_id_shop')
        
        if main_group_id and int(main_group_id) != 0:
            user_info = await bot.get_chat(user_id)
            
            # ✅ استفاده از متد جدید purchase_report
            log_text = AdminFormatter.purchase_report(
                user_name=user_info.first_name,
                user_id=user_id,
                service_name=username,
                type_text="#تمدید" if is_renewal else "#خرید_جدید",
                plan_name=plan['name'],
                limit_gb=int(plan['volume_gb']),
                days=plan['days'],
                price=int(plan['price']),
                uuid_str=service_data.get('uuid', username),
                date_str=datetime.now().strftime('%Y-%m-%d %H:%M'),
                wallet_balance=current_balance,  # مقدار جدید
                server_name=panel_name           # مقدار جدید
            )
            
            target_thread = int(shop_topic_id) if shop_topic_id and int(shop_topic_id) != 0 else None
            
            await bot.send_message(
                chat_id=int(main_group_id),
                text=log_text,
                message_thread_id=target_thread,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Failed to send log to supergroup: {e}")