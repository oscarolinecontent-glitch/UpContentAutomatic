"""
TELEGRAM BOT - Trung tâm điều khiển và báo cáo
Features:
- Báo tức thì khi có comment mới trên Facebook
- Báo cáo tổng kết hàng ngày lúc 21:30
- Nhận lệnh: /status /post_now /list_rooms /report
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

LOG_PATH = Path("./data/activity_log.json")
POSTED_PATH = Path("./data/posted_today.json")


# ─────────────────────────────────────────────
#  GỬI TIN NHẮN
# ─────────────────────────────────────────────
async def send_message(text: str, chat_id: str = None, parse_mode: str = "HTML") -> dict:
    """Gửi tin nhắn Telegram."""
    cid = chat_id or CHAT_ID
    if not cid:
        print("[Telegram] Chưa cấu hình TELEGRAM_CHAT_ID")
        return {}
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/sendMessage", json={
            "chat_id": cid,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        })
        res = resp.json()
        if not res.get("ok"):
            err_desc = res.get("description", "")
            print(f"[Telegram Error] Gửi tin thất bại: {err_desc}")
            if "can't parse entities" in err_desc.lower():
                # Fallback gửi dạng text thuần nếu lỗi định dạng HTML
                resp_fallback = await client.post(f"{API_BASE}/sendMessage", json={
                    "chat_id": cid,
                    "text": text,
                    "disable_web_page_preview": False,
                })
                return resp_fallback.json()
        return res


async def send_photo(image_url: str, caption: str, chat_id: str = None) -> dict:
    """Gửi ảnh kèm caption."""
    cid = chat_id or CHAT_ID
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/sendPhoto", json={
            "chat_id": cid,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML",
        })
        return resp.json()


# ─────────────────────────────────────────────
#  THÔNG BÁO ĐẶC BIỆT
# ─────────────────────────────────────────────
async def notify_comment(comment_data: dict):
    """🔔 Báo tức thì khi có comment mới trên bài đăng."""
    post_title = comment_data.get("post_title", "Bài đăng phòng")
    commenter = comment_data.get("commenter_name", "Khách hàng")
    comment_text = comment_data.get("comment_text", "")
    post_url = comment_data.get("post_url", "")
    group_name = comment_data.get("group_name", "Nhóm Facebook")
    timestamp = datetime.now().strftime("%H:%M %d/%m")
    
    msg = (
        f"🔔 <b>CÓ KHÁCH HỎI PHÒNG!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Tên khách:</b> {commenter}\n"
        f"💬 <b>Nội dung:</b> <i>{comment_text}</i>\n"
        f"📍 <b>Nhóm:</b> {group_name}\n"
        f"🏠 <b>Bài:</b> {post_title}\n"
        f"🕐 <b>Lúc:</b> {timestamp}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <a href='{post_url}'>Bấm vào đây để trả lời ngay!</a>\n\n"
        f"⚡ <b>Rep trong 3 phút đầu = tăng 70% cơ hội chốt phòng!</b>"
    )
    
    result = await send_message(msg)
    _log_activity("comment_alert", comment_data)
    return result


async def notify_post_success(post_data: dict):
    """✅ Báo khi đăng bài thành công."""
    import html
    group_name = html.escape(str(post_data.get("group_name", "Nhóm")))
    room_title = html.escape(str(post_data.get("room_title", "Phòng")))
    post_url = post_data.get("post_url", "")
    content = post_data.get("content", "")
    
    content_html = f"\n\n📝 <b>Nội dung đã đăng:</b>\n{html.escape(content)}" if content else ""
    
    msg = (
        f"✅ <b>ĐÃ ĐĂNG BÀI THÀNH CÔNG</b>\n"
        f"📍 <b>Nhóm:</b> {group_name}\n"
        f"🏠 <b>Phòng:</b> {room_title}\n"
        f"🔗 <a href='{post_url}'>Bấm vào đây để xem bài</a>"
        f"{content_html}"
    )
    
    await send_message(msg)
    _log_activity("post_success", post_data)


async def notify_post_failed(post_data: dict, error: str):
    """❌ Báo khi đăng bài thất bại."""
    msg = (
        f"❌ <b>Đăng bài thất bại</b>\n"
        f"📍 Nhóm: {post_data.get('group_name', '?')}\n"
        f"🏠 Phòng: {post_data.get('room_title', '?')}\n"
        f"⚠️ Lỗi: <code>{error[:200]}</code>"
    )
    await send_message(msg)


async def send_daily_report():
    """📊 Báo cáo tổng kết cuối ngày."""
    log = _load_log_today()
    
    posts_ok = [e for e in log if e["type"] == "post_success"]
    posts_fail = [e for e in log if e["type"] == "post_failed"]
    comments = [e for e in log if e["type"] == "comment_alert"]
    
    today = datetime.now().strftime("%d/%m/%Y")
    
    # Tính tổng phòng được hỏi (unique)
    rooms_inquired = len(set([c["data"].get("post_title", "") for c in comments]))
    
    report = (
        f"📊 <b>BÁO CÁO HOẠT ĐỘNG - {today}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Bài đã đăng:</b> {len(posts_ok)} thành công, {len(posts_fail)} thất bại\n"
        f"💬 <b>Lượt hỏi phòng:</b> {len(comments)} comment\n"
        f"🏠 <b>Phòng được quan tâm:</b> {rooms_inquired} phòng\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    if posts_ok:
        report += f"\n✅ <b>Nhóm đã đăng hôm nay:</b>\n"
        for p in posts_ok[:8]:
            report += f"  • {p['data'].get('group_name', '?')}\n"
    
    if comments:
        report += f"\n🔥 <b>Khách hỏi nhiều nhất:</b>\n"
        for c in comments[:5]:
            name = c["data"].get("commenter_name", "?")
            text = c["data"].get("comment_text", "")[:40]
            report += f"  👤 {name}: <i>{text}...</i>\n"
    
    report += f"\n⏰ Báo cáo lúc {datetime.now().strftime('%H:%M')} | Bot HiFriendz 🤖"
    
    await send_message(report)


# ─────────────────────────────────────────────
#  XỬ LÝ LỆNH BOT
# ─────────────────────────────────────────────
async def get_updates(offset: int = 0, timeout_sec: int = 5) -> list:
    """Lấy các tin nhắn mới gửi đến bot."""
    async with httpx.AsyncClient(timeout=timeout_sec + 5) as client:
        resp = await client.get(f"{API_BASE}/getUpdates", params={
            "offset": offset,
            "timeout": timeout_sec,
            "allowed_updates": ["message"],
        })
        data = resp.json()
        return data.get("result", [])


async def handle_command(message: dict) -> str | None:
    """Xử lý lệnh từ người dùng."""
    text = message.get("text", "").strip()
    if not text:
        return None
        
    chat_id = str(message["chat"]["id"])
    user = message.get("from", {}).get("first_name", "User")
    cmd = text.split()[0].split("@")[0].lower()
    print(f"[Bot] 📩 Nhận lệnh từ {user}: '{text}' (cmd: '{cmd}')")
    
    if cmd == "/start":
        return await send_message(
            "🤖 <b>Bot HiFriendz đang hoạt động!</b>\n\n"
            "Các lệnh có sẵn:\n"
            "• /status - Xem trạng thái hệ thống\n"
            "• /report - Báo cáo hôm nay\n"
            "• /list_rooms - Danh sách phòng hiện tại\n"
            "• /post_now - Kích hoạt đăng bài ngay\n"
            "• /help - Xem hướng dẫn",
            chat_id=chat_id
        )
    
    elif cmd == "/status":
        log = _load_log_today()
        posts_count = len([e for e in log if e.get("type") in ["post_success", "post_ok"]])
        last_post = "Chưa có" if not log else log[-1].get("timestamp", "?")[:16]
        
        return await send_message(
            f"⚙️ <b>Trạng thái hệ thống</b>\n"
            f"🟢 Bot: Hoạt động bình thường\n"
            f"📝 Bài đăng hôm nay: {posts_count}\n"
            f"🕐 Hoạt động gần nhất: {last_post}\n"
            f"💾 Cache phòng: {'Có' if Path('./data/rooms_cache.json').exists() else 'Chưa có'}",
            chat_id=chat_id
        )
    
    elif cmd == "/report":
        await send_daily_report()
    
    elif cmd == "/list_rooms":
        try:
            with open("./data/rooms_cache.json", encoding="utf-8") as f:
                data = json.load(f)
            rooms = data.get("rooms", [])[:10]
            if not rooms:
                return await send_message("⚠️ Chưa có phòng nào trong kho. Hãy cào thêm phòng!", chat_id=chat_id)
            
            msg = f"🏠 <b>Danh sách phòng ({len(rooms)} phòng)</b>\n\n"
            for i, r in enumerate(rooms, 1):
                title = r.get("title", "Phòng cho thuê")
                price = r.get("price", "Liên hệ")
                count = r.get("count", "")
                count_str = f" | {count}" if count else ""
                msg += f"{i}. <b>{title}</b>\n   💰 {price}{count_str}\n\n"
            
            return await send_message(msg, chat_id=chat_id)
        except Exception as e:
            return await send_message(f"⚠️ Lỗi đọc danh sách phòng: {e}", chat_id=chat_id)
    
    elif cmd == "/post_now":
        parts = text.split(maxsplit=1)
        target_room_url = parts[1].strip() if len(parts) > 1 else None
        
        await send_message(
            "⚡ <b>Đã nhận lệnh đăng bài!</b>\n"
            "Bot đang cào toàn bộ ảnh và đăng ngay vào nhóm Facebook...\n"
            "Bạn sẽ nhận thông báo khi hoàn tất.",
            chat_id=chat_id
        )
        
        async def _do_post():
            try:
                from fb_poster import post_to_specific_group
                target_group = "https://www.facebook.com/share/g/1EyweyiC64/"
                await post_to_specific_group(target_group, room=target_room_url, headless=True)
            except Exception as e:
                await send_message(f"❌ Lỗi khi đăng bài: {e}", chat_id=chat_id)
                
        asyncio.create_task(_do_post())
    
    elif cmd == "/help":
        return await send_message(
            "📖 <b>Hướng dẫn sử dụng Bot HiFriendz</b>\n\n"
            "<b>/status</b> - Xem trạng thái hệ thống và số bài đăng hôm nay\n"
            "<b>/report</b> - Xem báo cáo chi tiết hoạt động trong ngày\n"
            "<b>/list_rooms</b> - Xem danh sách phòng đang có trong kho\n"
            "<b>/post_now</b> - Kích hoạt đăng bài ngay lập tức\n\n"
            "💡 Bot tự động:\n"
            "• Đăng bài vào các nhóm Facebook\n"
            "• Báo ngay khi có khách comment hỏi phòng\n"
            "• Gửi báo cáo định kỳ",
            chat_id=chat_id
        )


# ─────────────────────────────────────────────
#  LOG HOẠT ĐỘNG
# ─────────────────────────────────────────────
def _log_activity(event_type: str, data: dict):
    """Ghi log hoạt động vào file JSON."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    logs = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH, encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    
    logs.append({
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    })
    
    # Giữ tối đa 500 log entries
    logs = logs[-500:]
    
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def _load_log_today() -> list:
    """Load các log entry trong ngày hôm nay."""
    if not LOG_PATH.exists():
        return []
    
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            logs = json.load(f)
        
        today = datetime.now().date().isoformat()
        return [l for l in logs if l.get("timestamp", "").startswith(today)]
    except Exception:
        return []


# ─────────────────────────────────────────────
#  LẤY CHAT ID (SETUP LẦN ĐẦU)
# ─────────────────────────────────────────────
async def get_my_chat_id():
    """Lấy Chat ID của bạn — chạy sau khi nhắn tin cho bot."""
    # Dùng offset=-1 để chỉ lấy update mới nhất
    updates = await get_updates(offset=-1, timeout_sec=5)
    if not updates:
        print("⚠️  Chưa có tin nhắn nào. Hãy nhắn /start cho bot trên Telegram trước!")
        return None
    
    for update in updates:
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            first_name = update["message"]["chat"].get("first_name", "")
            username = update["message"]["chat"].get("username", "?")
            print(f"✅ Chat ID của bạn: {chat_id} ({first_name} @{username})")
            print(f"   Thêm vào .env: TELEGRAM_CHAT_ID={chat_id}")
            return chat_id
    
    print("⚠️  Có update nhưng không phải dạng message. Thử nhắn thêm 1 tin nữa cho bot!")
    return None


# ─────────────────────────────────────────────
#  MAIN POLLING LOOP
# ─────────────────────────────────────────────
async def start_bot():
    """Khởi chạy bot polling."""
    print("🤖 Bot Telegram HiFriendz đang khởi động...")
    
    if not CHAT_ID:
        print("⚙️  Lấy Chat ID lần đầu...")
        await get_my_chat_id()
        return
    
    await send_message("🟢 <b>Bot HiFriendz đã khởi động!</b>\nGõ /help để xem các lệnh.")
    
    offset = 0
    print("✅ Bot đang lắng nghe lệnh...")
    
    while True:
        try:
            updates = await get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    await handle_command(update["message"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Bot] Lỗi: {repr(e)}")
        
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(start_bot())
