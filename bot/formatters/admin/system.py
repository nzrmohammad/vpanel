# bot/formatters/admin/system.py

class AdminSystemFormatter:
    
    @staticmethod
    def server_health(stats: dict) -> str:
        """نمایش وضعیت منابع سرور (RAM, CPU, Disk)"""
        return (
            f"🖥 <b>وضعیت سلامت سرور</b>\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"🧠 <b>رم (RAM):</b> {stats.get('ram_used', 0)} / {stats.get('ram_total', 0)} GB\n"
            f"⚙️ <b>پردازنده (CPU):</b> {stats.get('cpu_load', 0)}%\n"
            f"💾 <b>هارد (Disk):</b> {stats.get('disk_used', 0)}%\n"
            f"⏱ <b>آپتایم:</b> {stats.get('uptime', 'نامشخص')}\n"
            f"\n"
            f"🔄 <i>به‌روزرسانی خودکار: هر 5 دقیقه</i>"
        )