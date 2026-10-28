import os
import re
import json
import time
import requests
import urllib3
from config import SERVER_BASE_URL, STATUS_JSON_PATH, MATCH_DOMAINS, CA_DER_B64

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def clean_input(raw: str) -> str:
    """Tách username hoặc UID sạch từ chuỗi nhập vào (link locket.cam, @username hoặc text)"""
    s = raw.strip()
    # Loại bỏ tiền tố @
    s = s.lstrip("@")
    # Xử lý trường hợp người dùng dán link locket.cam/username hoặc locket.cam/u/username
    m = re.search(r"locket\.cam/(?:u/)?([^/?#&\s]+)", s, re.I)
    if m:
        s = m.group(1).lstrip("@")
    return s.strip()

def build_mobileconfig_xml(username: str, token: str, cf_url: str = SERVER_BASE_URL) -> str:
    """Tạo cấu hình XML profile Apple .mobileconfig chuẩn iOS (chứa CA và DNS DoH)"""
    display_tag = username or token or "VIP"
    doh_url = f"{cf_url.rstrip('/')}/dns-query/{token or 'vip'}"
    domain_tags = "\n".join([f"                    <string>{d}</string>" for d in MATCH_DOMAINS])
    
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadDisplayName</key>
    <string>Locket Gold VIP ({display_tag})</string>
    <key>PayloadDescription</key>
    <string>Cau hinh Locket Gold VIP + Spotify + YouTube Premium (Vinh vien 2099) - @{display_tag}</string>
    <key>PayloadIdentifier</key>
    <string>com.locketgold.profile</string>
    <key>PayloadOrganization</key>
    <string>Locket Gold VIP</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>9ddc879a-abb8-4bdb-9984-c53a273581e8</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.locketgold.rootca</string>
            <key>PayloadUUID</key>
            <string>bb0640e5-040b-4ecc-9f5c-53157883582a</string>
            <key>PayloadDisplayName</key>
            <string>Locket Gold Root CA</string>
            <key>PayloadDescription</key>
            <string>Chung chi goc Locket Gold Root CA</string>
            <key>PayloadContent</key>
            <data>{CA_DER_B64}</data>
        </dict>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.dnsSettings.managed</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.locketgold.dns</string>
            <key>PayloadUUID</key>
            <string>2504b094-3aad-4998-a308-a23e7db9ffa4</string>
            <key>PayloadDisplayName</key>
            <string>Locket Gold VIP DNS</string>
            <key>PayloadDescription</key>
            <string>DNS-over-HTTPS Locket Gold VIP</string>
            <key>DNSSettings</key>
            <dict>
                <key>DNSProtocol</key>
                <string>HTTPS</string>
                <key>ServerURL</key>
                <string>{doh_url}</string>
                <key>SupplementalMatchDomains</key>
                <array>
{domain_tags}
                </array>
            </dict>
        </dict>
    </array>
</dict>
</plist>"""

def resolve_locket_profile(raw_input: str) -> dict:
    """
    Giải mã tài khoản Locket và tạo cấu hình DNS:
    1. Thử gọi API server backend trực tiếp (lấy profile có ký số CMS xanh).
    2. Nếu lỗi hoặc server quá tải, kiểm tra cache status.json.
    3. Nếu không có trong cache, scrape profile qua r.jina.ai.
    4. Trả về thông tin user + bytes của file cấu hình .mobileconfig.
    """
    clean = clean_input(raw_input)
    if not clean:
        return {"ok": False, "error": "Vui lòng nhập Username hoặc Link Locket!"}

    # 1. Gọi trực tiếp API server backend
    try:
        r = requests.post(
            f"{SERVER_BASE_URL}/api/dns/generate",
            json={"url": clean},
            verify=False,
            timeout=6
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("uid"):
                token = data.get("token") or clean[:12].lower()
                uid = data.get("uid")
                username = data.get("username") or clean
                download_url = f"{SERVER_BASE_URL}/locket_gold.mobileconfig?token={token}&uid={uid}&username={username}"
                
                # Tải file đã ký số CMS xanh từ server
                profile_bytes = None
                try:
                    f_res = requests.get(download_url, verify=False, timeout=6)
                    if f_res.status_code == 200 and len(f_res.content) > 500:
                        profile_bytes = f_res.content
                except Exception:
                    pass
                
                # Nếu không tải được file ký, tự sinh XML fallback
                if not profile_bytes:
                    xml_str = build_mobileconfig_xml(username, token, SERVER_BASE_URL)
                    profile_bytes = xml_str.encode("utf-8")
                
                return {
                    "ok": True,
                    "uid": uid,
                    "username": username,
                    "full_name": data.get("full_name") or username,
                    "avatar": data.get("avatar") or f"https://cdn2.locketcamera.com/v0/b/locket-img/o/users%{uid}%2Fpublic%2Fprofile_pic.webp?alt=media",
                    "token": token,
                    "download_url": download_url,
                    "profile_bytes": profile_bytes,
                    "is_signed": len(profile_bytes) > 2000 and b"MII" in profile_bytes[:100],
                    "source": "server_api"
                }
    except Exception as e:
        print(f"[Warn] Server API error: {e}")

    # 2. Kiểm tra cache status.json
    try:
        if os.path.exists(STATUS_JSON_PATH):
            with open(STATUS_JSON_PATH, "r", encoding="utf-8") as f:
                st = json.load(f)
                users = st.get("users", [])
                for u in users:
                    if u.get("username", "").lower() == clean.lower() or u.get("uid") == clean:
                        uid = u.get("uid")
                        username = u.get("username")
                        token = u.get("token") or uid[:12].lower()
                        download_url = f"{SERVER_BASE_URL}/locket_gold.mobileconfig?token={token}&uid={uid}&username={username}"
                        xml_str = build_mobileconfig_xml(username, token, SERVER_BASE_URL)
                        return {
                            "ok": True,
                            "uid": uid,
                            "username": username,
                            "full_name": u.get("full_name") or username,
                            "avatar": u.get("avatar") or f"https://cdn2.locketcamera.com/v0/b/locket-img/o/users%{uid}%2Fpublic%2Fprofile_pic.webp?alt=media",
                            "token": token,
                            "download_url": download_url,
                            "profile_bytes": xml_str.encode("utf-8"),
                            "is_signed": False,
                            "source": "local_cache"
                        }
    except Exception as e:
        print(f"[Warn] Local cache error: {e}")

    # 3. Fallback: Quét qua jina.ai scraper
    try:
        jina_url = f"https://r.jina.ai/https://locket.cam/{clean}"
        r = requests.get(jina_url, timeout=8)
        if r.status_code == 200:
            text = r.text
            m_uid = re.search(r"users(?:%2F|/)([A-Za-z0-9]{28})(?:%2F|/)", text, re.I)
            if not m_uid:
                m_uid = re.search(r"(?:%2F|/)([A-Za-z0-9]{28})[0-9a-f]{16}", text, re.I)
            if m_uid:
                uid = m_uid.group(1)
                token = uid[:12].lower()
                m_img = re.search(r"(https://cdn2\.locketcamera\.com/v0/b/locket-img/o/users[^\s)\"\'<>\\]+)", text)
                avatar = m_img.group(1) if m_img else f"https://cdn2.locketcamera.com/v0/b/locket-img/o/users%{uid}%2Fpublic%2Fprofile_pic.webp?alt=media"
                download_url = f"{SERVER_BASE_URL}/locket_gold.mobileconfig?token={token}&uid={uid}&username={clean}"
                xml_str = build_mobileconfig_xml(clean, token, SERVER_BASE_URL)
                return {
                    "ok": True,
                    "uid": uid,
                    "username": clean,
                    "full_name": clean,
                    "avatar": avatar,
                    "token": token,
                    "download_url": download_url,
                    "profile_bytes": xml_str.encode("utf-8"),
                    "is_signed": False,
                    "source": "jina_scraper"
                }
    except Exception as e:
        print(f"[Warn] Jina error: {e}")

    # 4. Nếu người dùng nhập thẳng UID 28 ký tự
    if len(clean) == 28 and re.match(r"^[A-Za-z0-9]{28}$", clean):
        token = clean[:12].lower()
        short_name = clean[:8]
        download_url = f"{SERVER_BASE_URL}/locket_gold.mobileconfig?token={token}&uid={clean}&username={short_name}"
        xml_str = build_mobileconfig_xml(short_name, token, SERVER_BASE_URL)
        return {
            "ok": True,
            "uid": clean,
            "username": short_name,
            "full_name": short_name,
            "avatar": f"https://cdn2.locketcamera.com/v0/b/locket-img/o/users%{clean}%2Fpublic%2Fprofile_pic.webp?alt=media",
            "token": token,
            "download_url": download_url,
            "profile_bytes": xml_str.encode("utf-8"),
            "is_signed": False,
            "source": "raw_uid"
        }

    return {"ok": False, "error": f"Không tìm thấy thông tin tài khoản Locket cho '{raw_input}'. Hãy chắc chắn bạn đã nhập đúng username hoặc link mời kết bạn!"}

def check_server_health() -> dict:
    """Kiểm tra tình trạng máy chủ DNS Proxy"""
    start = time.time()
    try:
        r = requests.get(f"{SERVER_BASE_URL}/locket_gold.mobileconfig", verify=False, timeout=5)
        latency = int((time.time() - start) * 1000)
        online = (r.status_code == 200 or r.status_code == 400)
        return {
            "online": online,
            "status_code": r.status_code,
            "latency_ms": latency,
            "server_url": SERVER_BASE_URL
        }
    except Exception as e:
        return {
            "online": False,
            "status_code": None,
            "latency_ms": None,
            "error": str(e),
            "server_url": SERVER_BASE_URL
        }

def get_stats() -> dict:
    """Đếm số lượng người dùng đã lưu trong database"""
    count = 0
    if os.path.exists(STATUS_JSON_PATH):
        try:
            with open(STATUS_JSON_PATH, "r", encoding="utf-8") as f:
                st = json.load(f)
                count = len(st.get("users", []))
        except Exception:
            pass
    return {"user_count": count}

