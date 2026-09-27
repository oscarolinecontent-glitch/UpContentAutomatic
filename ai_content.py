"""
AI CONTENT ENGINE - Tạo nội dung bài đăng Facebook chuẩn văn phong HiFriendz
Theo yêu cầu:
1. Giữ nguyên 100% văn phong copy chuẩn của HiFriendz (thông tin, nội thất, tiện ích, phụ phí, quy định)
2. Thêm tiêu đề IN HOA ở đầu bài
3. Thêm liên hệ Zalo ở cuối bài
4. Còn lại không thêm bất cứ thứ gì (không AI văn vở, không hashtag, không link website)
"""
import random
import os
from dotenv import load_dotenv

load_dotenv()

CONTACT_ZALO = os.getenv("CONTACT_ZALO", "0769593713")


def clean_amenities_list(items: list) -> list:
    """Lọc và chuẩn hóa danh sách tiện nghi."""
    res = []
    for x in items:
        x = str(x).strip("· ").strip()
        if x and x not in ["·", "Có", "Chung", "Không"] and x not in res:
            res.append(x)
    if "Nước nóng" in res and "NLMT" in res:
        res = [x for x in res if x not in ["Nước nóng", "NLMT"]]
        res.append("Nước nóng NLMT")
    return res


def generate_fb_post(room: dict, style: str = None) -> str:
    """
    Format nội dung bài đăng Facebook:
    - Tiêu đề IN HOA ở đầu
    - Toàn bộ văn phong copy nguyên bản từ HiFriendz
    - Zalo ở cuối bài
    - Không thêm bất kỳ thứ gì khác
    """
    title_raw = room.get("title", "Phòng cho thuê")
    room_code = title_raw.split("·")[-1].strip() if "·" in title_raw else title_raw
    room_type = room.get("stats", {}).get("Loại phòng", "")
    price = room.get("price", "Giá tốt")
    addr = room.get("address", "")
    
    # Xác định khu vực để đưa vào tiêu đề IN HOA
    dist = ""
    for d in ["Thủ Đức", "Quận 9", "Quận 2", "Bình Thạnh", "Quận 1", "Quận 7", "Quận 10", "Gò Vấp", "Tân Bình", "Phú Nhuận", "Quận 3"]:
        if d.lower() in addr.lower():
            dist = d
            break

    code_up = room_code.upper() if room_code else ""
    type_up = room_type.upper() if room_type else ""
    dist_up = dist.upper() if dist else ""

    # Các mẫu tiêu đề IN HOA bắt mắt
    header_options = []
    if type_up and code_up and dist_up:
        header_options.append(f"🔥 PHÒNG {type_up} {code_up} - {dist_up} - VÀO Ở NGAY! 🔥")
        header_options.append(f"🔥 CĂN HỘ {type_up} {code_up} - {dist_up} - FULL TIỆN NGHI! 🔥")
    elif code_up and dist_up:
        header_options.append(f"🔥 PHÒNG {code_up} - {dist_up} - VÀO Ở NGAY! 🔥")
    elif dist_up:
        header_options.append(f"🔥 PHÒNG ĐẸP GIÁ TỐT {dist_up} - VÀO Ở NGAY! 🏠✨")
    else:
        header_options.append("🔥 PHÒNG ĐẸP GIÁ TỐT - VÀO Ở NGAY! 🏠✨")

    header = random.choice(header_options)

    # Dựng nội dung chuẩn 100% văn phong copy HiFriendz
    lines = [header, ""]

    # Tên phòng & Giá
    price_str = price
    if not any(price_str.endswith(s) for s in ["/tháng", "đ/tháng"]):
        price_str = f"{price_str}/tháng"
    if not price_str.endswith("đ/tháng") and "đ" not in price_str:
        price_str = price_str.replace("/tháng", "đ/tháng")

    display_name = f"Phòng {room_code}" if room_code else "Phòng cho thuê"
    lines.append(f"🏠 {display_name} - {price_str}")

    if addr:
        lines.append(f"📍 {addr}")

    stats = room.get("stats", {})
    t = [stats.get("Loại phòng"), stats.get("Diện tích"), stats.get("Nội thất") or stats.get("furnitureLevel")]
    t_line = " · ".join([x for x in t if x])
    if t_line:
        lines.append(f"🛏 {t_line}")

    # Tiện nghi nổi bật
    features = clean_amenities_list(room.get("amenities_room", []))
    if features:
        lines.append(f"✨ {', '.join(features[:8])}")

    def add_section(icon, sec_name, items):
        if items:
            lines.append("")
            lines.append(f"{icon} {sec_name.upper()}:")
            for item in items:
                lines.append(f"- {item}")

    add_section("🛋", "Nội thất phòng", features)

    proj_amenities = clean_amenities_list(room.get("amenities_project", []))
    add_section("🏢", "Tiện ích dự án", proj_amenities)

    # Phụ phí
    specs = room.get("specs", {})
    surcharge_lines = []
    if "Điện" in specs:
        surcharge_lines.append(f"Điện: {specs['Điện']}đ/kwh" if "kwh" not in specs['Điện'] else f"Điện: {specs['Điện']}")
    if "Nước" in specs:
        surcharge_lines.append(f"Nước: {specs['Nước']}đ/khối" if "khối" not in specs['Nước'] else f"Nước: {specs['Nước']}")
    if "Gửi xe" in specs:
        surcharge_lines.append(f"Gửi xe: {specs['Gửi xe']}")
    if "Dịch vụ" in specs:
        surcharge_lines.append(f"Dịch vụ: {specs['Dịch vụ']}đ/phòng" if "phòng" not in specs['Dịch vụ'] else f"Dịch vụ: {specs['Dịch vụ']}")
    add_section("📝", "Phụ phí", surcharge_lines)

    # Quy định (loại bỏ cọc, giữ phòng, khách nước ngoài)
    regulation_lines = []
    reg_keys = [
        ("Hợp đồng (tháng)", "Hợp đồng: {val} tháng"),
        ("Số người tối đa", "Số người tối đa: {val} người"),
        ("Số xe tối đa", "Số xe tối đa: {val} xe"),
        ("Thú cưng", "Thú cưng: {val}"),
        ("Giờ giấc", "Giờ giấc: {val}"),
    ]
    for k, fmt in reg_keys:
        if k in specs:
            val = specs[k]
            regulation_lines.append(fmt.format(val=val))
    add_section("📋", "Quy định", regulation_lines)

    # Zalo ở cuối bài (không thêm gì khác)
    lines.append("")
    lines.append(f"👉 Liên hệ / Zalo: {CONTACT_ZALO}")

    return "\n".join(lines)


if __name__ == "__main__":
    from scraper import scrape_room_detail
    room = scrape_room_detail("https://hifriendz.com/phong/LST-j5lDANYdYz9dmlmRQWBq")
    print("Testing generate_fb_post...")
    post = generate_fb_post(room)
    print("\n--- BÀI ĐĂNG THEO YÊU CẦU ---")
    print(post)
