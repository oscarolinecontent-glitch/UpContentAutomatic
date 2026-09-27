"""
SETUP FB SESSION v3 - Tự động phát hiện đăng nhập Facebook thành công
Mở Chrome thật, chờ bạn đăng nhập & hoàn tất 2FA, tự động lưu cookies đầy đủ.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_PATH = Path("./data/fb_cookies.json")
PROFILE_PATH = Path("./data/fb_profile")


async def export_cookies():
    print("=" * 60)
    print("🔑 SETUP FACEBOOK SESSION (TỰ ĐỘNG PHÁT HIỆN ĐĂNG NHẬP)")
    print("=" * 60)
    print()

    PROFILE_PATH.mkdir(parents=True, exist_ok=True)
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        # Ưu tiên dùng Chrome thật đã cài trên máy
        browser = None
        context = None
        channel_name = None

        for ch in ["chrome", "msedge", None]:
            try:
                print(f"🔄 Đang khởi tạo trình duyệt ({ch or 'Playwright Chromium'})...")
                # Dùng persistent_context để lưu lại toàn bộ cache/local storage
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_PATH.resolve()),
                    headless=False,
                    channel=ch,
                    viewport={"width": 1280, "height": 850},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="vi-VN",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                    ],
                )
                channel_name = ch or "Chromium"
                print(f"✅ Đang dùng: {channel_name}")
                break
            except Exception as e:
                print(f"⚠️  Không mở được {ch}: {e}")
                continue

        if not context:
            print("❌ Không thể mở trình duyệt!")
            return False

        page = context.pages[0] if context.pages else await context.new_page()

        print("\n🌐 Đang mở Facebook...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        await page.bring_to_front()

        print()
        print("┌────────────────────────────────────────────────────────┐")
        print("│ 👆 HƯỚNG DẪN ĐĂNG NHẬP:                                │")
        print("│ 1. Mở cửa sổ trình duyệt vừa hiện lên                  │")
        print("│ 2. Đăng nhập Email / SĐT và Mật khẩu                   │")
        print("│ 3. Nếu có 2FA: Nhập mã OTP hoặc xác nhận trên điện thoại│")
        print("│                                                        │")
        print("│ ⏳ Script sẽ TỰ ĐỘNG PHÁT HIỆN khi đăng nhập xong!     │")
        print("│    (Không cần bấm gì nếu chưa thấy báo thành công)     │")
        print("└────────────────────────────────────────────────────────┘")
        print()

        # Polling kiểm tra đăng nhập thành công qua cookie c_user
        print("⏳ Đang theo dõi trạng thái đăng nhập...")
        logged_in = False
        user_id = None

        for attempt in range(150):  # Chờ tối đa 5 phút (150 * 2s)
            cookies = await context.cookies()
            c_user_cookie = next((c for c in cookies if c.get("name") == "c_user"), None)
            
            if c_user_cookie and c_user_cookie.get("value"):
                user_id = c_user_cookie["value"]
                logged_in = True
                break

            # Kiểm tra xem có đang ở trang 2FA không
            current_url = page.url
            if "two_step_verification" in current_url or "checkpoint" in current_url:
                if attempt % 5 == 0:
                    print(f"   [Bước 2FA] Đang đợi bạn xác nhận mã trên Facebook... ({attempt*2}s)")
            elif "login" in current_url:
                if attempt % 5 == 0:
                    print(f"   [Đăng nhập] Đang đợi nhập tài khoản / mật khẩu... ({attempt*2}s)")

            await asyncio.sleep(2)

        if not logged_in:
            print("\n❌ Quá thời gian chờ đăng nhập (5 phút). Vui lòng thử lại!")
            await context.close()
            return False

        print(f"\n🎉 XÁC NHẬN ĐĂNG NHẬP THÀNH CÔNG!")
        print(f"👤 Facebook User ID: {user_id}")
        print("⏳ Đang lưu session & cookies...")
        await asyncio.sleep(3)

        # Lấy lại danh sách cookies đầy đủ nhất
        cookies = await context.cookies()
        with open(COOKIES_PATH, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"✅ Đã lưu {len(cookies)} cookies vào {COOKIES_PATH}")
        print("🚀 Session sẵn sàng! Bạn có thể đóng trình duyệt này.")
        
        await asyncio.sleep(2)
        await context.close()
        return True


if __name__ == "__main__":
    asyncio.run(export_cookies())
