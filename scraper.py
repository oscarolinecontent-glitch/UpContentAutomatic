"""
SCRAPER MODULE - Thu thập phòng trọ từ hifriendz.com
Hỗ trợ:
- Cào danh sách dự án / phòng từ trang tìm kiếm
- Cào chi tiết phòng đầy đủ (Nội thất, Tiện ích, Phụ phí, Quy định, Toàn bộ ảnh)
"""
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_URL = "https://hifriendz.com"
SEARCH_URL = f"{BASE_URL}/tim-kiem"
CACHE_PATH = Path("./data/rooms_cache.json")


def scrape_room_detail(url: str) -> dict:
    """
    Cào đầy đủ thông tin chi tiết của 1 phòng từ URL HiFriendz (hỗ trợ cả /phong/ và /du-an/).
    Trả về dict chứa:
    - title, price, address
    - stats: Diện tích, Loại phòng, Nội thất
    - amenities_room, amenities_project
    - specs: Phụ phí (Điện, Nước, Xe, Dịch vụ), Quy định (Cọc, HĐ, Số người, Xe, Thú cưng, Giờ giấc)
    - images: TOÀN BỘ ảnh của phòng đó (URL public _400x400)
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # Nếu là link du-an, tìm LST ID đầu tiên để lấy chi tiết phòng thực tế
    if "/du-an/" in url:
        try:
            r_proj = httpx.get(url, headers=headers, timeout=12)
            lst_matches = re.findall(r'LST-[a-zA-Z0-9]+', r_proj.text)
            valid_lsts = [l for l in lst_matches if len(l) > 10]
            if valid_lsts:
                url = f"https://hifriendz.com/phong/{valid_lsts[0]}"
                print(f"[Scraper] Đã chuyển đổi link dự án sang link phòng: {url}")
        except Exception as e:
            print(f"[Scraper] Lỗi chuyển đổi dự án: {e}")

    r = httpx.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    
    # 1. Title & Address & Price
    title_el = soup.select_one(".ps-detail-title, h1")
    title = title_el.get_text(strip=True) if title_el else "Phòng cho thuê"
    
    price_el = soup.select_one(".ps-book-price, .ps-book-bar-price")
    price = price_el.get_text(strip=True) if price_el else "Liên hệ"
    
    addr = ""
    for el in soup.select(".ps-detail-address, .ps-detail-sub, [class*='address']"):
        t = el.get_text(strip=True)
        if t and len(t) > 5:
            addr = t
            break
    if not addr and soup.title and "·" in soup.title.string:
        parts = soup.title.string.split("·")
        if len(parts) >= 3:
            addr = parts[2].split("|")[0].strip()

    # 2. Stats (Diện tích, Loại phòng, Nội thất)
    stats = {}
    for st in soup.select(".ps-stat"):
        lbl = st.select_one(".ps-stat-label")
        val = st.select_one(".ps-stat-value")
        if lbl:
            lbl_txt = lbl.get_text(strip=True)
            val_txt = val.get_text(strip=True) if val else st.get_text(strip=True).replace(lbl_txt, "").strip()
            stats[lbl_txt] = val_txt

    # 3. Specs (Phụ phí, Quy định)
    specs = {}
    for sp in soup.select(".ps-spec"):
        lbl = sp.select_one(".ps-spec-label")
        val = sp.select_one(".ps-spec-value")
        if lbl and val:
            specs[lbl.get_text(strip=True)] = val.get_text(strip=True)

    # 4. Amenities (Nội thất phòng, Tiện ích dự án)
    amenities_room = []
    amenities_project = []
    for sec in soup.select(".ps-dsection"):
        sec_title_el = sec.select_one(".ps-dsection-title")
        if not sec_title_el:
            continue
        sec_title = sec_title_el.get_text(strip=True)
        if "Nội thất phòng" in sec_title:
            for child in sec.children:
                if child != sec_title_el and hasattr(child, "get_text"):
                    parts = [p.strip() for p in re.split(r'[\n\r]+', child.get_text("\n", strip=True)) if p.strip()]
                    for p in parts:
                        if p not in ["Nội thất phòng", "·"] and p not in amenities_room:
                            amenities_room.append(p)
        elif "Tiện ích dự án" in sec_title:
            for child in sec.children:
                if child != sec_title_el and hasattr(child, "get_text"):
                    parts = [p.strip() for p in re.split(r'[\n\r]+', child.get_text("\n", strip=True)) if p.strip()]
                    for p in parts:
                        if p not in ["Tiện ích dự án", "·"] and p not in amenities_project:
                            amenities_project.append(p)

    if "Nước nóng" in amenities_room and "NLMT" in amenities_room:
        amenities_room = [x for x in amenities_room if x not in ["Nước nóng", "NLMT"]]
        amenities_room.append("Nước nóng NLMT")

    # 5. TOÀN BỘ ẢNH CỦA PHÒNG ĐÓ
    room_images = []
    seen = set()
    for img in soup.select(".ps-gallery-thumb img, .ps-gallery-slide img"):
        src = img.get("src", "").split("?")[0]
        if not src or "firebase" not in src:
            continue
        base_id = src.split("/")[-1].split("_")[0]
        if base_id not in seen:
            seen.add(base_id)
            if "_400x400" not in src:
                src = re.sub(r'(\.jpg|\.png|\.jpeg)', r'_400x400\1', src)
            src = src.replace("_800x800_400x400", "_400x400")
            room_images.append(src)

    # Fallback nếu không có gallery
    if not room_images:
        matches = re.findall(r'https://storage\.googleapis\.com/hifriendz-agent\.firebasestorage\.app/listings/uploads/[^"\'\s<>\\]+', r.text)
        for m in matches:
            u = m.split("?")[0]
            base_id = u.split("/")[-1].split("_")[0]
            if base_id not in seen:
                seen.add(base_id)
                if "_400x400" not in u:
                    u = re.sub(r'(\.jpg|\.png|\.jpeg)', r'_400x400\1', u)
                u = u.replace("_800x800_400x400", "_400x400")
                room_images.append(u)

    room_id = url.split("/")[-1]
    
    return {
        "id": room_id,
        "url": url,
        "title": title,
        "price": price,
        "address": addr,
        "stats": stats,
        "amenities_room": amenities_room,
        "amenities_project": amenities_project,
        "specs": specs,
        "images": room_images,
        "features": amenities_room + amenities_project,
        "scraped_at": datetime.now().isoformat(),
    }


async def _scrape_with_browser() -> list[dict]:
    """Dùng Playwright để cào trang tìm kiếm Next.js."""
    rooms = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            locale="vi-VN",
        )
        page = await context.new_page()
        
        print(f"[Scraper] Đang mở {SEARCH_URL}...")
        await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1.5)
        
        cards = await page.query_selector_all("a.ps-card--project, a.ps-card--room, a.ps-card")
        print(f"[Scraper] Tìm thấy {len(cards)} card")
        
        for card in cards:
            try:
                href = await card.get_attribute("href") or ""
                match = re.search(r'/(du-an|phong)/([^/?]+)', href)
                if not match:
                    continue
                full_url = f"{BASE_URL}{href}" if href.startswith("/") else href
                
                # Cào chi tiết phòng
                room_data = scrape_room_detail(full_url)
                if room_data and room_data.get("images"):
                    rooms.append(room_data)
            except Exception as e:
                print(f"[Scraper] Lỗi parse card: {e}")
        
        await browser.close()
    
    return rooms


async def fetch_room_list() -> list[dict]:
    """Cào danh sách phòng từ website (async)."""
    try:
        rooms = await _scrape_with_browser()
        print(f"[Scraper] Tổng: {len(rooms)} phòng chi tiết với đầy đủ ảnh")
        return rooms
    except Exception as e:
        print(f"[Scraper] Lỗi: {e}")
        return load_cache()


def save_cache(rooms: list[dict]):
    """Lưu danh sách phòng vào cache."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "rooms": rooms
        }, f, ensure_ascii=False, indent=2)
    print(f"[Cache] Đã lưu {len(rooms)} phòng vào cache")


def load_cache() -> list[dict]:
    """Đọc cache phòng từ file."""
    if not CACHE_PATH.exists():
        return []
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rooms", [])
    except Exception:
        return []


if __name__ == "__main__":
    print("Testing scrape_room_detail directly...")
    sample = scrape_room_detail("https://hifriendz.com/phong/LST-j5lDANYdYz9dmlmRQWBq")
    print(f"Title: {sample['title']}")
    print(f"Price: {sample['price']}")
    print(f"Address: {sample['address']}")
    print(f"Stats: {sample['stats']}")
    print(f"Total photos: {len(sample['images'])}")
    for img in sample['images']:
        print(" ", img)
