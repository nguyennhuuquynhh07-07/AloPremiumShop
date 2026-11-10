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


def get_dynamic_products() -> dict:
    try:
        import database as db
        return db.get_prices()
    except Exception:
        return PRODUCTS


def product_info(product_key: str) -> dict:
    prods = get_dynamic_products()
    return prods.get(product_key, PRODUCTS.get(product_key, {}))


def plan_info(product_key: str, plan_key: str) -> dict:
    prods = get_dynamic_products()
    return prods.get(product_key, PRODUCTS.get(product_key, {})).get("plans", {}).get(plan_key, {})


def build_product_menu_text() -> str:
    prods = get_dynamic_products()
    banner_line = ""
    try:
        import database as db
        b = db.get_banner_config()
        if b and b.get("enabled", True) and b.get("text"):
            badge = b.get("badge") or "🔥 HOT ƯU ĐÃI"
            banner_line = f"🎉 <b>[{badge}]</b> {b.get('text')}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    except Exception:
        pass

    lines = [
        "✨ <b>HỆ THỐNG ALOPREMIUM.SHOP TỰ ĐỘNG</b> ✨",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        banner_line + "⚡ <b>Kích hoạt siêu tốc qua DNS Profile</b>",
        "🛡 <b>Bảo hành trọn gói — Không cần mật khẩu</b>",
        "💎 <b>Ổn định, mượt mà trên mọi thiết bị iOS</b>",
        f"🌐 <b>Website chính thức:</b> <a href='{getattr(config, 'WEBSITE_URL', 'https://alopremium.shop')}'>AloPremium.Shop</a>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        "🛒 <b>DANH SÁCH DỊCH VỤ NỔI BẬT:</b>\n"
    ]
    for pk, pv in prods.items():
        lines.append(f"{pv['emoji']} <b>{pv['name'].upper()}</b>")
        lines.append(f"   └ <i>{pv['description']}</i>\n")
    lines.append("👇 <i>Chọn dịch vụ bạn muốn đăng ký hoặc mở Website bên dưới:</i>")
    return "\n".join(lines)


def build_plan_text(product_key: str) -> str:
    prods = get_dynamic_products()
    pv = prods.get(product_key, PRODUCTS[product_key])
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


ROOT_CA_CERT_B64 = (
    "MIIDNTCCAh2gAwIBAgIUOQqYkU7yWPiIWMNdvcQ5vM1NKgQwDQYJKoZIhvcNAQEL"
    "BQAwKjETMBEGA1UECgwKTG9ja2V0R29sZDETMBEGA1UEAwwKTG9ja2V0R29sZDAe"
    "Fw0yNjA5MzAxNDI5MDhaFw0zNjA5MjcxNDI5MDhaMCoxEzARBgNVBAoMCkxvY2tl"
    "dEdvbGQxEzARBgNVBAMMCkxvY2tldEdvbGQwggEiMA0GCSqGSIb3DQEBAQUAA4IB"
    "DwAwggEKAoIBAQCSgDJzEKZDUijfA1HYVGAIc9e2LVUsDk82iubefLGBXp6Ia5/F"
    "zGCn7RI4kkM6B4Gzdqcj52nZ2mQkh2hlftsE4SyKGlqnL/+50GnNRV8FkrIWb0UU"
    "I8SK22evSa/SW70CXTtTsezAXT5wodUcOzDZvhI6pxKzySEujg7WxRzYsfq1vr8t"
    "2yGJoV5NP0tqZShWq4RxZ7Tj4HyISHFE9+Upvy/8N2KQMKvMkSEphhxpk645dl+t"
    "F0Q37VV6bqZGVNEO/MdGaPzqMld8V3qbrv5eebIrOZBfZU5hRiTHiqK19FPuvvGx"
    "AjPsKGx27tx6+UoAGRlbQAyNBj7vKNMT6n0tAgMBAAGjUzBRMB0GA1UdDgQWBBT5"
    "dQfm6Eu5mNz5Od9cch7UlizH+jAfBgNVHSMEGDAWgBT5dQfm6Eu5mNz5Od9cch7U"
    "lizH+jAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAXwYJMRJ9n"
    "PpRmS7IVWF0PcuLB9z5q3qanc/x+xOQOH4urgm8NAvHGkHNg7rE64wsMkA1O7GTU"
    "T+NP2pdEDu2/zfocfflvsN1l3Gu3Z193bWhcpvr8q8YgLJ4rP6relyFLIxEQ5FkD"
    "XsXqZFf5QOn6+KgdwdIwqos7knp5quBAKqHZbXXVWWxZgOILe4+8uRBAkG2ppZrZ"
    "E9hocAQ8HlcQOX+FsDQZ74vKCPx+mS9szHJJigHNnJRXHD8Ys1oIOjvDUT2nfMGM"
    "Kk5v1hO2IlF1wsGtaWn3ulMsmth4MVHtEtf5wJq48yc7UBXjaq/h9jnO81d9yyI2"
    "RAYZ52CqMLYR"
)


def generate_mobileconfig(service_name: str, display_name: str, dns_link: str = "") -> io.BytesIO:
    """
    Tạo file cấu hình iOS chuẩn Apple .mobileconfig tích hợp đầy đủ 2 thành phần bắt buộc:
    1. Chứng chỉ bảo mật ROOT CA (com.apple.security.root) để iOS tin cậy xác thực máy chủ.
    2. Cấu hình DoH DNS (com.apple.dnsSettings.managed) định tuyến HTTPS qua máy chủ cấp quyền.
    """
    clean_name = (display_name or "VIP").replace(" ", "_")
    uuid_top = str(uuid.uuid4())
    uuid_ca = str(uuid.uuid4())
    uuid_dns = str(uuid.uuid4())

    locket_domains = [
        "api.revenuecat.com",
        "firebaseremoteconfig.googleapis.com",
        "api.locketcamera.com",
        "us-central1-locket-4252a.cloudfunctions.net",
    ]
    spotify_domains = [
        "spclient.wg.spotify.com",
        "spclient.spotify.com",
        "dealer.spotify.com",
        "apresolve.spotify.com",
        "spotify.com",
    ]

    s_lower = (service_name or "").lower()
    if "spotify" in s_lower and "locket" not in s_lower and "combo" not in s_lower and "duo" not in s_lower:
        match_domains = spotify_domains
    elif "locket" in s_lower and "spotify" not in s_lower and "combo" not in s_lower and "duo" not in s_lower:
        match_domains = locket_domains
    else:
        # Combo / Duo VIP: Kích hoạt đồng thời cả Locket & Spotify
        match_domains = locket_domains + spotify_domains

    domains_xml = "\n".join(f"                    <string>{d}</string>" for d in match_domains)

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>LocketGold Root CA</string>
            <key>PayloadContent</key>
            <data>{ROOT_CA_CERT_B64}</data>
            <key>PayloadDescription</key>
            <string>Adds a CA root certificate</string>
            <key>PayloadDisplayName</key>
            <string>LocketGold CA</string>
            <key>PayloadIdentifier</key>
            <string>com.apple.security.root.{uuid_ca}</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>{uuid_ca}</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
        <dict>
            <key>DNSSettings</key>
            <dict>
                <key>DNSProtocol</key>
                <string>HTTPS</string>
                <key>ServerURL</key>
                <string>https://doh.2707226.xyz/dns-query/common</string>
                <key>ServerAddresses</key>
                <array>
                    <string>103.211.207.247</string>
                </array>
                <key>SupplementalMatchDomains</key>
                <array>
{domains_xml}
                </array>
            </dict>
            <key>PayloadDescription</key>
            <string>DNS-over-HTTPS via LocketGold</string>
            <key>PayloadDisplayName</key>
            <string>{service_name} VIP DNS</string>
            <key>PayloadIdentifier</key>
            <string>com.apple.dnsSettings.managed.{uuid_dns}</string>
            <key>PayloadType</key>
            <string>com.apple.dnsSettings.managed</string>
            <key>PayloadUUID</key>
            <string>{uuid_dns}</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>PayloadDescription</key>
    <string>AloPremium.Shop - Cấu hình VIP kích hoạt {service_name} @{clean_name}</string>
    <key>PayloadDisplayName</key>
    <string>{service_name} ({clean_name})</string>
    <key>PayloadIdentifier</key>
    <string>com.alopremium.profile.{clean_name}</string>
    <key>PayloadOrganization</key>
    <string>AloPremium.shop Service</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>{uuid_top}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>"""
    buf = io.BytesIO(xml_content.encode("utf-8"))
    buf.name = f"{service_name.replace(' ', '_')}_{clean_name}.mobileconfig"
    buf.seek(0)
    return buf




