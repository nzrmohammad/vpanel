# bot/formatters/user/wallet.py
from bot.utils.date_helpers import to_shamsi
from bot.utils.formatters import escape_markdown, format_price

class WalletFormatter:

    @staticmethod
    def history_list(transactions: list) -> str:
        text = "📜 *تاریخچه تراکنش‌ها*\n"
        if not transactions:
            return text + "──────────────────\nتراکنشی یافت نشد"
            
        for t in transactions:
            amount = t.get('amount', 0)
            desc = t.get('description') or t.get('type', 'Unknown')
            date = to_shamsi(t.get('transaction_date'), include_time=True)
            
            icon = "➕" if amount > 0 else "➖"
            
            text += (
                "──────────────────\n"
                f"{icon} {escape_markdown(f'{int(abs(amount)):,}')} تومان \n"
                f" {escape_markdown(desc)} \n"
                f" {escape_markdown(date)}\n"
            )
        return text

    @staticmethod
    def purchase_receipt(plan_name, limit, days, service_name, server_name) -> str:
        return (
            f"✅ <b>خرید با موفقیت انجام شد!</b>\n"
            f"➖➖➖➖➖➖➖\n"
            f"📦 پلن: {plan_name}\n"
            f"💾 حجم: {limit} گیگ\n"
            f"⏳ مدت: {days} روز\n"
            f"👤 سرویس: <code>{service_name}</code>\n"
            f"🖥 سرور: {server_name}\n"
            f"➖➖➖➖➖➖➖\n"
            f"از خرید شما متشکریم 🌹"
        )
    
    @staticmethod
    def purchase_confirmation(plan_name, price, balance) -> str:
         return (
            f"🧾 <b>تایید نهایی خرید</b>\n\n"
            f"📦 سرویس: {plan_name}\n"
            f"💰 قیمت: {int(price):,} تومان\n"
            f"💳 موجودی شما: {int(balance):,} تومان\n\n"
            f"آیا از خرید اطمینان دارید؟"
        )

    @staticmethod
    def payment_details(method: dict) -> str:
        """نمایش اطلاعات کارت جهت واریز"""
        title = escape_markdown(method.get('title', ''))
        details = method.get('details', {})
        
        lines = []
        if isinstance(details, dict):
            labels = {'bank_name': '🏦 نام بانک', 'card_holder': '👤 صاحب حساب', 'card_number': '💳 شماره کارت'}
            for k, v in details.items():
                val = f"`{str(v).replace('-', '').replace(' ', '')}`" if k == 'card_number' else escape_markdown(str(v))
                lines.append(f"{labels.get(k, k)}: {val}")
        else:
            lines.append(escape_markdown(str(details)))

        return (
            f"📝 *اطلاعات پرداخت:*\n{title}\n"
            f"────────────────────\n"
            f"{chr(10).join(lines)}\n"
            f"────────────────────\n\n"
            f"📸 *لطفاً تصویر رسید را ارسال کنید\\.*"
        )