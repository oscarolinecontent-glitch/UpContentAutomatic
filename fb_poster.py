"""
FACEBOOK POSTER - Tự động đăng bài vào các nhóm Facebook
Dùng Playwright với Chrome session thật (cookie đã đăng nhập sẵn)
Mô phỏng hành vi người dùng thật để tránh bị checkpoint
"""
import asyncio
import json
import os
import random
import re
from pathlib import Path
from datetime import datetime
import httpx
from playwright.async_api import async_playwright, Page, Browser
from dotenv import load_dotenv

load_dotenv()

GROUPS_FILE = Path("./groups.txt") if Path("./groups.txt").exists() else Path("./nhóm")
COOKIES_FILE = Path(os.getenv("FB_COOKIES_PATH", "./data/fb_cookies.json"))
POSTED_LOG = Path("./data/posted_log.json")

# Giới hạn an toàn mỗi ngày
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", 12))
# Delay giữa các lần đăng (giây)
DELAY_MIN = int(os.getenv("POST_DELAY_MIN", 600))   # 10 phút
DELAY_MAX = int(os.getenv("POST_DELAY_MAX", 1500))  # 25 phút


def load_groups() -> list[str]:
    """Đọc danh sách nhóm Facebook từ file."""
    if not GROUPS_FILE.exists():
        print(f"[Poster] Không tìm thấy file nhóm: {GROUPS_FILE}")
        return []
    
    with open(GROUPS_FILE, encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip().startswith("http")]
    
    print(f"[Poster] Đã load {len(lines)} nhóm")
    return lines


def load_posted_log() -> list[dict]:
    """Đọc log bài đã đăng."""
    if not POSTED_LOG.exists():
        return []
    try:
        with open(POSTED_LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_posted_log(log: list[dict]):
    """Lưu log bài đã đăng."""
    POSTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(POSTED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def save_latest_post(room: dict, content: str, group_url: str):
    """Lưu bài viết AI vừa tạo ra file text để người dùng dễ xem."""
    out_file = Path("./data/latest_post.txt")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"=== BÀI ĐĂNG GẦN NHẤT ({datetime.now().strftime('%H:%M:%S %d/%m/%Y')}) ===\n")
        f.write(f"Nhóm: {group_url}\n")
        f.write(f"Phòng: {room.get('title')}\n")
        f.write(f"Giá: {room.get('price')}\n")
        f.write(f"Link phòng: {room.get('url')}\n")
        f.write("-" * 50 + "\n\n")
        f.write(content + "\n")


def get_today_posts() -> list[dict]:
    """Lấy danh sách bài đã đăng hôm nay."""
    log = load_posted_log()
    today = datetime.now().date().isoformat()
    return [p for p in log if p.get("date", "") == today]


def get_group_id_from_url(url: str) -> str:
    """Trích xuất group ID từ URL share."""
    # URL dạng: https://www.facebook.com/share/g/1EyweyiC64/
    match = re.search(r'/share/g/([^/]+)', url)
    return match.group(1) if match else url


async def ensure_room_images(room: dict, max_images: int = 30) -> list[str]:
    """Cào và tải TẤT CẢ ảnh của phòng từ trang chi tiết Hifriendz về máy."""
    detail_url = room.get("url")
    room_id = room.get("id", "room_temp")
    
    img_urls = list(room.get("images", []))
    if not img_urls and detail_url:
        try:
            print(f"[Poster] 🔍 Đang cào toàn bộ thông tin & ảnh từ {detail_url}...")
            from scraper import scrape_room_detail
            detailed = scrape_room_detail(detail_url)
            img_urls = detailed.get("images", [])
            for k, v in detailed.items():
                if k not in room or not room[k]:
                    room[k] = v
        except Exception as e:
            print(f"[Poster] ⚠️ Không cào được danh sách ảnh chi tiết: {e}")
            
    # Fallback về 1 ảnh thumbnail nếu không tìm thấy thêm
    if not img_urls and room.get("image_url"):
        img_urls = [room["image_url"]]
        
    print(f"[Poster] 📸 Tìm thấy {len(img_urls)} ảnh cho phòng này! Chuẩn bị tải toàn bộ...")
    
    img_dir = Path(f"./data/images/{room_id}")
    img_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_paths = []
    async with httpx.AsyncClient() as client:
        for idx, url in enumerate(img_urls[:max_images], 1):
            if "firebase" in url and "_400x400" not in url:
                url = re.sub(r'(\.jpg|\.png|\.jpeg)', r'_400x400\1', url)
            url = url.replace("_800x800_400x400", "_400x400")
            file_path = img_dir / f"img_{idx}.jpg"
            if not file_path.exists() or file_path.stat().st_size < 1000:
                try:
                    resp = await client.get(url, timeout=15)
                    if resp.status_code == 200:
                        with open(file_path, "wb") as f:
                            f.write(resp.content)
                except Exception:
                    continue
            if file_path.exists() and file_path.stat().st_size > 1000:
                downloaded_paths.append(str(file_path.resolve()))
                
    print(f"[Poster] ✅ Đã tải toàn bộ {len(downloaded_paths)} ảnh của phòng!")
    return downloaded_paths


# ─────────────────────────────────────────────
#  PLAYWRIGHT BROWSER HELPERS
# ─────────────────────────────────────────────
async def _human_type(page: Page, selector: str, text: str):
    """Gõ văn bản như người thật (random delay giữa các ký tự)."""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.5, 1.2))
    
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.03, 0.12))
    
    await asyncio.sleep(random.uniform(0.5, 1.0))


async def _random_scroll(page: Page):
    """Cuộn trang ngẫu nhiên để giống người dùng thật."""
    for _ in range(random.randint(2, 4)):
        scroll_y = random.randint(200, 600)
        await page.evaluate(f"window.scrollBy(0, {scroll_y})")
        await asyncio.sleep(random.uniform(0.8, 2.0))


async def load_facebook_session(browser: Browser) -> Page:
    """Tạo page Facebook với session đã đăng nhập từ cookies."""
    context_options = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "locale": "vi-VN",
    }
    
    if COOKIES_FILE.exists():
        with open(COOKIES_FILE, encoding="utf-8") as f:
            cookies = json.load(f)
        context = await browser.new_context(**context_options)
        await context.add_cookies(cookies)
        print("[Poster] Đã load Facebook session từ cookies")
    else:
        print("[Poster] ⚠️  Không có cookies! Cần export cookies trước.")
        print("[Poster]    Xem hướng dẫn: chạy python setup_fb_session.py")
        context = await browser.new_context(**context_options)
    
    page = await context.new_page()
    return page


async def check_if_logged_in(page: Page) -> bool:
    """Kiểm tra xem đã đăng nhập Facebook chưa."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    await asyncio.sleep(3)
    
    # Nếu có nút login/signup = chưa đăng nhập
    login_btn = await page.query_selector('[data-testid="royal_login_button"], [name="login"]')
    if login_btn:
        print("[Poster] ❌ Chưa đăng nhập Facebook!")
        return False
    
    print("[Poster] ✅ Đã đăng nhập Facebook")
    return True


async def post_to_group(page: Page, group_url: str, content: str, image_paths = None) -> dict:
    """
    Đăng bài vào 1 nhóm Facebook (hỗ trợ nhiều ảnh).
    
    Returns: dict với status và post_url
    """
    result = {
        "group_url": group_url,
        "status": "pending",
        "post_url": "",
        "error": "",
        "timestamp": datetime.now().isoformat(),
    }
    
    try:
        # Navigate đến nhóm
        print(f"[Poster] → Vào nhóm: {group_url}")
        await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(3, 5))
        
        # Cuộn nhẹ để tải trang
        await _random_scroll(page)
        
        # Nếu có tab "Thảo luận", click vào để chuyển sang chế độ đăng bài thông thường
        try:
            discussion_tab = await page.query_selector('div[role="tab"]:has-text("Thảo luận"), a:has-text("Thảo luận")')
            if discussion_tab:
                await discussion_tab.click()
                await asyncio.sleep(random.uniform(1.5, 2.5))
        except Exception:
            pass

        # Tìm ô "Viết gì đó..." hoặc "Bạn viết gì đi..." để tạo bài đăng
        write_box_selectors = [
            'span:has-text("Bạn viết gì đi...")',
            'div[role="button"]:has-text("Bạn viết gì đi...")',
            '[aria-label="Viết gì đó..."]',
            '[aria-label="Tạo bài viết công khai..."]',
            '[aria-label="Tạo bài viết"]',
            '[aria-label="Bạn đang nghĩ gì?"]',
            'div[role="button"]:has-text("Viết gì đó")',
            'div[role="button"]:has-text("Tạo bài viết công khai")',
            'div[role="button"]:has-text("Bạn đang nghĩ gì")',
            'span:text-is("Viết gì đó...")',
            'span:has-text("Viết gì đó")',
            'span:has-text("Tạo bài viết công khai")',
        ]
        
        write_box = None
        for sel in write_box_selectors:
            try:
                write_box = await page.wait_for_selector(sel, timeout=3000)
                if write_box:
                    break
            except Exception:
                continue
        
        if not write_box:
            result["status"] = "failed"
            result["error"] = "Không tìm thấy ô soạn thảo bài viết. Có thể cần tham gia nhóm trước hoặc nhóm yêu cầu duyệt."
            return result
        
        # Click vào ô soạn thảo
        await write_box.click()
        await asyncio.sleep(random.uniform(2, 3))
        
        # Chờ dialog "Tạo bài viết" mở ra
        dialog = page.get_by_role("dialog", name="Tạo bài viết").first
        try:
            await dialog.wait_for(state="visible", timeout=6000)
        except Exception:
            dialog = page.locator('div[role="dialog"]').first
            await dialog.wait_for(state="visible", timeout=5000)
        
        # Gõ nội dung vào ô soạn thảo bên trong dialog
        composer = dialog.locator('div[contenteditable="true"][role="textbox"]').first
        await composer.wait_for(state="visible", timeout=5000)
        await composer.click(force=True)
        await asyncio.sleep(0.5)
        
        # Gõ từng dòng bằng insert_text để giữ nguyên 100% tiếng Việt có dấu và emoji
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line:
                await page.keyboard.insert_text(line)
            await asyncio.sleep(random.uniform(0.04, 0.1))
            if i < len(lines) - 1:
                await page.keyboard.press("Enter")
                await asyncio.sleep(random.uniform(0.08, 0.2))
        
        await asyncio.sleep(random.uniform(1.5, 2.5))
        
        # Upload toàn bộ ảnh phòng (hỗ trợ nhiều ảnh)
        if image_paths:
            if isinstance(image_paths, (str, Path)):
                image_paths = [str(image_paths)]
            valid_paths = [str(Path(p).resolve()) for p in image_paths if Path(p).exists()]
            if valid_paths:
                try:
                    print(f"[Poster] 🖼️ Đang đính kèm {len(valid_paths)} ảnh vào bài đăng...")
                    photo_btn = dialog.locator('div[aria-label="Ảnh/video"], [aria-label*="Ảnh"], [aria-label*="Photo"]').first
                    if await photo_btn.is_visible():
                        await photo_btn.click()
                        await asyncio.sleep(1)
                    file_input = dialog.locator('input[type="file"]').first
                    await file_input.set_input_files(valid_paths)
                    print(f"[Poster] ⏳ Đang đợi {len(valid_paths)} ảnh tải lên Facebook...")
                    await asyncio.sleep(min(12, 3 + len(valid_paths) * 2))
                except Exception as e:
                    print(f"[Poster] ⚠️ Lỗi đính kèm ảnh: {e}")
        
        # Tìm và bấm nút Đăng bên trong dialog
        post_btn = dialog.locator('div[aria-label="Đăng"][role="button"], div[aria-label="Đăng"], div[role="button"]:has-text("Đăng")').first
        await post_btn.wait_for(state="visible", timeout=5000)
        
        if await post_btn.is_visible():
            await asyncio.sleep(random.uniform(0.8, 1.5))
            await post_btn.click(force=True)
            print(f"[Poster] ✅ Đã bấm Đăng!")
            
            # Đợi bài đăng hoàn tất (dialog đóng lại)
            try:
                await dialog.wait_for(state="hidden", timeout=12000)
            except Exception:
                await asyncio.sleep(5)
            
            result["status"] = "success"
            result["post_url"] = page.url  # URL hiện tại sau khi đăng
        else:
            result["status"] = "failed"
            result["error"] = "Không tìm thấy nút Đăng trong dialog"
    
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)[:300]
        print(f"[Poster] ❌ Lỗi: {e}")
    
    return result


# ─────────────────────────────────────────────
#  MAIN POSTING FLOW
# ─────────────────────────────────────────────
async def run_posting_session(rooms: list[dict], ai_content_fn=None, telegram_notify_fn=None):
    """
    Chạy phiên đăng bài tự động.
    
    Args:
        rooms: Danh sách phòng cần đăng
        ai_content_fn: Hàm generate content từ AI
        telegram_notify_fn: Hàm gửi thông báo Telegram
    """
    groups = load_groups()
    if not groups:
        print("[Poster] Không có nhóm nào để đăng!")
        return
    
    today_posts = get_today_posts()
    remaining_quota = MAX_POSTS_PER_DAY - len(today_posts)
    
    if remaining_quota <= 0:
        print(f"[Poster] Đã đăng đủ {MAX_POSTS_PER_DAY} bài hôm nay. Dừng!")
        return
    
    # Chọn nhóm chưa đăng hôm nay
    posted_groups_today = {p.get("group_url", "") for p in today_posts}
    target_groups = [g for g in groups if g not in posted_groups_today]
    target_groups = target_groups[:remaining_quota]
    
    print(f"[Poster] Kế hoạch: đăng {len(target_groups)} nhóm (quota còn: {remaining_quota})")
    
    async with async_playwright() as pw:
        # Dùng Chromium headless
        browser = await pw.chromium.launch(
            headless=True,  # Đổi thành False để xem trực tiếp khi debug
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        
        page = await load_facebook_session(browser)
        
        # Kiểm tra đăng nhập
        if not await check_if_logged_in(page):
            await browser.close()
            print("[Poster] Vui lòng chạy: python setup_fb_session.py để đăng nhập")
            return
        
        log = load_posted_log()
        
        for i, group_url in enumerate(target_groups):
            print(f"\n[Poster] [{i+1}/{len(target_groups)}] Chuẩn bị đăng...")
            
            # Chọn phòng ngẫu nhiên
            room = random.choice(rooms)
            
            # Tạo content AI
            if ai_content_fn:
                content = ai_content_fn(room)
            else:
                content = f"🏠 {room.get('title', '')} - Giá: {room.get('price', '')} | {room.url}"
            
            # Lưu ra file data/latest_post.txt để xem
            save_latest_post(room, content, group_url)
            
            # Tải TẤT CẢ ảnh phòng về máy
            image_paths = await ensure_room_images(room, max_images=30)
            
            # Đăng bài kèm toàn bộ ảnh
            result = await post_to_group(page, group_url, content, image_paths=image_paths)
            
            # Lưu log (kèm toàn bộ nội dung bài viết)
            log_entry = {
                "date": datetime.now().date().isoformat(),
                "group_url": group_url,
                "room_id": room.get("id", ""),
                "room_title": room.get("title", ""),
                "content": content,
                "status": result["status"],
                "post_url": result.get("post_url", ""),
                "timestamp": result["timestamp"],
            }
            log.append(log_entry)
            save_posted_log(log)
            
            # Thông báo Telegram (kèm nội dung bài)
            if telegram_notify_fn:
                if result["status"] == "success":
                    await telegram_notify_fn({
                        "group_name": group_url,
                        "room_title": room.get("title", ""),
                        "content": content,
                        "post_url": result.get("post_url", ""),
                    })
                else:
                    print(f"[Poster] ❌ Thất bại: {result.get('error', '')}")
            
            # Delay ngẫu nhiên giữa các lần đăng (tránh spam)
            if i < len(target_groups) - 1:
                delay = random.randint(DELAY_MIN, DELAY_MAX)
                print(f"[Poster] ⏳ Chờ {delay//60} phút {delay%60} giây trước khi đăng tiếp...")
                await asyncio.sleep(delay)
        
        await browser.close()
        print(f"\n[Poster] ✅ Xong phiên đăng bài! Tổng: {len(target_groups)} bài")


async def post_to_specific_group(group_url: str, room = None, headless: bool = False):
    """Đăng 1 bài vào nhóm cụ thể kèm đầy đủ toàn bộ ảnh và thông tin chi tiết."""
    from ai_content import generate_fb_post
    from telegram_bot import notify_post_success
    from scraper import load_cache, scrape_room_detail
    
    if isinstance(room, str):
        print(f"[Poster] 🔍 Đang cào thông tin chi tiết từ URL: {room}")
        room = scrape_room_detail(room)
    elif not room:
        rooms = load_cache()
        if rooms:
            room = rooms[0]
            if not room.get("specs") and room.get("url"):
                room = scrape_room_detail(room["url"])
        else:
            room = scrape_room_detail("https://hifriendz.com/phong/LST-j5lDANYdYz9dmlmRQWBq")
    elif isinstance(room, dict) and not room.get("specs") and room.get("url"):
        room = scrape_room_detail(room["url"])
    
    print(f"\n🚀 Đang chuẩn bị đăng bài vào nhóm: {group_url}")
    print(f"🏠 Phòng: {room.get('title')}")
    print(f"📍 Địa chỉ: {room.get('address')}")
    print(f"💰 Giá: {room.get('price')}")
    print("🤖 Đang tạo nội dung AI...")
    content = generate_fb_post(room)
    print("─" * 50)
    print(content)
    print("─" * 50)
    
    # Lưu ra file data/latest_post.txt để người dùng xem trực tiếp bất cứ lúc nào
    save_latest_post(room, content, group_url)
    
    # Tải TOÀN BỘ ảnh của phòng
    image_paths = await ensure_room_images(room, max_images=30)
    print(f"[Poster] 🖼️ Sẵn sàng đăng với {len(image_paths)} ảnh!")
    
    async with async_playwright() as pw:
        launch_kwargs = {
            "headless": headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        }
        if os.name == "nt" and not headless:
            launch_kwargs["channel"] = "chrome"
            launch_kwargs["args"].append("--start-maximized")
        browser = await pw.chromium.launch(**launch_kwargs)
        page = await load_facebook_session(browser)
        
        if not await check_if_logged_in(page):
            print("\n❌ Chưa đăng nhập Facebook! Hãy chạy: python setup_fb_session.py")
            await browser.close()
            return False
        
        print("\n⏳ Đang tiến hành đăng bài...")
        result = await post_to_group(page, group_url, content, image_paths=image_paths)
        
        if result["status"] == "success":
            print("\n🎉 ĐĂNG BÀI THÀNH CÔNG!")
            print(f"🔗 Link/URL: {result.get('post_url')}")
            
            # Lưu log để comment_monitor theo dõi khách bình luận
            log = load_posted_log()
            log.append({
                "date": datetime.now().date().isoformat(),
                "group_url": group_url,
                "room_id": room.get("id", ""),
                "room_title": room.get("title", ""),
                "content": content,
                "status": "success",
                "post_url": result.get("post_url", ""),
                "timestamp": datetime.now().isoformat(),
            })
            save_posted_log(log)

            # Báo về Telegram kèm nội dung
            await notify_post_success({
                "group_name": group_url,
                "room_title": room.get("title", ""),
                "content": content,
                "post_url": result.get("post_url", ""),
            })
            print("📱 Đã gửi thông báo về bot Telegram của bạn!")
        else:
            print(f"\n❌ Đăng bài thất bại: {result.get('error')}")
        
        await asyncio.sleep(3)
        await browser.close()
        return result["status"] == "success"


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.facebook.com/share/g/1EyweyiC64/"
    target_room = sys.argv[2] if len(sys.argv) > 2 else "https://hifriendz.com/phong/LST-j5lDANYdYz9dmlmRQWBq"
    asyncio.run(post_to_specific_group(target, room=target_room, headless=False))

