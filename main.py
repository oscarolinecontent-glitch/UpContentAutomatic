"""
MAIN ORCHESTRATOR - Điều phối toàn bộ hệ thống
Chạy lệnh này để vận hành hệ thống:
  python main.py scrape    → Cào dữ liệu phòng mới
  python main.py post      → Đăng bài vào Facebook
  python main.py bot       → Khởi động Telegram bot
  python main.py report    → Gửi báo cáo hôm nay
  python main.py all       → Cào + Đăng + Bot (chế độ full)
  python main.py test_ai   → Test AI tạo content
  python main.py get_chatid → Lấy Telegram Chat ID
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()


async def cmd_scrape():
    """Cào dữ liệu phòng từ hifriendz.com."""
    from scraper import fetch_room_list, save_cache
    print("🔍 Đang cào dữ liệu phòng trọ...")
    rooms = await fetch_room_list()
    if rooms:
        save_cache(rooms)
        print(f"✅ Đã lưu {len(rooms)} phòng vào cache")
    else:
        print("⚠️  Không tìm được phòng nào. Kiểm tra kết nối internet.")
    return rooms


async def cmd_post():
    """Đăng bài vào các nhóm Facebook."""
    from scraper import load_cache, fetch_room_list, save_cache
    from ai_content import generate_fb_post
    from fb_poster import run_posting_session, post_to_specific_group
    from telegram_bot import notify_post_success
    
    # Hỗ trợ đăng 1 bài cụ thể nếu có tham số dòng lệnh
    if len(sys.argv) > 2:
        arg2 = sys.argv[2]
        arg3 = sys.argv[3] if len(sys.argv) > 3 else None
        target_group = arg2 if "facebook" in arg2 else "https://www.facebook.com/share/g/1EyweyiC64/"
        target_room = arg3 if arg3 else (arg2 if "hifriendz" in arg2 else None)
        print(f"🚀 Đăng 1 bài tùy chọn vào nhóm: {target_group}")
        await post_to_specific_group(target_group, room=target_room, headless=False)
        return
        
    # Lấy danh sách phòng
    rooms = load_cache()
    if not rooms:
        print("📥 Cache trống, đang cào dữ liệu mới...")
        rooms = await fetch_room_list()
        save_cache(rooms)
    
    if not rooms:
        print("❌ Không có phòng nào để đăng!")
        return
    
    print(f"📋 Có {len(rooms)} phòng trong kho")
    
    # Chạy phiên đăng bài tự động theo quota
    await run_posting_session(
        rooms=rooms,
        ai_content_fn=generate_fb_post,
        telegram_notify_fn=notify_post_success,
    )


async def cmd_bot():
    """Khởi động Telegram bot."""
    from telegram_bot import start_bot
    await start_bot()


async def cmd_monitor():
    """Quét bình luận khách hàng trên các bài đã đăng và gửi thông báo tức thì."""
    from comment_monitor import run_comment_monitor
    await run_comment_monitor()


async def cmd_report():
    """Gửi báo cáo tổng kết."""
    from telegram_bot import send_daily_report
    print("📊 Đang gửi báo cáo...")
    await send_daily_report()
    print("✅ Đã gửi báo cáo!")


async def cmd_test_ai():
    """Test nội dung bài đăng theo đúng chuẩn yêu cầu."""
    from scraper import load_cache, scrape_room_detail
    from ai_content import generate_fb_post
    
    rooms = load_cache()
    if rooms:
        room = rooms[0]
        if not room.get("specs") and room.get("url"):
            room = scrape_room_detail(room["url"])
    else:
        room = scrape_room_detail("https://hifriendz.com/phong/LST-j5lDANYdYz9dmlmRQWBq")
        
    print(f"🏠 Test phòng: {room.get('title')}")
    print("\n📝 Nội dung xuất ra:\n")
    print("=" * 50)
    print(generate_fb_post(room))
    print("=" * 50)


async def cmd_get_chatid():
    """Lấy Telegram Chat ID."""
    from telegram_bot import get_my_chat_id
    print("📱 Lấy Chat ID Telegram...")
    print("   (Đảm bảo bạn đã nhắn tin /start cho bot trên Telegram!)")
    chat_id = await get_my_chat_id()
    if chat_id:
        print(f"\n✅ Chat ID: {chat_id}")
        print(f"   Thêm vào file .env: TELEGRAM_CHAT_ID={chat_id}")


async def cmd_all():
    """Chạy toàn bộ: cào → đăng bài → bot chờ lệnh + quét comment song song."""
    print("🚀 Khởi động hệ thống HiFriendz Auto...")
    print()
    
    # 1. Cào dữ liệu
    await cmd_scrape()
    print()
    
    # 2. Chạy bot và comment monitor song song
    bot_task = asyncio.create_task(cmd_bot())
    monitor_task = asyncio.create_task(cmd_monitor())
    
    await asyncio.sleep(3)
    
    # 3. Đăng bài
    await cmd_post()
    
    # 4. Duy trì các service
    print("\n🤖 Hệ thống đang hoạt động ngầm (Bot Telegram + Quét Comment). Nhấn Ctrl+C để dừng.")
    await asyncio.gather(bot_task, monitor_task)


def print_help():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                 🏠 HIFRIENDZ AUTO SYSTEM v2.0                 ║
╠═══════════════════════════════════════════════════════════════╣
║  python main.py scrape          Cào phòng mới & ảnh đầy đủ    ║
║  python main.py post            Đăng bài Facebook theo lịch   ║
║  python main.py post [room_url] Đăng ngay 1 phòng chỉ định    ║
║  python main.py bot             Khởi động Telegram bot        ║
║  python main.py monitor         Bật quét comment khách hàng   ║
║  python main.py report          Gửi báo cáo hôm nay           ║
║  python main.py test_ai         Xem trước format bài đăng     ║
║  python main.py all             Vận hành toàn bộ hệ thống     ║
╚═══════════════════════════════════════════════════════════════╝
""")


async def main():
    if len(sys.argv) < 2:
        print_help()
        return
    
    cmd = sys.argv[1].lower()
    
    commands = {
        "scrape": cmd_scrape,
        "post": cmd_post,
        "bot": cmd_bot,
        "monitor": cmd_monitor,
        "report": cmd_report,
        "test_ai": cmd_test_ai,
        "get_chatid": cmd_get_chatid,
        "all": cmd_all,
    }
    
    if cmd not in commands:
        print(f"❌ Lệnh không hợp lệ: {cmd}")
        print_help()
        return
    
    await commands[cmd]()


if __name__ == "__main__":
    asyncio.run(main())
