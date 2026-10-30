"""
utils.py – Các hàm tiện ích dùng chung
"""

import config
import random
import string
from datetime import datetime

from config import PRODUCTS


def clean_input(raw: str) -> str:
    """Tách username hoặc UID sạch từ chuỗi nhập vào (link locket.cam, @username hoặc text)"""
    import re
    s = raw.strip().lstrip("@")
    m = re.search(r"locket\.cam/(?:u/)?([^/?#&\s]+)", s, re.I)
    if m:
        s = m.group(1).lstrip("@")
    return s.strip()


def gen_order_id() -> str:
    """Tạo mã đơn hàng ngẫu nhiên 8 ký tự chữ hoa + số."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=8))


def fmt_price(price: int) -> str:
    """Định dạng giá tiền VNĐ: 99000 → 99.000đ"""
    return f"{price:,}đ".replace(",", ".")

def check_and_apply_coupon(code: str, original_price: int) -> dict:
    """
    Kiểm tra mã giảm giá (từ DB do Admin tạo qua lệnh /addcode).
    Trả về dict: {"ok": bool, "code": str, "discount_amount": int, "final_price": int, "desc": str, "error": str}
    """
    code_clean = (code or "").strip().upper()
    if not code_clean:
        return {"ok": False, "error": "Vui lòng nhập mã giảm giá."}

    try:
        import database as db
        db_item = db.get_code(code_clean)
        if db_item and db_item.get("active", True):
            max_uses = db_item.get("max_uses", 0)
            used_count = db_item.get("used_count", 0)
            if max_uses > 0 and used_count >= max_uses:
                return {"ok": False, "error": f"Mã '{code_clean}' đã hết số lượt sử dụng."}
            pct = db_item.get("discount_pct", 0)
            discount_amount = int(original_price * (pct / 100.0))
            discount_amount = min(discount_amount, original_price - 1000)
            final_price = max(1000, original_price - discount_amount)
            return {
                "ok": True,
                "code": code_clean,
                "discount_amount": discount_amount,
                "final_price": final_price,
                "desc": f"Giảm {pct}% tổng đơn hàng",
                "is_db": True
            }
    except Exception:
        pass

    return {"ok": False, "error": f"Mã giảm giá '{code_clean}' không tồn tại hoặc đã hết hạn."}



def fmt_datetime(iso: str | None) -> str:
    if not iso:
        return "—"
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%d/%m/%Y %H:%M")


def product_info(product_key: str) -> dict:
    return PRODUCTS[product_key]


def plan_info(product_key: str, plan_key: str) -> dict:
    return PRODUCTS[product_key]["plans"][plan_key]


def build_product_menu_text() -> str:
    lines = [
        "✨ <b>HỆ THỐNG ALOPREMIUM.SHOP TỰ ĐỘNG</b> ✨",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚡ <b>Kích hoạt siêu tốc qua DNS Profile</b>",
        "🛡 <b>Bảo hành trọn gói — Không cần mật khẩu</b>",
        "💎 <b>Ổn định, mượt mà trên mọi thiết bị iOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        "🛒 <b>DANH SÁCH DỊCH VỤ NỔI BẬT:</b>\n"
    ]
    for pk, pv in PRODUCTS.items():
        lines.append(f"{pv['emoji']} <b>{pv['name'].upper()}</b>")
        lines.append(f"   └ <i>{pv['description']}</i>\n")
    lines.append("👇 <i>Chọn dịch vụ bạn muốn đăng ký bên dưới:</i>")
    return "\n".join(lines)


def build_plan_text(product_key: str) -> str:
    pv = PRODUCTS[product_key]
    lines = [
        f"{pv['emoji']} <b>BẢNG GIÁ {pv['name'].upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 <i>{pv['description']}</i>\n",
        "💎 <b>CÁC GÓI ĐANG MỞ BÁN:</b>"
    ]
    for pk, pln in pv["plans"].items():
        lines.append(f"  • <b>{pln['label']:10s}</b> ➔ <code>{fmt_price(pln['price'])}</code>")
    lines.extend([
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔒 <b>Cam kết:</b> Bảo hành 1 đổi 1 trong suốt thời gian sử dụng.",
        "👇 <i>Chọn gói thời hạn bạn muốn mua bên dưới:</i>"
    ])
    return "\n".join(lines)


def status_emoji(status: str) -> str:
    return {
        "waiting_payment":  "💳",
        "pending_approval": "⏳",
        "pending":          "⏳",
        "done":             "✅",
        "failed":           "❌",
        "rejected":         "🚫",
        "cancelled":        "🚫",
    }.get(status, "❓")

import io
import uuid
from urllib.parse import quote


def get_vietqr_url(amount: int, add_info: str) -> str:
    """
    Tạo link ảnh QR chuyển khoản ngân hàng (chuẩn VietQR / NAPAS định dạng PNG).
    Lưu ý: img.vietqr.io trả về SVG khiến Telegram báo lỗi 'Failed to get HTTP URL content'.
    qr.sepay.vn tạo ảnh PNG chuẩn VietQR tương thích hoàn hảo với Telegram.
    """
    bank_id = getattr(config, "BANK_ID", "TCB")
    account_no = getattr(config, "ACCOUNT_NO", "")
    return (
        f"https://qr.sepay.vn/img?bank={bank_id}&acc={account_no}&template=compact"
        f"&amount={amount}&des={quote(add_info)}"
    )


def generate_qr_code(data: str) -> io.BytesIO:
    """Tạo ảnh QR Code định dạng PNG từ một URL hoặc chuỗi dữ liệu bất kỳ"""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        bio.name = "qrcode.png"
        return bio
    except Exception as e:
        import requests
        # Fallback qua API nếu có vấn đề thư viện
        api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={quote(data)}"
        r = requests.get(api_url, timeout=10)
        bio = io.BytesIO(r.content)
        bio.name = "qrcode.png"
        return bio


def get_qr_image_url(data: str) -> str:
    """Tạo URL ảnh QR code nhanh qua API (dùng cho web hoặc fallback)"""
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(data)}"


def generate_mobileconfig(service_name: str, display_name: str, dns_link: str) -> io.BytesIO:
    """
    Tạo nội dung file cấu hình DNS iOS chuẩn Apple .mobileconfig (PayloadType: Configuration & com.apple.dnsSettings.managed).
    Người dùng chỉ cần bấm mở file trong Telegram trên iPhone là hệ thống tự bung cửa sổ cài đặt DNS Profile.
    """
    clean_name = (display_name or "VIP").replace(" ", "_")
    uuid1 = str(uuid.uuid4())
    uuid2 = str(uuid.uuid4())

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadDisplayName</key>
    <string>{service_name} ({clean_name})</string>
    <key>PayloadDescription</key>
    <string>Cau hinh DNS Profile {service_name} tu dong - @{clean_name}</string>
    <key>PayloadIdentifier</key>
    <string>com.alopremium.profile.{clean_name}</string>
    <key>PayloadOrganization</key>
    <string>AloPremium.shop Service</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>{uuid1}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.dnsSettings.managed</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.alopremium.profile.dns</string>
            <key>PayloadUUID</key>
            <string>{uuid2}</string>
            <key>PayloadDisplayName</key>
            <string>{service_name} VIP DNS</string>
            <key>PayloadDescription</key>
            <string>DNS-over-HTTPS {service_name}</string>
            <key>DNSSettings</key>
            <dict>
                <key>DNSProtocol</key>
                <string>HTTPS</string>
                <key>ServerURL</key>
                <string>{dns_link}</string>
            </dict>
        </dict>
    </array>
</dict>
</plist>"""
    buf = io.BytesIO(xml_content.encode("utf-8"))
    buf.name = f"{service_name.replace(' ', '_')}_{clean_name}.mobileconfig"
    buf.seek(0)
    return buf




