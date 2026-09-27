"""
COMMENT MONITOR - Quét bình luận trên các bài đã đăng
Phát hiện comment mới và báo ngay qua Telegram
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

POSTED_LOG = Path("./data/posted_log.json")
SEEN_COMMENTS = Path("./data/seen_comments.json")
CHECK_INTERVAL_MINUTES = 15  # Quét mỗi 15 phút


def load_seen_comments() -> set:
    """Load danh sách comment đã thấy (tránh báo trùng)."""
    if not SEEN_COMMENTS.exists():
        return set()
    try:
        with open(SEEN_COMMENTS, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen_comments(seen: set):
    SEEN_COMMENTS.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_COMMENTS, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)


def get_recent_posts() -> list[dict]:
    """Lấy các bài đăng thành công trong 48h gần nhất."""
    if not POSTED_LOG.exists():
        return []
    try:
        with open(POSTED_LOG, encoding="utf-8") as f:
            log = json.load(f)
        
        cutoff = datetime.now() - timedelta(hours=48)
        recent = []
        for entry in log:
            if entry.get("status") != "success":
                continue
            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts > cutoff and entry.get("post_url"):
                    recent.append(entry)
            except Exception:
                continue
        
        return recent
    except Exception:
        return []


async def check_comments_on_post(page, post_url: str) -> list[dict]:
    """Lấy danh sách comment mới nhất trên 1 bài đăng."""
    comments = []
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        
        # Scroll để load comment
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(2)
        
        # Tìm các comment element
        comment_els = await page.query_selector_all('[aria-label*="Bình luận"], .UFIComment, [data-testid="UFI2Comment"]')
        
        for el in comment_els[:20]:  # Chỉ lấy 20 comment đầu
            try:
                # Tên người comment
                name_el = await el.query_selector('a[role="link"], strong')
                name = await name_el.inner_text() if name_el else "Ẩn danh"
                
                # Nội dung comment
                text_el = await el.query_selector('[data-testid="UFI2CommentBody"], div[dir="auto"]')
                text = await text_el.inner_text() if text_el else ""
                
                # Tạo unique ID cho comment
                comment_id = f"{post_url}:{name}:{text[:30]}"
                
                if name and text:
                    comments.append({
                        "commenter_name": name,
                        "comment_text": text,
                        "post_url": post_url,
                        "comment_id": comment_id,
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[Monitor] Lỗi check comment {post_url}: {e}")
    
    return comments


async def run_comment_monitor():
    """Vòng lặp quét comment liên tục."""
    from telegram_bot import notify_comment
    from fb_poster import load_facebook_session
    
    print("👁️  Comment Monitor đang khởi động...")
    seen = load_seen_comments()
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await load_facebook_session(browser)
        
        while True:
            print(f"[Monitor] Quét comment lúc {datetime.now().strftime('%H:%M')}...")
            
            posts = get_recent_posts()
            print(f"[Monitor] Kiểm tra {len(posts)} bài đăng gần đây")
            
            for post in posts:
                post_url = post.get("post_url", "")
                if not post_url:
                    continue
                
                comments = await check_comments_on_post(page, post_url)
                
                for comment in comments:
                    cid = comment["comment_id"]
                    if cid not in seen:
                        seen.add(cid)
                        
                        # Thêm thông tin phòng vào comment
                        comment["post_title"] = post.get("room_title", "")
                        comment["group_name"] = post.get("group_url", "")
                        
                        print(f"[Monitor] 🔔 Comment mới từ: {comment['commenter_name']}")
                        await notify_comment(comment)
                
                await asyncio.sleep(3)  # Delay giữa mỗi bài
            
            save_seen_comments(seen)
            
            # Chờ trước lần quét tiếp theo
            wait_sec = CHECK_INTERVAL_MINUTES * 60
            print(f"[Monitor] ⏳ Chờ {CHECK_INTERVAL_MINUTES} phút...")
            await asyncio.sleep(wait_sec)
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_comment_monitor())
