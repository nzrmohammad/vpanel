import asyncio
import httpx

# ================= تنظیمات (اینجا را پر کنید) =================
# آدرس پنل (مثال: https://panel.example.com)
PANEL_URL = "https://dashboard.cloudvibe.ir" 

# توکن ادمین (API Token)
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1dWlkIjoiYThlZTFhNjgtMjYxZC00M2Y5LThhNTYtZWQyNjliMjdhYzQ3IiwidXNlcm5hbWUiOm51bGwsInJvbGUiOiJBUEkiLCJpYXQiOjE3NjU3ODY1NzIsImV4cCI6MTA0MDU3MDAxNzJ9.67o3-zCQScxh7E-lxI9QRGnhBWIhiPdqB33J9A7MQSs"

# آن UUID که ربات می‌گوید پیدا نمی‌کند
TARGET_UUID = "2e1919a7-e929-4e11-99eb-d0e988d25aa7"
# ==============================================================

async def debug_panel():
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # اصلاح آدرس (حذف اسلش آخر)
    base_url = PANEL_URL.rstrip('/')
    
    print(f"🔍 Testing Connection to: {base_url} ...\n")

    async with httpx.AsyncClient(timeout=10) as client:
        # 1. تست دریافت کاربر خاص
        print(f"👉 1. Trying to fetch user: {TARGET_UUID}")
        try:
            resp = await client.get(f"{base_url}/api/users/{TARGET_UUID}", headers=headers)
            print(f"   Status Code: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}...") # نمایش 200 کاراکتر اول
            
            if resp.status_code == 200:
                print("   ✅ SUCCESS: User exists!")
            else:
                print("   ❌ FAIL: User not found or error.")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")

        print("-" * 30)

        # 2. دریافت لیست همه کاربران (برای مقایسه)
        print("👉 2. Fetching ALL users to compare UUIDs...")
        try:
            resp = await client.get(f"{base_url}/api/users", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # هندل کردن ساختارهای مختلف پاسخ
                users = []
                if isinstance(data, list): users = data
                elif "users" in data: users = data["users"]
                elif "response" in data and "users" in data["response"]: users = data["response"]["users"]
                
                print(f"   📊 Found {len(users)} users in panel.")
                
                found = False
                for u in users:
                    u_uuid = u.get("uuid") or u.get("id")
                    u_name = u.get("username")
                    print(f"   - User: {u_name} | UUID: {u_uuid}")
                    
                    if str(u_uuid) == TARGET_UUID:
                        found = True
                        print("   ✨ MATCH FOUND! The UUID is correct.")
                
                if not found:
                    print("\n   ⚠️ WARNING: Target UUID was NOT found in the list.")
                    print("   Please update the UUID in your bot database with one of the above.")
            else:
                print(f"   ❌ Failed to list users. Status: {resp.status_code}")
                print(f"   Response: {resp.text}")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(debug_panel())