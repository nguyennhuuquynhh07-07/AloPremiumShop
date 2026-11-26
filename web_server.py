"""
web_server.py – Máy chủ Web & API Cổng Thanh Toán VIP Duo (Locket & Spotify)
Phục vụ:
1. Giao diện Web App bán hàng Responsive siêu đẹp cho Safari iPhone & Desktop.
2. Tải trực tiếp file .mobileconfig vào Cài đặt iOS (Content-Type: application/x-apple-aspen-config).
3. API Kiểm tra tài khoản Locket & Spotify trực tiếp trước khi mua.
4. API Tạo đơn hàng & sinh mã QR VietQR tự động (TPBank).
5. API Tra cứu trạng thái đơn & tự động kích hoạt khi nhận tiền (Polling SePay & Webhook).
6. API Reset thiết bị Spotify & Tra cứu lịch sử đơn hàng.
"""

import os
import sys
import json
import base64
import uuid
import hashlib
import ipaddress
import socket
import logging
import threading
import asyncio
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
import urllib.parse
import urllib.request

import config
import database as db
import api_client as api
import utils

logger = logging.getLogger("web_server")

BOT_INSTANCE = None
BOT_LOOP = None

def set_bot_context(bot, loop):
    global BOT_INSTANCE, BOT_LOOP
    BOT_INSTANCE = bot
    BOT_LOOP = loop

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

import time
import hmac
import re
from collections import defaultdict

_RATE_LIMIT_LOCK = threading.Lock()
_IP_REQUESTS = defaultdict(list)
_IP_BANNED = {}
_ADMIN_PIN_FAILS = defaultdict(list)
_ADMIN_PIN_BANNED = {}
_UPLOAD_REQUESTS = defaultdict(list)

_MEDIA_SECRET_SEED = (
    str(getattr(config, "SECRET_KEY", "") or "")
    + "|"
    + str(getattr(config, "API_KEY", "") or "")
    + "|"
    + str(getattr(config, "ADMIN_PIN", "") or "")
)
_MEDIA_SECRET = (
    hashlib.sha256(_MEDIA_SECRET_SEED.encode("utf-8")).digest()
    if _MEDIA_SECRET_SEED.strip("|")
    else os.urandom(32)
)
_MEDIA_CACHE_LOCK = threading.Lock()
_MEDIA_CACHE: dict[str, tuple[float, str, bytes]] = {}


def _encode_media_token(raw_url: str) -> str:
    raw = str(raw_url or "").strip().encode("utf-8")
    if not raw:
        return ""
    nonce = os.urandom(8)
    ks = hashlib.sha256(_MEDIA_SECRET + nonce).digest()
    enc = bytes(b ^ ks[i % len(ks)] for i, b in enumerate(raw))
    tag = hmac.new(_MEDIA_SECRET, nonce + enc, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(nonce + tag + enc).decode("ascii").rstrip("=")


def _decode_media_token(token: str) -> str:
    t = str(token or "").strip()
    if not t or len(t) > 2048:
        return ""
    try:
        pad = "=" * ((4 - len(t) % 4) % 4)
        blob = base64.urlsafe_b64decode((t + pad).encode("ascii"))
        if len(blob) <= 24:
            return ""
        nonce, tag, enc = blob[:8], blob[8:24], blob[24:]
        expected = hmac.new(_MEDIA_SECRET, nonce + enc, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expected):
            return ""
        ks = hashlib.sha256(_MEDIA_SECRET + nonce).digest()
        dec = bytes(b ^ ks[i % len(ks)] for i, b in enumerate(enc))
        return dec.decode("utf-8")
    except Exception:
        return ""


def _proxy_media_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return raw_url
    s = str(raw_url).strip()
    if not s:
        return s
    if s.startswith("/api/media?m=") or not (s.startswith("http://") or s.startswith("https://")):
        return s
    try:
        p = urlparse(s)
        base_host = urlparse(getattr(config, "WEBSITE_URL", "https://alopremium.shop")).netloc.lower()
        if p.hostname and p.hostname.lower() == base_host.split(":")[0]:
            return (p.path or "/") + (f"?{p.query}" if p.query else "")
    except Exception:
        pass
    tok = _encode_media_token(s)
    return f"/api/media?m={tok}" if tok else s


def _unwrap_media_url(raw_url: str) -> str:
    s = str(raw_url or "").strip()
    if "/api/media?" in s:
        try:
            q = parse_qs(urlparse(s).query)
            tok = q.get("m", [""])[0].strip()
            decoded = _decode_media_token(tok)
            if decoded:
                return decoded
        except Exception:
            pass
    return s


def _resolve_frame_url(raw_url: str) -> str:
    """Giải mã token media proxy và quy đổi đường dẫn nội bộ /assets/... thành https:// đầy đủ."""
    resolved = _unwrap_media_url(raw_url)
    if resolved.startswith("/") and not resolved.startswith("//"):
        base_web = getattr(config, "WEBSITE_URL", "https://alopremium.shop").rstrip("/")
        if base_web.startswith("http://"):
            base_web = "https://" + base_web[len("http://"):]
        return f"{base_web}{resolved}"
    return resolved


def _get_masked_vietqr_url(amount: int, add_info: str) -> str:
    raw = utils.get_vietqr_url(amount=amount, add_info=add_info)
    return _proxy_media_url(raw) or raw


def _is_safe_public_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        host = p.hostname.lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not infos:
            return False
        for info in infos:
            ip_str = info[4][0].split("%")[0]
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
                return False
        return True
    except Exception:
        return False


def _protect_html_response(html_text: str) -> bytes:
    """Ẩn comment HTML và mã hóa runtime các thẻ <script data-protected="1"> trước khi trả về trình duyệt."""
    script_re = re.compile(r'(<script\b[^>]*>[\s\S]*?</script>|<style\b[^>]*>[\s\S]*?</style>)', re.I)
    protected_re = re.compile(r'^<script\b([^>]*\bdata-protected=["\']?1["\']?[^>]*)>([\s\S]*?)</script>$', re.I)
    parts = script_re.split(html_text)
    out = []
    for idx, part in enumerate(parts):
        if idx % 2 == 0:
            out.append(re.sub(r'<!--(?!\[if)[\s\S]*?-->', '', part))
        else:
            m = protected_re.match(part)
            if not m:
                out.append(part)
                continue
            js_bytes = m.group(2).encode("utf-8")
            key = os.urandom(16)
            xored = bytes(b ^ key[i % 16] for i, b in enumerate(js_bytes))
            b64_payload = base64.b64encode(xored).decode("ascii")
            key_arr = ",".join(str(b) for b in key)
            loader = (
                "<script>"
                "(function(){"
                "if(window.__AP_DEVTOOLS_LOCKED__){if(window.__apTriggerSecurityError)window.__apTriggerSecurityError('LOCKED');return;}"
                f"var _k=[{key_arr}],_r=atob('{b64_payload}'),_n=_r.length,_u=new Uint8Array(_n),_i=0;"
                "for(;_i<_n;_i++){_u[_i]=_r.charCodeAt(_i)^_k[_i%_k.length];}"
                "var _c=new TextDecoder('utf-8').decode(_u);"
                "(0,eval)(_c);"
                "})();"
                "</script>"
            )
            out.append(loader)
    return "".join(out).encode("utf-8")


def _get_admin_pin() -> str:
    return str(getattr(config, "ADMIN_PIN", "") or "").strip()


def check_ip_rate_limit(ip: str, max_requests: int = 60, window_secs: int = 60) -> tuple[bool, str]:
    now = time.time()
    with _RATE_LIMIT_LOCK:
        if ip in _IP_BANNED:
            remaining = int(_IP_BANNED[ip] - now)
            if remaining > 0:
                return False, f"IP bị tạm khóa do gửi yêu cầu quá nhanh. Vui lòng thử lại sau {remaining} giây."
            del _IP_BANNED[ip]

        timestamps = [t for t in _IP_REQUESTS[ip] if now - t < window_secs]
        timestamps.append(now)
        _IP_REQUESTS[ip] = timestamps
        if len(_IP_REQUESTS) > 2000:
            stale = [k for k, v in _IP_REQUESTS.items() if not v or (now - v[-1] > 300)]
            for k in stale:
                del _IP_REQUESTS[k]
        if len(timestamps) > max_requests:
            _IP_BANNED[ip] = now + 900
            return False, "Tần suất yêu cầu bất thường. IP của bạn đã bị tạm khóa 15 phút để đảm bảo an toàn."

        return True, ""


def check_admin_pin_bruteforce(ip: str) -> tuple[bool, str]:
    now = time.time()
    with _RATE_LIMIT_LOCK:
        ban_until = _ADMIN_PIN_BANNED.get(ip, 0)
        if ban_until > now:
            rem = int(ban_until - now)
            return False, f"Bạn đã nhập sai mã PIN quá nhiều lần. Vui lòng thử lại sau {rem} giây."
        if ip in _ADMIN_PIN_BANNED:
            del _ADMIN_PIN_BANNED[ip]
        return True, ""


def record_admin_pin_result(ip: str, success: bool) -> None:
    now = time.time()
    with _RATE_LIMIT_LOCK:
        if success:
            _ADMIN_PIN_FAILS.pop(ip, None)
            _ADMIN_PIN_BANNED.pop(ip, None)
            return
        fails = [t for t in _ADMIN_PIN_FAILS[ip] if now - t < 900]
        fails.append(now)
        _ADMIN_PIN_FAILS[ip] = fails
        if len(fails) >= 5:
            _ADMIN_PIN_BANNED[ip] = now + 900
            _ADMIN_PIN_FAILS.pop(ip, None)


def check_upload_rate_limit(ip: str, max_uploads: int = 12, window_secs: int = 600) -> tuple[bool, str]:
    now = time.time()
    with _RATE_LIMIT_LOCK:
        times = [t for t in _UPLOAD_REQUESTS[ip] if now - t < window_secs]
        if len(times) >= max_uploads:
            return False, "Bạn đã tải lên quá nhiều ảnh trong thời gian ngắn. Vui lòng thử lại sau ít phút."
        times.append(now)
        _UPLOAD_REQUESTS[ip] = times
        return True, ""


_RECENT_DISPATCHED_ALERTS = {}  # order_id -> (timestamp, price)

def dispatch_admin_order_alert(order_id: str, pv: dict, plnv: dict, display_name: str, identifier: str, price: int, orig_price: int, applied_code: str = "", discount_amount: int = 0):
    """Gửi thông báo đơn hàng mới từ Web sang Bot Telegram siêu tốc (< 0.2s, đa kênh dự phòng, chống spam tin nhắn trùng mã đơn)"""
    import time
    now = time.time()
    # Chống spam thông báo trùng: Nếu mã đơn này đã gửi trong vòng 5 phút (300s) với cùng giá tiền -> bỏ qua
    last_alert = _RECENT_DISPATCHED_ALERTS.get(order_id)
    if last_alert:
        last_time, last_price = last_alert
        if (now - last_time < 300) and (last_price == price):
            logger.info(f"Skipping duplicate admin order alert for order {order_id} (already alerted {int(now - last_time)}s ago)")
            return

    _RECENT_DISPATCHED_ALERTS[order_id] = (now, price)

    def _worker():
        if applied_code and discount_amount > 0:
            price_line = (
                f"• Giá niêm yết: <s>{utils.fmt_price(orig_price)}</s>\n"
                f"• Mã giảm giá: <code>{applied_code}</code> (-{utils.fmt_price(discount_amount)})\n"
                f"• Cần thanh toán: <b>{utils.fmt_price(price)}</b>"
            )
        else:
            price_line = f"• Số tiền: <b>{utils.fmt_price(price)}</b>"

        msg_admin = (
            f"🛒 <b>[ĐƠN HÀNG WEB MỚI]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Mã đơn: <code>ORDER_{order_id}</code>\n"
            f"• Dịch vụ: <b>{pv.get('name', 'Gói VIP')} - {plnv.get('label', '')}</b>\n"
            f"• Khách: {display_name} (<code>@{identifier}</code>)\n"
            f"{price_line}\n"
            f"• Đang chờ chuyển khoản VietQR..."
        )
        from keyboards import admin_approval_kb
        kb = admin_approval_kb(order_id)
        sent_refs = []

        # 1. Thử gửi qua Telegram Bot loop nếu có
        sent_any = False
        if BOT_INSTANCE and BOT_LOOP and BOT_LOOP.is_running():
            for aid in config.ADMIN_IDS:
                try:
                    fut = asyncio.run_coroutine_threadsafe(
                        BOT_INSTANCE.send_message(
                            chat_id=aid,
                            text=msg_admin,
                            parse_mode="HTML",
                            reply_markup=kb
                        ),
                        BOT_LOOP
                    )
                    sent_msg = fut.result(timeout=4.0)
                    if sent_msg and getattr(sent_msg, "message_id", None):
                        sent_refs.append({"chat_id": aid, "message_id": sent_msg.message_id})
                    sent_any = True
                except Exception as e_bot:
                    logger.warning(f"Bot loop send failed: {e_bot}")

        # 2. Dự phòng: Gửi thẳng qua Telegram HTTP API không bao giờ nghẽn
        if not sent_any:
            try:
                import httpx
                bot_token = getattr(config, "BOT_TOKEN", "")
                if bot_token:
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    kb_dict = kb.to_dict() if hasattr(kb, "to_dict") else {}
                    with httpx.Client(timeout=4.0) as client:
                        for aid in config.ADMIN_IDS:
                            r = client.post(url, json={
                                "chat_id": aid,
                                "text": msg_admin,
                                "parse_mode": "HTML",
                                "reply_markup": kb_dict
                            })
                            try:
                                mid = r.json().get("result", {}).get("message_id")
                                if mid:
                                    sent_refs.append({"chat_id": aid, "message_id": mid})
                            except Exception:
                                pass
            except Exception as e_http:
                logger.warning(f"Telegram HTTP direct notification failed: {e_http}")

        if sent_refs:
            try:
                db.update_order(order_id, admin_alert_messages=sent_refs)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()


class WebAppHandler(BaseHTTPRequestHandler):
    server_version = "ProtectedServer/2.0"
    sys_version = ""

    def _get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        cf_ip = self.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-Admin-Pin, X-Admin-PIN, X-Locket-User")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()")

    def _extract_admin_pin(self, params: dict | None = None, body: dict | None = None, explicit_pin: str = "") -> str:
        hdr_pin = (self.headers.get("X-Admin-PIN") or self.headers.get("X-Admin-Pin") or "").strip()
        if hdr_pin:
            return hdr_pin
        if explicit_pin:
            return explicit_pin.strip()
        if isinstance(body, dict) and body.get("pin") is not None:
            return str(body.get("pin") or "").strip()
        if isinstance(params, dict):
            return str(params.get("pin", [""])[0] or "").strip()
        return ""

    def _is_valid_admin_pin(self, pin: str) -> bool:
        expected = _get_admin_pin()
        if not expected or not pin:
            return False
        return hmac.compare_digest(pin.encode("utf-8"), expected.encode("utf-8"))

    def _require_admin(self, params: dict | None = None, body: dict | None = None, explicit_pin: str = "") -> bool:
        client_ip = self._get_client_ip()
        allowed, reason = check_admin_pin_bruteforce(client_ip)
        if not allowed:
            self._send_json(429, {"ok": False, "error": reason})
            return False
        pin = self._extract_admin_pin(params=params, body=body, explicit_pin=explicit_pin)
        if not self._is_valid_admin_pin(pin):
            record_admin_pin_result(client_ip, False)
            self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
            return False
        record_admin_pin_result(client_ip, True)
        return True

    def _require_vip_or_admin(self, params: dict | None = None) -> bool:
        hdr_pin = (self.headers.get("X-Admin-PIN") or self.headers.get("X-Admin-Pin") or "").strip()
        param_pin = str((params or {}).get("pin", [""])[0] or "").strip()
        if hdr_pin or param_pin:
            return self._require_admin(params=params)
        ident = ""
        if isinstance(params, dict):
            ident = str(
                params.get("identifier", [""])[0]
                or params.get("username", [""])[0]
                or params.get("uid", [""])[0]
                or ""
            ).strip()
        if not ident:
            ident = (self.headers.get("X-Locket-User") or "").strip()
        if not ident:
            self._send_json(403, {"ok": False, "error": "Vui lòng kết nối tài khoản Locket Gold VIP để sử dụng tính năng này."})
            return False
        is_vip, info = self._verify_customer_locket_vip(ident)
        if not is_vip:
            self._send_json(403, {"ok": False, "error": info.get("error") or "Tài khoản chưa kích hoạt Locket Gold VIP tại cửa hàng."})
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            if content_length > 28 * 1024 * 1024:
                return {}
            raw_data = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_data)
        except Exception as e:
            logger.warning(f"Failed to parse JSON body: {e}")
            return {}

    def _read_multipart_form(self) -> tuple[dict, bytes, str]:
        """Đọc multipart/form-data an toàn (tối đa 22MB cho file 3D LUT .cube 20MB)."""
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype.lower():
            return {}, b"", ""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length <= 0 or content_length > 22 * 1024 * 1024:
            raise ValueError("Kích thước dữ liệu tải lên không hợp lệ (tối đa 20MB).")
        raw_body = self.rfile.read(content_length)

        from email.parser import BytesParser
        from email.policy import default as email_policy
        header_bytes = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin-1")
        msg = BytesParser(policy=email_policy).parsebytes(header_bytes + raw_body)

        fields = {}
        file_bytes = b""
        filename = ""
        if msg.is_multipart():
            for part in msg.iter_parts():
                name = part.get_param("name", header="Content-Disposition")
                fname = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if fname:
                    if len(payload) <= 20 * 1024 * 1024:
                        file_bytes = payload
                        filename = os.path.basename(fname)
                    else:
                        raise ValueError("Dung lượng file vượt quá giới hạn 20MB.")
                elif name:
                    fields[name] = payload.decode("utf-8", errors="replace").strip()
        return fields, file_bytes, filename

    def _verify_customer_locket_vip(self, raw_identifier: str) -> tuple[bool, dict]:
        """Kiểm tra tài khoản Locket có đang active VIP trên locket.2707226.xyz hoặc có đơn hoàn tất tại shop."""
        cleaned = utils.clean_input(raw_identifier)
        if not cleaned or len(cleaned) < 2 or " " in cleaned:
            return False, {"error": "Username hoặc UID Locket không hợp lệ!"}

        uid = ""
        username = cleaned
        avatar = ""
        package_name = ""
        expires_at = None
        is_active = False

        try:
            res = api.check_uid_details(cleaned, "locket")
            dt = res.get("data", {}) if isinstance(res, dict) and isinstance(res.get("data"), dict) else (res if isinstance(res, dict) else {})
            if dt:
                uid = str(dt.get("uid") or dt.get("id") or "").strip()
                username = str(dt.get("username") or cleaned).strip()
                avatar = dt.get("avatarUrl") or dt.get("avatar") or ""
                pkg = dt.get("package") or {}
                if isinstance(pkg, dict):
                    package_name = pkg.get("name") or pkg.get("code") or ""
                expires_at = dt.get("expiresAt")
                if (dt.get("active") is True or dt.get("status") == "ACTIVE") and (dt.get("isMine") is True):
                    is_active = True
        except Exception:
            pass

        if not uid:
            try:
                r_res = api.locket_resolve(cleaned)
                r_dt = r_res.get("data", {}) if isinstance(r_res, dict) and isinstance(r_res.get("data"), dict) else (r_res if isinstance(r_res, dict) else {})
                uid = str(r_dt.get("uid") or r_dt.get("id") or "").strip()
                username = str(r_dt.get("username") or username).strip()
                avatar = avatar or r_dt.get("avatar") or r_dt.get("avatarUrl") or ""
            except Exception:
                pass

        has_paid_order = False
        cleaned_l = cleaned.lower().lstrip("@")
        uid_l = uid.lower()
        uname_l = username.lower().lstrip("@")
        for od in db.get_orders().values():
            if od.get("status") == "done" and od.get("product") in ("locket", "combo", "locket_spotify", "locket_ai"):
                cand = [
                    str(od.get("identifier", "")).lower().lstrip("@"),
                    str(od.get("uid", "")).lower(),
                    str(od.get("display_name", "")).lower().lstrip("@"),
                    str(od.get("account_target", "")).lower().lstrip("@"),
                    str(od.get("locket_username", "")).lower().lstrip("@"),
                ]
                if cleaned_l in cand or (uid_l and uid_l in cand) or (uname_l and uname_l in cand):
                    has_paid_order = True
                    if not package_name:
                        package_name = od.get("plan_label") or od.get("plan") or "Locket Gold VIP"
                    break

        is_vip = bool(is_active or has_paid_order)
        if not uid and not is_vip:
            return False, {"error": f"Không tìm thấy tài khoản Locket '@{cleaned}' trên hệ thống!"}

        return is_vip, {
            "uid": uid or cleaned,
            "username": username,
            "avatar": avatar or "logo.png",
            "is_vip": is_vip,
            "active_on_server": is_active,
            "has_shop_order": has_paid_order,
            "package_name": (package_name or "Locket Gold VIP") if is_vip else "Chưa mua gói VIP tại cửa hàng",
            "expires_at": expires_at,
        }

    def _upsert_ctv_lookup_order(
        self,
        ret_oid: str,
        product: str,
        plan_name: str,
        ret_user: str,
        ret_uid: str,
        created_at: str | None,
        expires_at: str | None,
        avatar: str | None,
    ) -> dict:
        """Đồng bộ đơn CTV vào DB nội bộ khi tra cứu và trả về bản ghi hiển thị."""
        created_str = created_at or datetime.now().isoformat()
        dns_str = f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
        fields_ctv = {
            "user_id": 0,
            "username": ret_user,
            "display_name": ret_user,
            "account_target": ret_user,
            "uid": ret_uid,
            "product": product,
            "plan": plan_name,
            "plan_label": plan_name,
            "status": "done",
            "created_at": created_str,
            "done_at": created_str,
            "expires_at": expires_at,
            "avatar": avatar,
            "dns_link": dns_str,
            "source": "web_chu",
        }
        if not db.update_order(ret_oid, **fields_ctv):
            db.create_order(order_id=ret_oid, price=0, **fields_ctv)
        masked_avatar = _proxy_media_url(avatar)
        return {
            "order_id": ret_oid,
            "product": product,
            "plan": plan_name,
            "price": 0,
            "status": "done",
            "uid": ret_uid,
            "display_name": ret_user,
            "avatar": masked_avatar,
            "expires_at": expires_at,
            "created_at": created_str,
            "download_url": f"/api/download_profile?order_id={ret_oid}",
            "direct_safari_url": f"/api/download_profile?order_id={ret_oid}",
        }

    def do_HEAD(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        raw_path = urllib.parse.unquote(path)
        params = parse_qs(parsed.query)
        client_ip = self._get_client_ip()

        # 0. Chặn Path Traversal và các ký tự nguy hiểm
        if ".." in raw_path or "%2e" in self.path.lower() or "\\." in raw_path:
            self._send_json(403, {"ok": False, "error": "Access denied"})
            return

        # 0.1 Chặn tuyệt đối truy cập các file nhạy cảm (.py, .json, .env, .bat, .sh, .git, v.v.)
        lower_raw = raw_path.lower()
        forbidden_exts = (".py", ".json", ".env", ".bat", ".sh", ".git", ".yaml", ".yml", ".md", ".lock")
        if any(lower_raw.endswith(ext) or (ext + "/") in lower_raw for ext in forbidden_exts):
            self._send_json(403, {"ok": False, "error": "Access denied"})
            return

        # Kiểm tra Rate Limit (tách giới hạn rộng cho proxy ảnh/asset và ping)
        static_exts_check = (
            ".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp", ".mp4",
            ".js", ".css", ".woff", ".woff2", ".ttf", ".webmanifest", ".mobileconfig"
        )
        if path in ("/api/media", "/api/donate_qr", "/api/default_symbol"):
            allowed, reason = check_ip_rate_limit(f"media:{client_ip}", max_requests=600, window_secs=60)
            if not allowed:
                self._send_json(429, {"ok": False, "error": reason})
                return
        elif not path.startswith(("/health", "/ping")) and not lower_raw.endswith(static_exts_check):
            allowed, reason = check_ip_rate_limit(client_ip, max_requests=60, window_secs=60)
            if not allowed:
                self._send_json(429, {"ok": False, "error": reason})
                return

        # 0.2 Proxy ảnh/SVG/QR same-origin để ẩn 100% domain nguồn khỏi DevTools Sources
        if path == "/api/media":
            token = params.get("m", [""])[0].strip()
            target_url = _decode_media_token(token)
            if not target_url:
                self._send_json(403, {"ok": False, "error": "Invalid or expired media token"})
                return
            now = time.time()
            with _MEDIA_CACHE_LOCK:
                cached = _MEDIA_CACHE.get(target_url)
                if cached and (now - cached[0]) < 1800:
                    c_type, c_bytes = cached[1], cached[2]
                    self.send_response(200)
                    self.send_header("Content-Type", c_type)
                    self.send_header("Content-Length", str(len(c_bytes)))
                    self.send_header("Cache-Control", "public, max-age=1800")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    if "svg" in c_type.lower():
                        self.send_header("Content-Security-Policy", "sandbox")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(c_bytes)
                    return

            if not _is_safe_public_url(target_url):
                self._send_json(403, {"ok": False, "error": "Disallowed media target"})
                return
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    c_type = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip().lower()
                    data = resp.read(4 * 1024 * 1024 + 1)
                if len(data) > 4 * 1024 * 1024:
                    self._send_json(413, {"ok": False, "error": "Media too large"})
                    return
                if not c_type.startswith("image/") and c_type not in ("application/octet-stream",):
                    self._send_json(403, {"ok": False, "error": "Unsupported media type"})
                    return
                if c_type == "application/octet-stream":
                    c_type = "image/svg+xml" if target_url.lower().endswith(".svg") else "image/png"
                if "svg" in c_type:
                    c_type = "image/svg+xml; charset=utf-8"
                with _MEDIA_CACHE_LOCK:
                    if len(_MEDIA_CACHE) >= 300:
                        _MEDIA_CACHE.pop(next(iter(_MEDIA_CACHE)))
                    _MEDIA_CACHE[target_url] = (now, c_type, data)
                self.send_response(200)
                self.send_header("Content-Type", c_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=1800")
                self.send_header("X-Content-Type-Options", "nosniff")
                if "svg" in c_type.lower():
                    self.send_header("Content-Security-Policy", "sandbox")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
            except Exception as e_media:
                self._send_json(502, {"ok": False, "error": f"Media unavailable: {e_media}"})
            return

        if path == "/api/donate_qr":
            bank_id = getattr(config, "BANK_ID", "TPB")
            acc_no = getattr(config, "ACCOUNT_NO", "34528022007")
            cache_k = f"donate_qr:{bank_id}:{acc_no}"
            now = time.time()
            with _MEDIA_CACHE_LOCK:
                cached = _MEDIA_CACHE.get(cache_k)
                if cached and (now - cached[0]) < 3600:
                    c_type, c_bytes = cached[1], cached[2]
                    self.send_response(200)
                    self.send_header("Content-Type", c_type)
                    self.send_header("Content-Length", str(len(c_bytes)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(c_bytes)
                    return
            urls = [
                f"https://qr.sepay.vn/img?bank={urllib.parse.quote(bank_id)}&acc={urllib.parse.quote(acc_no)}&template=compact&des=UNG%20HO%20SHOP",
                f"https://img.vietqr.io/image/{urllib.parse.quote(bank_id)}-{urllib.parse.quote(acc_no)}-compact2.png?addInfo=UNG%20HO%20SHOP",
            ]
            for u in urls:
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        if resp.status == 200:
                            c_type = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip().lower()
                            data = resp.read(2 * 1024 * 1024)
                            if c_type.startswith("image/") and data:
                                with _MEDIA_CACHE_LOCK:
                                    _MEDIA_CACHE[cache_k] = (now, c_type, data)
                                self.send_response(200)
                                self.send_header("Content-Type", c_type)
                                self.send_header("Content-Length", str(len(data)))
                                self.send_header("Cache-Control", "public, max-age=3600")
                                self.send_header("X-Content-Type-Options", "nosniff")
                                self._send_cors_headers()
                                self.end_headers()
                                self.wfile.write(data)
                                return
                except Exception:
                    continue
            self._send_json(502, {"ok": False, "error": "Donate QR temporarily unavailable"})
            return

        if path == "/api/default_symbol":
            sym_name = params.get("name", ["wind"])[0].strip() or "wind"
            if not re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", sym_name):
                self._send_json(400, {"ok": False, "error": "Invalid symbol name"})
                return
            upstream_base = getattr(config, "API_BASE_URL", "https://locket.2707226.xyz").rstrip("/")
            target_url = f"{upstream_base}/assets/sf-symbols/{sym_name}.svg"
            now = time.time()
            with _MEDIA_CACHE_LOCK:
                cached = _MEDIA_CACHE.get(target_url)
                if cached and (now - cached[0]) < 86400:
                    c_type, c_bytes = cached[1], cached[2]
                    self.send_response(200)
                    self.send_header("Content-Type", c_type)
                    self.send_header("Content-Length", str(len(c_bytes)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Security-Policy", "sandbox")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(c_bytes)
                    return
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = resp.read(512 * 1024)
                c_type = "image/svg+xml; charset=utf-8"
                with _MEDIA_CACHE_LOCK:
                    _MEDIA_CACHE[target_url] = (now, c_type, data)
                self.send_response(200)
                self.send_header("Content-Type", c_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Security-Policy", "sandbox")
                self.send_header("X-Content-Type-Options", "nosniff")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self._send_json(404, {"ok": False, "error": "Symbol unavailable"})
            return

        # 1. Health check & Render keep-alive
        if path in ("/health", "/ping"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b"Bot Locket Gold + Spotify is running 24/7!")
            return

        # 1.1 Gói Free đã tạm đóng -> trả 410 Gone thay vì cho tải lén .mobileconfig Free
        if raw_path in ("/Free.mobileconfig", "/LocketNgon.mobileconfig"):
            self._send_json(410, {
                "ok": False,
                "error": "Gói Locket Gold Free đã tạm ngưng phát hành. Vui lòng chọn gói VIP từ 5.000đ!"
            })
            return

        # 1.2 Phục vụ trang Hướng dẫn cài đặt DNS (Clean URL)
        if raw_path in ("/huong-dan", "/huong-dan.html", "/cai-dns", "/cai-dns.html"):
            guide_path = os.path.join(os.path.dirname(__file__), "huong-dan.html")
            if not os.path.exists(guide_path):
                guide_path = os.path.join(os.path.dirname(__file__), "cai-dns.html")
            if os.path.exists(guide_path) and os.path.isfile(guide_path):
                with open(guide_path, "rb") as f:
                    guide_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(guide_bytes)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(guide_bytes)
                return
            else:
                self._send_json(404, {"ok": False, "error": "huong-dan.html not found"})
                return

        # 1.3 Phục vụ Static Files trong danh sách thư mục cho phép (Bảo mật Whitelist & Path Traversal)
        ALLOWED_STATIC_DIRS = ("_next", "fonts", "assets", "huong dan image", "seo")
        ALLOWED_ROOT_FILES = (
            "favicon.ico", "favicon.png", "site.webmanifest", "robots.txt", "vip-custom.css",
            "logo.png", "spotify-icon.png", "locket-icon.png", "zalo_group_qr.png", "huong_dan_cai_dat.mp4"
        )
        STATIC_EXTENSIONS = (
            ".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp", ".mp4",
            ".js", ".css", ".woff", ".woff2", ".ttf", ".webmanifest"
        )

        clean_rel = raw_path.lstrip("/").replace("\\", "/")
        is_static_ext = any(lower_raw.endswith(ext) for ext in STATIC_EXTENSIONS)

        if is_static_ext:
            base_dir = os.path.abspath(os.path.dirname(__file__))
            file_path = os.path.abspath(os.path.join(base_dir, clean_rel))

            # Chặn Path Traversal
            try:
                if os.path.commonpath([base_dir, file_path]) != base_dir:
                    self._send_json(403, {"ok": False, "error": "Access denied"})
                    return
            except Exception:
                self._send_json(403, {"ok": False, "error": "Access denied"})
                return

            # Kiểm tra Whitelist thư mục cho phép hoặc file gốc cho phép
            rel_parts = clean_rel.split("/", 1)
            is_permitted = False
            if len(rel_parts) > 1 and rel_parts[0] in ALLOWED_STATIC_DIRS:
                is_permitted = True
            elif len(rel_parts) == 1 and rel_parts[0] in ALLOWED_ROOT_FILES:
                is_permitted = True

            if not is_permitted:
                self._send_json(403, {"ok": False, "error": "Access to this path is not permitted"})
                return

            if os.path.exists(file_path) and os.path.isfile(file_path):
                file_name = os.path.basename(file_path)
                ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

                mime_map = {
                    "mp4": "video/mp4",
                    "ico": "image/x-icon",
                    "svg": "image/svg+xml",
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "webp": "image/webp",
                    "js": "application/javascript; charset=utf-8",
                    "css": "text/css; charset=utf-8",
                    "woff": "font/woff",
                    "woff2": "font/woff2",
                    "ttf": "font/ttf",
                    "webmanifest": "application/manifest+json; charset=utf-8"
                }
                mime = mime_map.get(ext, "application/octet-stream")

                file_size = os.path.getsize(file_path)
                range_header = self.headers.get("Range")
                if range_header and ext == "mp4":
                    try:
                        range_val = range_header.replace("bytes=", "").strip()
                        parts = range_val.split("-")
                        start = int(parts[0]) if parts[0] else 0
                        end = int(parts[1]) if parts[1] else file_size - 1
                        length = end - start + 1
                        self.send_response(206)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                        self.send_header("Content-Length", str(length))
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Cache-Control", "public, max-age=86400")
                        self._send_cors_headers()
                        self.end_headers()
                        with open(file_path, "rb") as f:
                            f.seek(start)
                            self.wfile.write(f.read(length))
                        return
                    except Exception:
                        pass

                with open(file_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "public, max-age=86400")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self._send_json(404, {"ok": False, "error": f"File not found: {clean_rel}"})
                return

        # 2. API Cấu hình ngân hàng & thông tin hệ thống
        if path == "/api/config":
            self._send_json(200, {
                "ok": True,
                "bank_id": getattr(config, "BANK_ID", "TPB"),
                "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                "support_username": getattr(config, "SUPPORT_USERNAME", "nguyennhuquynh28"),
                "support_phone": getattr(config, "SUPPORT_PHONE", "0345222802"),
                "support_telegram": getattr(config, "SUPPORT_TELEGRAM", "https://t.me/nguyennhuquynh28"),
                "server_url": getattr(config, "SERVER_BASE_URL", ""),
            })
            return

        # 3. API Danh sách gói cước & bảng giá (kèm cấu hình Banner ưu đãi)
        if path == "/api/packages":
            try:
                from order_service import trigger_upstream_package_sync_bg
                trigger_upstream_package_sync_bg()
            except Exception:
                pass
            try:
                db.apply_custom_prices()
            except Exception:
                pass
            self._send_json(200, {
                "ok": True,
                "products": config.PRODUCTS,
                "banner": db.get_banner_config(),
                "zalo_group_url": getattr(config, "ZALO_GROUP_URL", "").strip(),
                "zalo_group_qr": "/zalo_group_qr.png",
                "support_phone": getattr(config, "SUPPORT_PHONE", "0345222802"),
                "support_telegram": getattr(config, "SUPPORT_TELEGRAM", "https://t.me/nguyennhuquynh28"),
                "bank_id": getattr(config, "BANK_ID", "TPB"),
                "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
            })
            return

        # 3.0 API Đồng bộ đơn hàng từ máy chủ CTV (Chỉ Admin)
        if path == "/api/sync_upstream":
            if not self._require_admin(params=params):
                return
            from order_service import sync_upstream_orders
            cnt = sync_upstream_orders()
            self._send_json(200, {
                "ok": True,
                "message": f"Đã đồng bộ {cnt} tài khoản từ máy chủ CTV thành công!",
                "synced_count": cnt
            })
            return

        # 3.01 API Danh sách Khung Widget Locket (Chỉ dành cho khách VIP hoặc Admin)
        if path == "/api/frames":
            if not self._require_vip_or_admin(params=params):
                return
            all_frames = []
            seen_urls = set()

            # 1. Lấy khung Live CTV dành cho ALL (ẩn hoàn toàn UID cá nhân của khách khác)
            ctv_connected = False
            try:
                ctv_res = api.ctv_get_frames()
                if isinstance(ctv_res, dict) and ctv_res.get("ok"):
                    ctv_connected = True
                    for fr in ctv_res.get("frames", []):
                        if not isinstance(fr, dict) or not fr.get("active", True):
                            continue
                        t_uid = str(fr.get("targetUid") or "").strip().upper()
                        t_uids = [str(u).strip().upper() for u in (fr.get("targetUids") or [])]
                        if t_uid == "ALL" or "ALL" in t_uids:
                            u_img = str(fr.get("url") or "").strip()
                            if u_img and u_img not in seen_urls:
                                seen_urls.add(u_img)
                                masked_img = _proxy_media_url(u_img)
                                all_frames.append({
                                    "id": fr.get("id") or f"ctv_{len(all_frames)}",
                                    "name": fr.get("name") or "Khung Độc Quyền VIP",
                                    "category": "Khung Nổi Bật",
                                    "group": "ctv_live",
                                    "image": masked_img,
                                    "rawImage": masked_img,
                                    "badge": "Nổi Bật",
                                    "source": "ctv_live",
                                })
            except Exception as e_ctv_fr:
                logger.warning(f"Fetch CTV live frames failed: {e_ctv_fr}")

            # 2. Nạp thêm 79 khung thư viện từ data/frames.json
            frames_path = os.path.join(os.path.dirname(__file__), "data", "frames.json")
            if os.path.exists(frames_path):
                try:
                    with open(frames_path, "r", encoding="utf-8") as f:
                        f_data = json.load(f)
                    for fr in f_data.get("frames", []):
                        raw_u = str(fr.get("rawImage") or fr.get("image") or "").strip()
                        if raw_u and raw_u not in seen_urls:
                            seen_urls.add(raw_u)
                            fr_copy = dict(fr)
                            if fr_copy.get("image"):
                                fr_copy["image"] = _proxy_media_url(fr_copy["image"])
                            if fr_copy.get("rawImage"):
                                fr_copy["rawImage"] = _proxy_media_url(fr_copy["rawImage"])
                            all_frames.append(fr_copy)
                except Exception as e_f:
                    logger.warning(f"Error reading data/frames.json: {e_f}")

            self._send_json(200, {
                "ok": True,
                "success": True,
                "ctv_connected": ctv_connected,
                "count": len(all_frames),
                "frames": all_frames,
            })
            return

        # 3.02 API Thư viện 449 Apple SF Symbols (Yêu cầu VIP/Admin)
        if path == "/api/features/symbols":
            if not self._require_vip_or_admin(params=params):
                return
            category = params.get("category", ["all"])[0].strip()
            q_kw = params.get("q", [""])[0].strip()
            try:
                sym_data = api.ctv_get_symbols(category=category, q=q_kw)
                if isinstance(sym_data, dict) and isinstance(sym_data.get("symbols"), list):
                    sym_copy = dict(sym_data)
                    masked_syms = []
                    for s in sym_data["symbols"]:
                        if isinstance(s, dict):
                            sc = dict(s)
                            if sc.get("previewUrl"):
                                sc["previewUrl"] = _proxy_media_url(sc["previewUrl"])
                            if sc.get("url"):
                                sc["url"] = _proxy_media_url(sc["url"])
                            masked_syms.append(sc)
                        else:
                            masked_syms.append(s)
                    sym_copy["symbols"] = masked_syms
                    sym_data = sym_copy
                self._send_json(200, sym_data)
            except Exception as e_sym:
                self._send_json(502, {"ok": False, "error": f"Không tải được kho SF Symbols từ máy chủ Locket: {e_sym}"})
            return

        # 3.03 API Bộ Lọc Màu 3D LUT (Yêu cầu VIP/Admin)
        if path == "/api/features/filters":
            if not self._require_vip_or_admin(params=params):
                return
            try:
                flt_data = api.ctv_get_filters()
                sample_luts = []
                for it in (flt_data.get("sampleLuts", []) or []):
                    if isinstance(it, dict):
                        itc = dict(it)
                        if itc.get("iconUrl"):
                            itc["iconUrl"] = _proxy_media_url(itc["iconUrl"])
                        if itc.get("icon"):
                            itc["icon"] = _proxy_media_url(itc["icon"])
                        sample_luts.append(itc)
                custom_luts = []
                for cf in (flt_data.get("customFilters", []) or []):
                    if isinstance(cf, dict) and cf.get("enabled", True) is not False:
                        cfc = dict(cf)
                        if cfc.get("iconUrl"):
                            cfc["iconUrl"] = _proxy_media_url(cfc["iconUrl"])
                        if cfc.get("icon"):
                            cfc["icon"] = _proxy_media_url(cfc["icon"])
                        custom_luts.append(cfc)
                self._send_json(200, {
                    "ok": True,
                    "sampleLuts": sample_luts,
                    "customFilters": custom_luts,
                    "total": len(sample_luts) + len(custom_luts),
                })
            except Exception as e_flt:
                self._send_json(502, {"ok": False, "error": f"Không tải được bộ lọc LUT từ máy chủ Locket: {e_flt}"})
            return

        # 3.04 API Brand Captions đang hoạt động của Shop (Yêu cầu VIP/Admin)
        if path == "/api/features/brand_captions":
            if not self._require_vip_or_admin(params=params):
                return
            try:
                cap_res = api.ctv_get_captions()
                public_caps = []
                for cp in (cap_res.get("captions", []) or []):
                    if not isinstance(cp, dict) or not cp.get("active", True):
                        continue
                    t_uid = str(cp.get("targetUid") or "").strip().upper()
                    t_uids = [str(u).strip().upper() for u in (cp.get("targetUids") or [])]
                    if t_uid == "ALL" or "ALL" in t_uids:
                        public_caps.append({
                            "id": cp.get("id"),
                            "text": cp.get("text", ""),
                            "icon": cp.get("icon", ""),
                            "iconType": cp.get("iconType", "emoji"),
                            "symbolName": cp.get("symbolName"),
                            "symbolPreviewUrl": _proxy_media_url(cp.get("symbolPreviewUrl")),
                            "colors": cp.get("colors") or ["#FFB800", "#FF8008"],
                        })
                self._send_json(200, {"ok": True, "captions": public_caps, "total": len(public_caps)})
            except Exception as e_bc:
                self._send_json(502, {"ok": False, "error": str(e_bc)})
            return

        # 3.1 API Danh sách đơn hàng vừa kích hoạt thành công (Đồng bộ máy chủ CTV + Đơn nội bộ)
        if path == "/api/recent_purchases":
            self._send_json(200, {"ok": True, "purchases": []})
            return

        if path == "/api/order_status":
            order_id = params.get("order_id", [""])[0].strip()
            force_check = params.get("force", ["0"])[0].strip() == "1"
            if not order_id:
                self._send_json(400, {"ok": False, "error": "Thiếu mã đơn hàng order_id"})
                return
            order = db.get_order(order_id)
            if not order:
                self._send_json(404, {"ok": False, "error": "Không tìm thấy đơn hàng"})
                return

            from order_service import payment_deadline, auto_activate_deadline, check_sepay_payments
            auto_dl = auto_activate_deadline(order)
            if (
                order.get("status") in (*db.UNPAID_ORDER_STATUSES, "cancelled")
                and getattr(config, "SEPAY_API_TOKEN", "")
                and (force_check or (auto_dl is not None and time.time() < auto_dl))
            ):
                try:
                    if BOT_LOOP and BOT_LOOP.is_running():
                        fut = asyncio.run_coroutine_threadsafe(
                            check_sepay_payments(BOT_INSTANCE, order_id=order_id, force_refresh=force_check),
                            BOT_LOOP,
                        )
                        fut.result(timeout=7)
                    else:
                        asyncio.run(check_sepay_payments(BOT_INSTANCE, order_id=order_id, force_refresh=force_check))
                except Exception as e_chk:
                    logger.warning(f"On-demand SePay check for {order_id} error: {e_chk}")
                order = db.get_order(order_id) or order

            deadline = payment_deadline(order)
            status = order.get("status", "waiting_payment")
            if status in ("pending", "waiting_payment") and deadline is not None and time.time() >= deadline:
                status = "expired"
            elif status == "cancelled" and order.get("cancel_reason"):
                status = "expired"

            is_done = order.get("status") == "done"
            prod_key = order.get("product")
            is_locket_ai = (prod_key == "locket_ai")
            is_filter_topup = (prod_key == "filter_topup")
            is_caption_pack = (prod_key == "caption_pack")
            is_combo = prod_key in ("combo", "locket_spotify")
            has_studio = order.get("has_studio", False) or (prod_key == "studio_caption")
            studio_url = "/#section_features" if has_studio else None

            if is_locket_ai or is_filter_topup or is_caption_pack:
                download_url = None
            else:
                download_url = f"/api/download_profile?order_id={order_id}" if is_done else None

            self._send_json(200, {
                "ok": True,
                "order_id": order_id,
                "status": status,
                "is_paid": is_done,
                "expires_at_ms": int(deadline * 1000) if deadline is not None else None,
                "product": order.get("product"),
                "plan": order.get("plan"),
                "plan_label": order.get("plan_label"),
                "price": order.get("price"),
                "uid": order.get("uid"),
                "display_name": order.get("display_name"),
                "download_url": download_url,
                "dns_link": download_url,
                "direct_safari_url": download_url,
                "created_at": order.get("created_at"),
                "is_locket_ai": is_locket_ai,
                "is_caption_pack": is_caption_pack,
                "contact_admin": is_locket_ai or is_filter_topup,
                "has_studio": has_studio,
                "studio_url": studio_url if is_done else None,
                "vip_download_url": None,
            })
            return

        # 5. API Tải file .mobileconfig (BẢO VỆ CHẶT CHẼ: CHỈ CHO ĐƠN ĐÃ THANH TOÁN THẬT)
        if path == "/api/download_profile" or (path.endswith(".mobileconfig") and not path.endswith("Free.mobileconfig") and not path.endswith("LocketNgon.mobileconfig")):
            order_id = params.get("order_id", [""])[0].strip()
            username = params.get("username", [""])[0].strip() or params.get("uid", [""])[0].strip()

            order = None
            if order_id:
                o_check = db.get_order(order_id)
                if o_check and o_check.get("status") == "done":
                    order = o_check

            if not order and username:
                clean_u = utils.clean_input(username).lower().lstrip("@")
                for od in db.get_orders().values():
                    if od.get("status") == "done":
                        u_list = [
                            str(od.get("identifier", "")).lower().lstrip("@"),
                            str(od.get("uid", "")).lower(),
                            str(od.get("display_name", "")).lower().lstrip("@"),
                            str(od.get("username", "")).lower().lstrip("@"),
                            str(od.get("account_target", "")).lower().lstrip("@")
                        ]
                        if clean_u in u_list:
                            order = od
                            break
                # Fallback: kiểm tra trực tiếp trên máy chủ API CTV (chỉ cho tài khoản của chính shop)
                if not order and len(clean_u) >= 3:
                    try:
                        ctv_info = api.check_uid_details(clean_u, "locket")
                        dt = ctv_info.get("data", {}) if isinstance(ctv_info, dict) else {}
                        if (dt.get("active") is True or dt.get("status") == "ACTIVE") and (dt.get("isMine") is True):
                            order = {
                                "order_id": f"CTV_{clean_u.upper()}",
                                "product": dt.get("service") or "locket",
                                "display_name": dt.get("username") or clean_u,
                                "uid": dt.get("uid") or clean_u,
                                "status": "done"
                            }
                    except Exception:
                        pass

            # Nếu không tìm thấy đơn hàng ĐÃ THANH TOÁN (status == done) -> TỪ CHỐI TẢI
            if not order:
                self._send_json(403, {
                    "ok": False,
                    "error": "⛔ Không thể tải cấu hình: Đơn hàng chưa thanh toán hoặc chưa kích hoạt thành công!"
                })
                return

            product_key = order.get("product", "locket")
            if product_key in ("locket_ai", "filter_topup", "caption_pack", "studio_caption"):
                self._send_json(403, {
                    "ok": False,
                    "error": "Gói này không sử dụng file tải DNS mặc định. Vui lòng xem hướng dẫn hoặc liên hệ Admin hỗ trợ!"
                })
                return

            if product_key in ("combo", "locket_spotify"):
                combo_dns = order.get("dns_link") or f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
                self.send_response(302)
                self.send_header("Location", combo_dns)
                self._send_cors_headers()
                self.end_headers()
                return

            # Chuyển hướng trực tiếp về hồ sơ chính chủ AloPremiumShop trên server CTV cho Locket và Spotify
            official_dns_url = order.get("dns_link") or f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
            self.send_response(302)
            self.send_header("Location", official_dns_url)
            self._send_cors_headers()
            self.end_headers()
            return

        # 6. API Tra cứu đơn hàng & Lịch sử mua DNS (Khớp Order ID, Username Locket/Spotify hoặc UID)
        if path == "/api/lookup":
            q = params.get("q", [""])[0].strip()
            if len(q) < 3:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập tối thiểu 3 ký tự (Mã đơn hoặc Username)!"})
                return

            orders = db.get_orders()
            results = []
            q_clean = utils.clean_input(q).lower().lstrip("@")
            q_raw = q.lower().strip()
            q_no_order = q_raw.replace("order_", "").strip()

            for oid, od in orders.items():
                oid_lower = oid.lower()
                o_user = str(od.get("username", "")).lower().lstrip("@")
                o_ident = str(od.get("identifier", "")).lower().lstrip("@")
                o_disp = str(od.get("display_name", "")).lower().lstrip("@")
                o_target = str(od.get("account_target", "")).lower().lstrip("@")
                o_uid = str(od.get("uid", "")).lower()

                match = (
                    oid_lower == q_raw or
                    oid_lower == q_no_order or
                    (bool(q_clean) and (
                        o_user == q_clean or
                        o_ident == q_clean or
                        o_disp == q_clean or
                        o_target == q_clean or
                        o_uid == q_clean
                    ))
                )

                if match:
                    is_done = od.get("status") == "done"
                    prod_k = od.get("product") or "locket"
                    is_ai = (prod_k == "locket_ai")
                    is_filter = (prod_k == "filter_topup")
                    is_cap = (prod_k == "caption_pack")
                    u_disp = od.get("display_name") or od.get("username") or od.get("identifier") or "Khách VIP"
                    u_clean = utils.clean_input(str(u_disp)).lstrip("@")
                    if is_ai or is_filter or is_cap:
                        exact_safari = None
                        exact_dl = None
                    else:
                        exact_dl = f"/api/download_profile?order_id={oid}" if is_done else None
                        exact_safari = exact_dl

                    results.append({
                        "order_id": oid,
                        "product": prod_k,
                        "plan": od.get("plan") or "VIP",
                        "plan_label": od.get("plan_label"),
                        "price": od.get("price", 0),
                        "status": od.get("status"),
                        "uid": od.get("uid"),
                        "display_name": u_disp,
                        "avatar": _proxy_media_url(od.get("avatar")),
                        "created_at": od.get("created_at"),
                        "download_url": exact_dl,
                        "direct_safari_url": exact_safari,
                        "dns_link": exact_safari,
                        "studio_url": None,
                        "contact_admin": is_ai or is_filter
                    })

            # Nếu chưa thấy trong database local nhưng tài khoản đã kích hoạt trên máy chủ API CTV (web chủ)
            if len(results) == 0 and len(q_clean) >= 3:
                # 1. Quét nhanh trong danh sách UIDs đã kích hoạt từ web chủ
                try:
                    uids = api.get_activated_uids()
                    for it in uids:
                        if it.get("isMine") is False:
                            continue
                        it_u = str(it.get("username", "")).lower().lstrip("@")
                        it_uid = str(it.get("uidString", "")).lower()
                        if q_clean == it_u or q_clean == it_uid:
                            pkg_it = it.get("package") or {}
                            svc_it = it.get("service") or "locket"
                            safe_suffix = (it_uid[:8] if len(it_uid) >= 8 else it_u[:8]).upper()
                            oid_it = f"CTV_{safe_suffix}"
                            results.append(self._upsert_ctv_lookup_order(
                                ret_oid=oid_it,
                                product=svc_it,
                                plan_name=pkg_it.get("name") or "VIP",
                                ret_user=it.get("username") or it_u or q_clean,
                                ret_uid=it.get("uidString") or q_clean,
                                created_at=it.get("createdAt"),
                                expires_at=it.get("expiresAt"),
                                avatar=it.get("avatarUrl"),
                            ))
                            break
                except Exception as e_q_uids:
                    logger.warning(f"Error checking active UIDs during lookup: {e_q_uids}")

                # 2. Nếu vẫn chưa có, gọi tra cứu chi tiết UID (cả Locket và Spotify)
                if len(results) == 0:
                    for svc in ("locket", "spotify"):
                        try:
                            ctv_res = api.check_uid_details(q_clean, svc)
                            dt = ctv_res.get("data", {}) if isinstance(ctv_res, dict) else {}
                            if (dt.get("active") is True or dt.get("status") == "ACTIVE") and (dt.get("isMine") is True):
                                pkg_info = dt.get("package") or {}
                                ret_uid = dt.get("uid") or q_clean
                                ret_user = dt.get("username") or q_clean
                                safe_suffix = (ret_uid[:8] if len(ret_uid) >= 8 else ret_user[:8]).upper()
                                ret_oid = f"CTV_{safe_suffix}"
                                results.append(self._upsert_ctv_lookup_order(
                                    ret_oid=ret_oid,
                                    product=dt.get("service") or svc,
                                    plan_name=pkg_info.get("name") or "VIP",
                                    ret_user=ret_user,
                                    ret_uid=ret_uid,
                                    created_at=dt.get("createdAt"),
                                    expires_at=dt.get("expiresAt"),
                                    avatar=dt.get("avatarUrl"),
                                ))
                                break
                        except Exception:
                            pass

            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            self._send_json(200, {"ok": True, "orders": results[:5]})
            return

        # API Tạo Mã QR Code động định dạng PNG từ link tải / dữ liệu bất kỳ
        if path == "/api/qr":
            raw_data = params.get("data", [""])[0].strip()
            if not raw_data:
                self._send_json(400, {"ok": False, "error": "Thiếu tham số data"})
                return
            if len(raw_data) > 1024:
                self._send_json(400, {"ok": False, "error": "Dữ liệu mã QR vượt quá 1024 ký tự"})
                return
            try:
                bio = utils.generate_qr_code(raw_data)
                qr_bytes = bio.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(qr_bytes)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(qr_bytes)
            except Exception as e:
                self._send_json(500, {"ok": False, "error": f"Lỗi tạo mã QR: {e}"})
            return

        # Phục vụ Trang Quản Trị Web App (admin.html)
        if path in ("/admin", "/admin.html"):
            admin_path = os.path.join(os.path.dirname(__file__), "admin.html")
            if os.path.exists(admin_path):
                with open(admin_path, "r", encoding="utf-8") as f:
                    html_bytes = _protect_html_response(f.read())
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "SAMEORIGIN")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            else:
                self._send_json(404, {"ok": False, "error": "admin.html not found"})
                return

        # API Admin: Lấy thông tin đồng bộ API CTV & Gói cước
        if path == "/api/admin/api_info":
            if not self._require_admin(params=params):
                return
            svc_filter = params.get("service", ["all"])[0].strip().lower()
            if svc_filter not in ("all", "spotify", "locket"):
                svc_filter = "all"
            try:
                acc = api.get_account_info().get("data", {})
            except Exception as e:
                acc = {"error": str(e), "balanceCoin": 0}

            try:
                pkgs = api.get_packages(svc_filter).get("data", [])
            except Exception as e:
                pkgs = []

            codes = list(db.get_codes().values())
            try:
                activated_uids = api.get_activated_uids()
            except Exception:
                activated_uids = []

            self._send_json(200, {
                "ok": True,
                "service": svc_filter,
                "account": acc,
                "packages": pkgs,
                "codes": codes,
                "activated_uids": activated_uids,
                "api_base_url": config.API_BASE_URL,
            })
            return

        # API Admin: Tổng quan Tính Năng CTV (Frames, Brand Captions, Filters LUT)
        if path == "/api/admin/ctv/overview":
            if not self._require_admin(params=params):
                return
            frames_data = {}
            captions_data = {}
            filters_data = {}
            acc_data = {}
            errors = {}
            try:
                acc_data = api.get_account_info().get("data", {})
            except Exception as e_acc:
                errors["account"] = str(e_acc)
            try:
                frames_data = api.ctv_get_frames(force_refresh=True)
            except Exception as e_fr:
                errors["frames"] = str(e_fr)
            try:
                captions_data = api.ctv_get_captions()
            except Exception as e_cp:
                errors["captions"] = str(e_cp)
            try:
                filters_data = api.ctv_get_filters(force_refresh=True)
            except Exception as e_fl:
                errors["filters"] = str(e_fl)

            self._send_json(200, {
                "ok": True,
                "account": acc_data,
                "balanceCoin": acc_data.get("balanceCoin"),
                "frames": frames_data.get("frames", []),
                "framesExpiresAt": frames_data.get("expiresAt"),
                "captions": captions_data.get("captions", []),
                "captionsMode": captions_data.get("mode", "brand"),
                "captionsExpiresAt": captions_data.get("expiresAt"),
                "sampleLuts": filters_data.get("sampleLuts", []),
                "customFilters": filters_data.get("customFilters", []),
                "filtersExpiresAt": filters_data.get("expiresAt"),
                "errors": errors,
            })
            return

        # API Admin: Tra cứu Caption CTV hoặc theo UID khách hàng
        if path == "/api/admin/ctv/captions":
            if not self._require_admin(params=params):
                return
            uid_q = params.get("uid", [""])[0].strip()
            try:
                res = api.ctv_get_captions(uid=uid_q)
                self._send_json(200, res)
            except Exception as e_c:
                self._send_json(400, {"ok": False, "error": str(e_c)})
            return

        # API Admin: Lấy danh sách đơn hàng
        if path == "/api/admin/orders":
            if not self._require_admin(params=params):
                return
            all_orders = list(db.get_orders().values())
            all_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            self._send_json(200, {"ok": True, "orders": all_orders[:50]})
            return

        # API Admin: Lấy danh sách bảng giá & mã gói (kèm cấu hình Banner)
        if path == "/api/admin/prices":
            if not self._require_admin(params=params):
                return
            self._send_json(200, {
                "ok": True,
                "products": config.PRODUCTS,
                "custom_prices": db.get_custom_prices(),
                "banner": db.get_banner_config()
            })
            return

        # API Admin: Lấy danh sách mã giảm giá
        if path == "/api/admin/codes":
            if not self._require_admin(params=params):
                return
            codes = list(db.get_codes().values())
            self._send_json(200, {"ok": True, "codes": codes})
            return

        # API Admin: Thống kê doanh thu & tổng quan toàn diện
        if path == "/api/admin/stats":
            if not self._require_admin(params=params):
                return

            orders = list(db.get_orders().values())
            users = db.get_users()
            done_orders = [o for o in orders if o.get("status") == "done"]
            pending_orders = [o for o in orders if o.get("status") in (*db.UNPAID_ORDER_STATUSES, "paid_review")]
            rejected_orders = [o for o in orders if o.get("status") in ("cancelled", "rejected", "failed")]
            
            total_revenue = sum(o.get("price", 0) for o in done_orders)

            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            today_orders = [o for o in done_orders if str(o.get("done_at", "")).startswith(today_str) or str(o.get("created_at", "")).startswith(today_str)]
            today_revenue = sum(o.get("price", 0) for o in today_orders)

            locket_done = [o for o in done_orders if o.get("product") == "locket"]
            spotify_done = [o for o in done_orders if o.get("product") == "spotify"]
            combo_done = [o for o in done_orders if o.get("product") in ("combo", "locket_spotify")]
            ai_done = [o for o in done_orders if o.get("product") == "locket_ai"]
            addon_done = [o for o in done_orders if o.get("product") in ("filter_topup", "caption_pack", "studio_caption")]

            self._send_json(200, {
                "ok": True,
                "stats": {
                    "total_revenue": total_revenue,
                    "today_revenue": today_revenue,
                    "total_orders": len(orders),
                    "done_count": len(done_orders),
                    "pending_count": len(pending_orders),
                    "rejected_count": len(rejected_orders),
                    "total_users": len(users),
                    "locket": {
                        "count": len(locket_done),
                        "revenue": sum(o.get("price", 0) for o in locket_done)
                    },
                    "spotify": {
                        "count": len(spotify_done),
                        "revenue": sum(o.get("price", 0) for o in spotify_done)
                    },
                    "combo": {
                        "count": len(combo_done),
                        "revenue": sum(o.get("price", 0) for o in combo_done)
                    },
                    "locket_ai": {
                        "count": len(ai_done),
                        "revenue": sum(o.get("price", 0) for o in ai_done)
                    },
                    "addons": {
                        "count": len(addon_done),
                        "revenue": sum(o.get("price", 0) for o in addon_done)
                    }
                }
            })
            return

        # API Admin: Danh sách khách hàng & chi tiêu
        if path == "/api/admin/users":
            if not self._require_admin(params=params):
                return

            raw_users = db.get_users()
            orders = list(db.get_orders().values())

            user_spending = {}
            user_orders_count = {}
            for o in orders:
                uid = o.get("user_id")
                if uid:
                    user_orders_count[uid] = user_orders_count.get(uid, 0) + 1
                    if o.get("status") == "done":
                        user_spending[uid] = user_spending.get(uid, 0) + o.get("price", 0)

            user_list = []
            for uid_str, u in raw_users.items():
                try:
                    uid_int = int(uid_str)
                except Exception:
                    uid_int = uid_str
                banned, b_reason = db.is_banned(uid_str)
                user_list.append({
                    "user_id": uid_str,
                    "username": u.get("username", "") or "Ẩn danh",
                    "first_name": u.get("first_name", "") or "",
                    "joined_at": u.get("joined_at", ""),
                    "orders_count": user_orders_count.get(uid_int, 0),
                    "total_spent": user_spending.get(uid_int, 0),
                    "is_banned": banned,
                    "ban_reason": b_reason
                })

            user_list.sort(key=lambda x: x.get("total_spent", 0), reverse=True)
            self._send_json(200, {"ok": True, "users": user_list[:100]})
            return

        # API Admin: Thông tin cấu hình hệ thống
        if path == "/api/admin/system_info":
            if not self._require_admin(params=params):
                return

            self._send_json(200, {
                "ok": True,
                "info": {
                    "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                    "bank_account": getattr(config, "BANK_ACCOUNT", "34528022007"),
                    "account_holder": getattr(config, "ACCOUNT_HOLDER", "NGUYEN NHU QUYNH"),
                    "bot_username": "@AloPremiumShop_Bot",
                    "domain": "https://alopremium.shop",
                    "sepay_connected": bool(getattr(config, "SEPAY_API_TOKEN", "")),
                    "api_base_url": getattr(config, "API_BASE_URL", "https://locket.2707226.xyz"),
                    "server_status": "ONLINE 24/7"
                }
            })
            return

        # 7. Phục vụ Trang chủ Web App (index.html)
        if path in ("/", "/index.html", "/LocketNgon", "/LocketNgon.html"):
            index_path = os.path.join(os.path.dirname(__file__), "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    html_bytes = _protect_html_response(f.read())
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "SAMEORIGIN")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"AloPremium.shop Web Storefront is ready.")
                return

        # Mặc định 404
        self._send_json(404, {"ok": False, "error": "Endpoint not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        client_ip = self._get_client_ip()

        # Kiểm tra Rate Limit cho các API POST
        allowed, reason = check_ip_rate_limit(client_ip, max_requests=40, window_secs=60)
        if not allowed:
            self._send_json(429, {"ok": False, "error": reason})
            return

        # Xử lý riêng Upload Multipart/JSON cho file 3D LUT (.cube) trước khi đọc body JSON
        ctype = self.headers.get("Content-Type", "")
        if path == "/api/admin/ctv/filters/upload" and "multipart/form-data" in ctype.lower():
            pin_header = (self.headers.get("X-Admin-PIN") or self.headers.get("X-Admin-Pin") or params.get("pin", [""])[0] or "").strip()
            try:
                fields, file_bytes, filename = self._read_multipart_form()
            except ValueError as e_mp:
                self._send_json(400, {"ok": False, "error": str(e_mp)})
                return
            pin = (pin_header or fields.get("pin") or "").strip()
            if not self._require_admin(explicit_pin=pin):
                return
            if not file_bytes or not filename.lower().endswith(".cube"):
                self._send_json(400, {"ok": False, "error": "Vui lòng tải lên file 3D LUT định dạng .cube (tối đa 20MB)."})
                return
            lut_name = fields.get("name", "").strip()
            try:
                res = api.ctv_upload_filter(file_bytes=file_bytes, filename=filename, name=lut_name)
                self._send_json(200, res)
            except Exception as e_up:
                self._send_json(400, {"ok": False, "error": str(e_up)})
            return

        body = self._read_json_body()

        # API Admin: Đăng nhập mã PIN
        if path == "/api/admin/login":
            if self._require_admin(body=body):
                self._send_json(200, {"ok": True})
            return

        # API Admin: Cập nhật thông báo ưu đãi (Banner Header Web)
        if path == "/api/admin/update_banner":
            if not self._require_admin(body=body):
                return
            tag = body.get("tag", "🔥 HOT ƯU ĐÃI")
            text = body.get("text", "")
            enabled = body.get("enabled", True)
            saved_banner = db.update_banner_config(tag, text, enabled)
            self._send_json(200, {
                "ok": True,
                "message": "Đã cập nhật banner thông báo ưu đãi thành công!",
                "banner": saved_banner
            })
            return

        # API Admin: Cập nhật giá 1 gói cước (Đồng bộ Web & Bot)
        if path == "/api/admin/update_price":
            if not self._require_admin(body=body):
                return
            product = str(body.get("product", "")).strip()
            plan = str(body.get("plan", "")).strip()
            price = body.get("price")
            if not product or not plan or price is None:
                self._send_json(400, {"ok": False, "error": "Thiếu product, plan hoặc price"})
                return
            try:
                price = int(price)
                if price < 0:
                    raise ValueError()
            except Exception:
                self._send_json(400, {"ok": False, "error": "Giá tiền không hợp lệ"})
                return

            ok = db.update_plan_price(product, plan, price)
            if not ok:
                self._send_json(400, {"ok": False, "error": "Gói cước không tồn tại"})
                return

            self._send_json(200, {
                "ok": True,
                "message": f"Đã cập nhật giá gói thành công!",
                "products": config.PRODUCTS
            })
            return

        # API Admin: Cập nhật toàn bộ bảng giá cùng lúc
        if path == "/api/admin/update_all_prices":
            if not self._require_admin(body=body):
                return
            prices = body.get("prices")
            if not isinstance(prices, dict):
                self._send_json(400, {"ok": False, "error": "Dữ liệu prices không hợp lệ"})
                return

            db.update_all_prices(prices)
            self._send_json(200, {
                "ok": True,
                "message": "Đã lưu toàn bộ bảng giá mới thành công!",
                "products": config.PRODUCTS
            })
            return

        # API Admin: Khôi phục bảng giá về mặc định
        if path == "/api/admin/reset_prices":
            if not self._require_admin(body=body):
                return
            db.reset_default_prices()
            self._send_json(200, {
                "ok": True,
                "message": "Đã khôi phục bảng giá về mặc định thành công!",
                "products": config.PRODUCTS
            })
            return

        # API Admin: Tạo mã giảm giá mới (Hỗ trợ 1 mã hoặc nhiều mã cùng lúc cách nhau bằng dấu phẩy)
        if path == "/api/admin/add_code":
            if not self._require_admin(body=body):
                return

            raw_code = str(body.get("code", "")).strip().upper()
            try:
                discount_pct = int(body.get("discount_pct", 0))
                if not (1 <= discount_pct <= 90):
                    raise ValueError()
            except Exception:
                self._send_json(400, {"ok": False, "error": "Phần trăm giảm giá phải từ 1% đến 90% (tránh giá bị ép về 1.000đ)"})
                return

            max_uses = int(body.get("max_uses", 0) or 0)

            code_list = [c.strip().upper() for c in re.split(r"[,;\s\n\r]+", raw_code) if len(c.strip()) >= 2]
            
            if not code_list:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập ít nhất 1 mã hợp lệ (tối thiểu 2 ký tự)"})
                return

            created_items = db.add_codes_batch(code_list, discount_pct, max_uses)
            self._send_json(200, {
                "ok": True, 
                "count": len(created_items),
                "codes": [it["code"] for it in created_items],
                "item": created_items[0] if created_items else None
            })
            return

        # API Admin: Xóa mã giảm giá
        if path == "/api/admin/del_code":
            if not self._require_admin(body=body):
                return
            code = str(body.get("code", "")).strip().upper()
            success = db.del_code(code)
            if success:
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"ok": False, "error": f"Không tìm thấy mã {code}"})
            return

        # API Admin: Tra cứu UID qua API CTV
        if path == "/api/admin/check_uid":
            if not self._require_admin(body=body):
                return
            identifier = str(body.get("identifier", "")).strip()
            service = str(body.get("service", "locket")).strip()
            try:
                if service == "spotify":
                    res = api.spotify_check(identifier)
                else:
                    res = api.check_uid_details(identifier, "locket")
                self._send_json(200, {"ok": True, "data": res})
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
            return

        # API Admin: Kích hoạt gói thủ công trực tiếp lên máy chủ API CTV
        if path == "/api/admin/manual_activate":
            if not self._require_admin(body=body):
                return
            username = str(body.get("username", "")).strip()
            package_code = str(body.get("package_code", "LKGVV")).strip()
            service = str(body.get("service", "locket")).strip()
            if not username:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username hoặc UID!"})
                return
            try:
                clean_target = utils.clean_input(username)
                res = api.create_subscription(
                    uid=clean_target,
                    package_code=package_code,
                    service=service,
                    note=f"Admin manual activation for {clean_target}"
                )
                self._send_json(200, {
                    "ok": True, 
                    "data": res, 
                    "message": f"Kích hoạt thành công {clean_target} lên gói {package_code} trên máy chủ!"
                })
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
            return

        # API Admin: Duyệt đơn và kích hoạt tự động 1-chạm
        if path == "/api/admin/approve_order":
            if not self._require_admin(body=body):
                return
            order_id = str(body.get("order_id", "")).strip()
            order = db.get_order(order_id)
            if not order:
                self._send_json(404, {"ok": False, "error": "Không tìm thấy đơn hàng trong hệ thống"})
                return
            if order.get("status") == "done":
                self._send_json(400, {"ok": False, "error": "Đơn hàng này đã được duyệt trước đó rồi"})
                return

            from order_service import execute_order_activation
            try:
                if BOT_LOOP:
                    future = asyncio.run_coroutine_threadsafe(
                        execute_order_activation(BOT_INSTANCE, order_id),
                        BOT_LOOP
                    )
                    ok, msg = future.result(timeout=20)
                else:
                    ok, msg = asyncio.run(execute_order_activation(BOT_INSTANCE, order_id))

                if ok:
                    self._send_json(200, {"ok": True, "message": f"Đã duyệt và kích hoạt thành công đơn ORDER_{order_id}!"})
                else:
                    self._send_json(400, {"ok": False, "error": f"Lỗi kích hoạt API: {msg}"})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": f"Lỗi xử lý duyệt đơn: {e}"})
            return

        # API Admin: Từ chối / Hủy đơn hàng
        if path == "/api/admin/reject_order":
            if not self._require_admin(body=body):
                return
            order_id = str(body.get("order_id", "")).strip()
            reason = str(body.get("reason", "Admin hủy đơn thủ công")).strip()
            order = db.get_order(order_id)
            if not order:
                self._send_json(404, {"ok": False, "error": "Không tìm thấy đơn hàng"})
                return
            
            if not db.update_order(
                order_id, expected_statuses=db.UNPAID_ORDER_STATUSES,
                status="rejected", rejected_reason=reason, rejected_at=datetime.now().isoformat(),
            ):
                self._send_json(409, {"ok": False, "error": "Đơn không còn chờ thanh toán hoặc duyệt. Hãy kiểm tra lại giao dịch trước khi xử lý."})
                return
            try:
                if BOT_INSTANCE and order.get("user_id"):
                    coro = BOT_INSTANCE.send_message(
                        chat_id=int(order["user_id"]),
                        text=f"🚫 Đơn hàng <code>ORDER_{order_id}</code> đã bị từ chối/hủy bởi Quản trị viên.\nLý do: <i>{reason}</i>\nNếu bạn đã chuyển khoản, vui lòng liên hệ CSKH để được hỗ trợ.",
                        parse_mode="HTML"
                    )
                    if BOT_LOOP:
                        asyncio.run_coroutine_threadsafe(coro, BOT_LOOP)
                    else:
                        asyncio.run(coro)
            except Exception:
                pass
            self._send_json(200, {"ok": True, "message": f"Đã từ chối đơn hàng ORDER_{order_id}!"})
            return

        # API Admin: Khóa / Mở khóa khách hàng
        if path == "/api/admin/toggle_ban":
            if not self._require_admin(body=body):
                return
            user_id = str(body.get("user_id", "")).strip()
            should_ban = bool(body.get("ban", True))
            reason = str(body.get("reason", "Vi phạm quy định shop")).strip()
            if should_ban:
                db.ban_user(user_id, reason)
                self._send_json(200, {"ok": True, "message": f"Đã khóa người dùng {user_id}"})
            else:
                db.unban_user(user_id)
                self._send_json(200, {"ok": True, "message": f"Đã mở khóa người dùng {user_id}"})
            return

        # API Admin: Thêm / Cập nhật Khung Widget CTV lên locket.2707226.xyz
        if path == "/api/admin/ctv/frames":
            if not self._require_admin(body=body):
                return
            url_img = _resolve_frame_url(str(body.get("url", "")).strip())
            name = str(body.get("name", "")).strip()
            target_uid = str(body.get("targetUid", "ALL")).strip() or "ALL"
            target_uids = body.get("targetUids")
            active = bool(body.get("active", True))
            if not url_img or not url_img.startswith("http"):
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập URL ảnh khung PNG hợp lệ (bắt đầu bằng https://)!"})
                return
            try:
                res = api.ctv_save_frame(
                    url_img=url_img,
                    name=name,
                    target_uid=target_uid,
                    target_uids=target_uids if isinstance(target_uids, list) else None,
                    active=active,
                )
                self._send_json(200, res)
            except Exception as e_fr:
                self._send_json(400, {"ok": False, "error": str(e_fr)})
            return

        # API Admin: Thêm / Cập nhật Brand Caption hoặc Caption khách hàng lên locket.2707226.xyz
        if path == "/api/admin/ctv/captions":
            if not self._require_admin(body=body):
                return
            text_val = str(body.get("text", "")).strip()
            if not text_val:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập nội dung Caption!"})
                return
            uid_val = str(body.get("uid", "")).strip()
            target_uid = str(body.get("targetUid", "")).strip()
            if not uid_val and not target_uid:
                target_uid = "ALL"
            try:
                res = api.ctv_save_caption(
                    text=text_val,
                    uid=uid_val,
                    icon=str(body.get("icon", "")).strip(),
                    icon_type=str(body.get("iconType", "")).strip(),
                    symbol_name=str(body.get("symbolName", "")).strip(),
                    colors=body.get("colors") if isinstance(body.get("colors"), list) else None,
                    target_uid=target_uid,
                    active=bool(body.get("active", True)),
                )
                self._send_json(200, res)
            except Exception as e_cp:
                self._send_json(400, {"ok": False, "error": str(e_cp)})
            return

        # API Admin: Bật / Tắt Bộ Lọc Màu LUT trên locket.2707226.xyz
        if path == "/api/admin/ctv/filters/toggle":
            if not self._require_admin(body=body):
                return
            filter_id = str(body.get("filterId", "")).strip()
            enabled = bool(body.get("enabled", True))
            if not filter_id:
                self._send_json(400, {"ok": False, "error": "Thiếu filterId cần bật/tắt!"})
                return
            try:
                res = api.ctv_toggle_filter(filter_id=filter_id, enabled=enabled)
                self._send_json(200, res)
            except Exception as e_tg:
                self._send_json(400, {"ok": False, "error": str(e_tg)})
            return

        # API Admin: Upload 3D LUT .cube dạng JSON Base64 (dự phòng khi không dùng multipart)
        if path == "/api/admin/ctv/filters/upload":
            if not self._require_admin(body=body):
                return
            filename = os.path.basename(str(body.get("filename", "")).strip() or "custom.cube")
            file_b64 = str(body.get("file_b64", "")).strip()
            lut_name = str(body.get("name", "")).strip()
            if not file_b64 or not filename.lower().endswith(".cube"):
                self._send_json(400, {"ok": False, "error": "Vui lòng gửi file .cube hợp lệ!"})
                return
            try:
                if "," in file_b64:
                    file_b64 = file_b64.split(",", 1)[1]
                file_bytes = base64.b64decode(file_b64)
                if len(file_bytes) > 20 * 1024 * 1024:
                    self._send_json(413, {"ok": False, "error": "Dung lượng file vượt quá 20MB!"})
                    return
                res = api.ctv_upload_filter(file_bytes=file_bytes, filename=filename, name=lut_name)
                self._send_json(200, res)
            except Exception as e_b64:
                self._send_json(400, {"ok": False, "error": str(e_b64)})
            return

        # API Admin: Tải & Thêm 3D LUT (.cube) từ Link bên ngoài (Drive, Dropbox, GitHub, Web)
        if path == "/api/admin/ctv/filters/upload_url":
            if not self._require_admin(body=body):
                return
            ext_url = str(body.get("url", "")).strip()
            lut_name = str(body.get("name", "")).strip()
            if not ext_url:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập link tải file .cube bên ngoài!"})
                return
            try:
                res = api.ctv_upload_filter_from_url(external_url=ext_url, name=lut_name)
                self._send_json(200, res)
            except Exception as e_u:
                self._send_json(400, {"ok": False, "error": str(e_u)})
            return

        # API Upload ảnh khung PNG từ máy tính (Admin PIN hoặc Khách VIP đã xác thực)
        if path == "/api/upload_frame_image":
            pin = self._extract_admin_pin(params=params, body=body)
            ident = str(body.get("identifier", "")).strip()
            if pin:
                if not self._require_admin(params=params, body=body):
                    return
            else:
                if not ident:
                    self._send_json(401, {"ok": False, "error": "Vui lòng kết nối tài khoản Locket VIP trước khi tải khung ảnh lên!"})
                    return
                is_vip, info = self._verify_customer_locket_vip(ident)
                if not is_vip:
                    self._send_json(403, {"ok": False, "error": info.get("error") or "Tài khoản chưa kích hoạt Locket Gold VIP để tải khung lên máy chủ."})
                    return
                up_ok, up_reason = check_upload_rate_limit(client_ip)
                if not up_ok:
                    self._send_json(429, {"ok": False, "error": up_reason})
                    return

            img_b64 = str(body.get("image_b64", "")).strip()
            if not img_b64:
                self._send_json(400, {"ok": False, "error": "Thiếu dữ liệu ảnh khung!"})
                return
            try:
                if "," in img_b64:
                    img_b64 = img_b64.split(",", 1)[1]
                raw_img = base64.b64decode(img_b64)
                if len(raw_img) > 5 * 1024 * 1024:
                    self._send_json(413, {"ok": False, "error": "Ảnh khung tối đa 5MB!"})
                    return
                if raw_img.startswith(b"\x89PNG\r\n\x1a\n"):
                    ext = "png"
                elif raw_img[:4] == b"RIFF" and raw_img[8:12] == b"WEBP":
                    ext = "webp"
                else:
                    self._send_json(400, {"ok": False, "error": "Chỉ hỗ trợ ảnh khung PNG trong suốt hoặc WEBP!"})
                    return

                up_dir = os.path.join(os.path.dirname(__file__), "assets", "uploads", "frames")
                os.makedirs(up_dir, exist_ok=True)
                fname = f"frame_{uuid.uuid4().hex[:12]}.{ext}"
                fpath = os.path.join(up_dir, fname)
                with open(fpath, "wb") as f_out:
                    f_out.write(raw_img)

                base_web = getattr(config, "WEBSITE_URL", "https://alopremium.shop").rstrip("/")
                allowed_host = urlparse(base_web).netloc.lower()
                host_hdr = self.headers.get("Host", "").strip()
                if host_hdr and (host_hdr.lower() == allowed_host or host_hdr.lower().endswith(".onrender.com")):
                    public_url = f"https://{host_hdr}/assets/uploads/frames/{fname}"
                else:
                    public_url = f"{base_web}/assets/uploads/frames/{fname}"
                self._send_json(200, {"ok": True, "url": public_url, "local_path": f"/assets/uploads/frames/{fname}"})
            except Exception as e_img:
                self._send_json(400, {"ok": False, "error": f"Lỗi xử lý ảnh khung: {e_img}"})
            return

        # 1.1 API Khách hàng kết nối tài khoản Locket với mục Tính Năng VIP (Chỉ mở khi đã mua gói VIP)
        if path == "/api/features/connect_uid":
            raw_id = str(body.get("identifier", "") or body.get("username", "") or body.get("uid", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username Locket của bạn!"})
                return

            is_vip, info = self._verify_customer_locket_vip(raw_id)
            if "error" in info:
                self._send_json(400, {"ok": False, "error": info["error"]})
                return
            if isinstance(info, dict) and info.get("avatar"):
                info["avatar"] = _proxy_media_url(info["avatar"])

            verified_uid = info["uid"]
            verified_uname = info["username"]
            free_q = int(getattr(config, "FREE_CAPTION_QUOTA", 5))

            if not is_vip:
                self._send_json(200, {
                    "ok": True,
                    "account": info,
                    "customer_captions": [],
                    "customer_frames": [],
                    "caption_quota": {
                        "free": free_q,
                        "extra": 0,
                        "total": free_q,
                        "used": 0,
                        "remaining": 0,
                    },
                })
                return

            # Lấy danh sách Caption cá nhân RIÊNG của chính khách hàng này từ https://locket.2707226.xyz
            customer_captions = []
            try:
                cap_res = api.ctv_get_captions(uid=verified_uid)
                if isinstance(cap_res, dict) and cap_res.get("ok"):
                    customer_captions = cap_res.get("captions", []) or []
            except Exception:
                try:
                    cap_res2 = api.ctv_get_captions(uid=verified_uname)
                    if isinstance(cap_res2, dict) and cap_res2.get("ok"):
                        customer_captions = cap_res2.get("captions", []) or []
                except Exception:
                    pass
            masked_captions = []
            for cp in customer_captions:
                if isinstance(cp, dict):
                    cpc = dict(cp)
                    if cpc.get("symbolPreviewUrl"):
                        cpc["symbolPreviewUrl"] = _proxy_media_url(cpc["symbolPreviewUrl"])
                    masked_captions.append(cpc)
                else:
                    masked_captions.append(cp)

            # Lấy danh sách Khung riêng của chính khách hàng từ CTV (ẩn tuyệt đối UID khách khác)
            customer_frames = []
            try:
                fr_res = api.ctv_get_frames()
                for fr in (fr_res.get("frames", []) or []):
                    if not isinstance(fr, dict) or not fr.get("active", True):
                        continue
                    raw_t = str(fr.get("targetUid") or "")
                    t_list = [x.strip() for x in raw_t.split(",") if x.strip()] + [
                        str(x).strip() for x in (fr.get("targetUids") or []) if str(x).strip()
                    ]
                    if verified_uid in t_list or verified_uname in t_list:
                        masked_u = _proxy_media_url(fr.get("url"))
                        customer_frames.append({
                            "id": fr.get("id"),
                            "name": fr.get("name") or "Khung Của Bạn",
                            "category": "Khung Cá Nhân Đã Nạp",
                            "group": "my_frames",
                            "image": masked_u,
                            "rawImage": masked_u,
                            "badge": "Đã Gán Tài Khoản",
                            "source": "customer_assigned",
                        })
            except Exception:
                pass

            q_info = db.get_caption_quota_info(verified_uid, verified_uname)
            used_cap = len(masked_captions)
            total_cap = int(q_info.get("total_quota", free_q))

            self._send_json(200, {
                "ok": True,
                "account": info,
                "customer_captions": masked_captions,
                "customer_frames": customer_frames,
                "caption_quota": {
                    "free": q_info.get("free_quota", free_q),
                    "extra": q_info.get("extra_quota", 0),
                    "total": total_cap,
                    "used": used_cap,
                    "remaining": max(0, total_cap - used_cap),
                },
            })
            return

        # 1.2 API Khách hàng VIP áp dụng Khung Widget trực tiếp lên tài khoản Locket của chính mình
        if path == "/api/features/apply_frame":
            raw_id = str(body.get("identifier", "") or body.get("username", "") or body.get("uid", "")).strip()
            frame_url = _resolve_frame_url(str(body.get("url", "")).strip())
            frame_name = str(body.get("name", "")).strip() or "Khung Widget VIP"
            if not raw_id or not frame_url:
                self._send_json(400, {"ok": False, "error": "Thiếu Username Locket hoặc ảnh khung viền!"})
                return
            if not frame_url.startswith("https://"):
                self._send_json(400, {"ok": False, "error": "Ảnh khung viền không hợp lệ, vui lòng tải lại file ảnh PNG/WEBP!"})
                return

            is_vip, info = self._verify_customer_locket_vip(raw_id)
            if "error" in info:
                self._send_json(400, {"ok": False, "error": info["error"]})
                return
            if isinstance(info, dict) and info.get("avatar"):
                info["avatar"] = _proxy_media_url(info["avatar"])
            if not is_vip:
                self._send_json(403, {
                    "ok": False,
                    "error": f"Tài khoản @{info['username']} chưa kích hoạt Locket Gold VIP tại cửa hàng! Vui lòng mua gói (chỉ từ 5.000đ) để nạp khung trực tiếp lên máy chủ.",
                })
                return

            verified_uid = info["uid"]
            try:
                res = api.ctv_save_frame(
                    url_img=frame_url,
                    name=frame_name,
                    target_uid=verified_uid,
                    target_uids=[verified_uid],
                    active=True,
                )
                self._send_json(200, {
                    "ok": True,
                    "message": f"Đã nạp khung '{frame_name}' cho tài khoản @{info['username']} thành công!",
                    "frame": res.get("frame"),
                })
            except Exception as e_af:
                self._send_json(400, {"ok": False, "error": str(e_af)})
            return

        # 1.3 API Khách hàng VIP lưu & gửi Caption SF Symbol lên tài khoản Locket của chính mình
        if path == "/api/features/save_caption":
            raw_id = str(body.get("identifier", "") or body.get("username", "") or body.get("uid", "")).strip()
            text_val = str(body.get("text", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng kết nối Username Locket trước khi lưu Caption!"})
                return
            if not text_val or len(text_val) > 100:
                self._send_json(400, {"ok": False, "error": "Nội dung Caption không được để trống và tối đa 100 ký tự!"})
                return

            is_vip, info = self._verify_customer_locket_vip(raw_id)
            if "error" in info:
                self._send_json(400, {"ok": False, "error": info["error"]})
                return
            if isinstance(info, dict) and info.get("avatar"):
                info["avatar"] = _proxy_media_url(info["avatar"])
            if not is_vip:
                self._send_json(403, {
                    "ok": False,
                    "error": f"Tài khoản @{info['username']} chưa kích hoạt Locket Gold VIP tại cửa hàng! Vui lòng nâng cấp gói (từ 5.000đ) để nạp Caption trực tiếp.",
                })
                return

            verified_uid = info["uid"]
            verified_uname = info["username"]
            icon_val = str(body.get("icon", "")).strip()
            icon_type = str(body.get("iconType", "symbol")).strip()
            symbol_name = str(body.get("symbolName", "") or icon_val).strip()
            colors = body.get("colors") if isinstance(body.get("colors"), list) else ["#FFB800", "#FF8008"]
            caption_id = str(body.get("caption_id") or body.get("id") or "").strip()

            try:
                caps_before = []
                try:
                    cb_res = api.ctv_get_captions(uid=verified_uid)
                    if isinstance(cb_res, dict) and cb_res.get("ok"):
                        caps_before = cb_res.get("captions", []) or []
                except Exception:
                    try:
                        cb_res2 = api.ctv_get_captions(uid=verified_uname)
                        if isinstance(cb_res2, dict) and cb_res2.get("ok"):
                            caps_before = cb_res2.get("captions", []) or []
                    except Exception:
                        caps_before = []

                q_info = db.get_caption_quota_info(verified_uid, verified_uname)
                total_cap = int(q_info.get("total_quota", 5))
                used_cap = len(caps_before)

                if caption_id:
                    if not any(str(c.get("id") or "") == caption_id for c in caps_before):
                        self._send_json(403, {"ok": False, "error": "Bạn chỉ được chỉnh sửa Caption thuộc tài khoản của chính mình!"})
                        return
                else:
                    if used_cap >= total_cap:
                        self._send_json(402, {
                            "ok": False,
                            "need_caption_topup": True,
                            "used_count": used_cap,
                            "total_quota": total_cap,
                            "error": f"Bạn đã dùng hết {used_cap}/{total_cap} Caption! Mua thêm gói +10 Caption (5.000đ) hoặc +30 Caption (10.000đ) để tạo thêm.",
                        })
                        return

                res = api.ctv_save_caption(
                    text=text_val,
                    uid=verified_uid,
                    icon=icon_val,
                    icon_type=icon_type,
                    symbol_name=symbol_name if icon_type == "symbol" else "",
                    colors=colors,
                    active=True,
                    caption_id=caption_id,
                )
                caps_now = caps_before
                try:
                    c_res = api.ctv_get_captions(uid=verified_uid)
                    caps_now = c_res.get("captions", []) or []
                except Exception:
                    pass
                used_after = len(caps_now)
                self._send_json(200, {
                    "ok": True,
                    "message": res.get("message") or f"Đã nạp Caption riêng lên tài khoản @{verified_uname}!",
                    "caption": res.get("caption"),
                    "customer_captions": caps_now,
                    "caption_quota": {
                        "free": q_info.get("free_quota", 5),
                        "extra": q_info.get("extra_quota", 0),
                        "total": total_cap,
                        "used": used_after,
                        "remaining": max(0, total_cap - used_after),
                    },
                })
            except Exception as e_sc:
                self._send_json(400, {"ok": False, "error": str(e_sc)})
            return

        # 1. API Kiểm tra tài khoản Locket / Spotify trước khi mua (TÁCH BIỆT NGHIÊM NGẶT)
        if path == "/api/check_account":
            service = body.get("service", "locket")
            raw_id = str(body.get("identifier", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập thông tin tài khoản!"})
                return

            try:
                if service == "spotify":
                    if not re.search(r"spotify\.com/user/[a-zA-Z0-9._-]+", raw_id, re.I):
                        self._send_json(400, {
                            "ok": False,
                            "error": "Phần Spotify chỉ nhận Link Profile Spotify (VD: https://open.spotify.com/user/...). Không điền Username chữ thông thường!"
                        })
                        return

                    cleaned_sp = utils.extract_spotify_uid(raw_id)
                    res = api.spotify_check(raw_id)
                    data = res.get("data") if isinstance(res.get("data"), dict) else res
                    uid = data.get("uid") or data.get("id") or cleaned_sp
                    display = data.get("displayName") or data.get("username") or data.get("name") or uid
                    avatar = data.get("avatar") or data.get("image") or data.get("avatarUrl")
                    plan = data.get("plan") or data.get("product") or "Free"
                    is_bound = data.get("isBound", False)

                    used_trial = bool(utils.has_used_test_trial("spotify", [uid, cleaned_sp, display, raw_id]))
                    self._send_json(200, {
                        "ok": True,
                        "service": "spotify",
                        "uid": uid,
                        "display_name": display,
                        "avatar": _proxy_media_url(avatar),
                        "plan": plan,
                        "is_bound": is_bound,
                        "used_test_trial": used_trial,
                        "status_text": "Đã kết nối IP thiết bị" if is_bound else "Chưa khóa IP (Sẵn sàng nâng cấp)"
                    })
                    return

                else:
                    # Gói Locket Gold / Combo (Dòng 1) / VIP All-in-One: CHỈ NHẬN USERNAME LOCKET, CHẶN MỌI ĐƯỜNG LINK
                    if re.search(r"(https?://|/|spotify\.com|locket\.cam)", raw_id, re.I):
                        self._send_json(400, {
                            "ok": False,
                            "error": "Phần Locket chỉ cho phép điền Username Locket (VD: conlaigii), tuyệt đối không được dán đường link!"
                        })
                        return

                    cleaned = utils.clean_input(raw_id)
                    if not cleaned or len(cleaned) < 2 or " " in cleaned:
                        self._send_json(400, {
                            "ok": False,
                            "error": "Username Locket không hợp lệ! Vui lòng chỉ điền đúng tên người dùng Locket (không khoảng trắng, không dán link)."
                        })
                        return

                    res = api.locket_resolve(cleaned)
                    data = res.get("data") if isinstance(res.get("data"), dict) else res
                    if not isinstance(data, dict) or (not data.get("uid") and not data.get("id") and not data.get("username")):
                        self._send_json(400, {
                            "ok": False,
                            "error": f"Không tìm thấy tài khoản Locket '@{cleaned}'! Vui lòng kiểm tra lại đúng Username trên app Locket."
                        })
                        return

                    locket_username = data.get("username") or cleaned
                    uid = data.get("uid") or data.get("id") or locket_username
                    display = locket_username
                    avatar = data.get("avatar") or data.get("avatarUrl")
                    used_trial = bool(utils.has_used_test_trial("locket", [uid, locket_username, cleaned]))

                    self._send_json(200, {
                        "ok": True,
                        "service": "locket",
                        "uid": uid,
                        "display_name": display,
                        "avatar": _proxy_media_url(avatar),
                        "used_test_trial": used_trial,
                    })
                    return
            except Exception as e:
                logger.warning(f"Error checking account: {e}")
                self._send_json(400, {"ok": False, "error": str(e)})
                return

        # 1.1 API Kiểm tra mã giảm giá
        if path == "/api/check_coupon":
            code = str(body.get("code", "")).strip().upper()
            product = str(body.get("product", "locket"))
            plan = str(body.get("plan", "ltm"))
            
            try:
                db.apply_custom_prices()
            except Exception:
                pass
            pv = config.PRODUCTS.get(product, {})
            plnv = pv.get("plans", {}).get(plan, {})
            orig_price = plnv.get("price", 160000)

            chk = utils.check_and_apply_coupon(code, orig_price)
            if chk.get("ok"):
                self._send_json(200, {
                    "ok": True,
                    "code": chk["code"],
                    "description": chk.get("desc", ""),
                    "discount_amount": chk["discount_amount"],
                    "original_price": orig_price,
                    "final_price": chk["final_price"]
                })
            else:
                self._send_json(400, {
                    "ok": False,
                    "error": chk.get("error", f"Mã giảm giá '{code}' không tồn tại hoặc đã hết hạn.")
                })
            return

        # 2. API Tạo đơn hàng Web & Sinh VietQR
        if path == "/api/create_order":
            try:
                product = body.get("product")
                plan = body.get("plan")
                raw_ident = str(body.get("identifier", "")).strip()
                if product == "spotify":
                    identifier = utils.extract_spotify_uid(raw_ident) or raw_ident
                else:
                    identifier = utils.clean_input(raw_ident) or raw_ident
                display_name = str(body.get("display_name", "")).strip() or identifier
                if "spotify.com/user/" in display_name.lower() or "locket.cam/" in display_name.lower():
                    display_name = identifier
                raw_sp = str(body.get("spotify_uid", "")).strip()
                spotify_uid = utils.extract_spotify_uid(raw_sp) if raw_sp else (identifier if product == "spotify" else "")
                avatar = body.get("avatar", "")
                token = body.get("token", "")

                if not product or not plan or not identifier:
                    self._send_json(400, {"ok": False, "error": "Thiếu thông tin gói hoặc tài khoản khách"})
                    return

                try:
                    db.apply_custom_prices()
                except Exception:
                    pass
                pv = config.PRODUCTS.get(product)
                if not pv or plan not in pv.get("plans", {}):
                    self._send_json(400, {"ok": False, "error": "Gói cước không hợp lệ"})
                    return

                plnv = pv["plans"][plan]
                price = plnv["price"]
                orig_price = price

                locket_uid_param = str(body.get("locket_uid") or "").strip()
                if plan == "test" or str(plnv.get("packageCode") or "").upper() in ("LKGT3D", "SPT"):
                    trial_cands = [raw_ident, identifier, display_name, spotify_uid, locket_uid_param]
                    if product == "locket" and not locket_uid_param:
                        try:
                            r_lk = api.locket_resolve(identifier)
                            r_dt = r_lk.get("data") if isinstance(r_lk, dict) and isinstance(r_lk.get("data"), dict) else (r_lk if isinstance(r_lk, dict) else {})
                            resolved_uid = str(r_dt.get("uid") or r_dt.get("id") or "").strip()
                            resolved_uname = str(r_dt.get("username") or "").strip()
                            if resolved_uid:
                                locket_uid_param = resolved_uid
                                trial_cands.append(resolved_uid)
                            if resolved_uname:
                                trial_cands.append(resolved_uname)
                        except Exception:
                            pass
                    if utils.has_used_test_trial(product, trial_cands):
                        self._send_json(403, {
                            "ok": False,
                            "used_test_trial": True,
                            "error": "⛔ Mỗi tài khoản chỉ được dùng thử gói Test 3 Ngày tối đa 1 lần! Tài khoản này đã thử trước đó, vui lòng chọn gói 6 Tháng, 1 Năm hoặc Vĩnh Viễn để tiếp tục."
                        })
                        return

                # Gói VIP ALL-IN-ONE (locket_ai) mặc định đã bao gồm sẵn bản quyền Studio (trọn bộ)
                has_studio = True if product == "locket_ai" else bool(body.get("has_studio", False))

                # Tính toán mã giảm giá trước (tránh lỗi UnboundLocalError khi tái sử dụng đơn cũ)
                coupon = str(body.get("discount_code", "") or body.get("coupon", "")).strip().upper()
                discount_amount = 0
                applied_code = ""

                if coupon:
                    chk = utils.check_and_apply_coupon(coupon, orig_price)
                    if chk.get("ok"):
                        discount_amount = chk["discount_amount"]
                        price = chk["final_price"]
                        applied_code = chk["code"]

                # Chống Spam Đơn Hàng (Anti-Spam Order Creation)
                clean_ident = utils.clean_input(identifier).lower()
                existing_orders = db.get_orders()
                pending_same_order = None
                pending_count_user = 0

                from order_service import payment_deadline
                for od in existing_orders.values():
                    deadline = payment_deadline(od)
                    if (od.get("status") in ("waiting_payment", "pending")
                            and deadline is not None and time.time() < deadline):
                        od_ident = str(od.get("uid", "")).lower()
                        if od_ident == clean_ident or od_ident == identifier.lower():
                            pending_count_user += 1
                            if (
                                od.get("product") == product and od.get("plan") == plan
                                and od.get("source") == "web"
                                and (od.get("spotify_uid") or "") == spotify_uid
                                and (od.get("discount_code") or "") == applied_code
                            ):
                                pending_same_order = od

                # Nếu tài khoản này đã tạo từ 5 đơn trở lên mà chưa thanh toán đơn nào -> Chặn spam
                if pending_count_user >= 5 and not pending_same_order:
                    self._send_json(429, {
                        "ok": False,
                        "error": "Bạn đang có nhiều đơn hàng chưa thanh toán! Vui lòng hoàn tất chuyển khoản đơn hàng trước đó hoặc chờ 5 phút."
                    })
                    return

                if pending_same_order:
                    p_id = pending_same_order["order_id"]
                    p_price = pending_same_order["price"]
                    qr_url = _get_masked_vietqr_url(amount=p_price, add_info=f"ORDER_{p_id}")
                    self._send_json(200, {
                        "ok": True,
                        "order_id": p_id,
                        "memo": f"ORDER_{p_id}",
                        "price": p_price,
                        "qr_url": qr_url,
                        "bank_id": getattr(config, "BANK_ID", "TPB"),
                        "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                        "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                        "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                        "product": product,
                        "plan": plan,
                        "product_name": pv["name"],
                        "plan_label": plnv["label"],
                        "is_reused": True,
                        "expires_at_ms": int(payment_deadline(pending_same_order) * 1000)
                    })
                    return

                order_id = utils.gen_order_id()
                # Không trừ used_count lúc tạo đơn để tránh spam đốt hết mã giảm giá;
                # chỉ trừ trong order_service khi đơn thanh toán & kích hoạt thành công.

                # Lưu vào Database dùng chung với Bot Telegram
                extra_fields = {
                    "source": "web",
                    "avatar": avatar,
                    "token": token,
                    "account_target": identifier,  # Luôn lưu UID thực tế, không dùng display_name
                    "locket_uid": locket_uid_param,
                    "spotify_uid": spotify_uid,
                    "discount_code": applied_code,
                    "discount_amount": discount_amount,
                    "original_price": orig_price,
                    "has_studio": has_studio,
                }

                order = db.create_order(
                    order_id=order_id,
                    user_id=0,
                    username=f"web_{identifier[:15]}",
                    product=product,
                    plan=plan,
                    price=price,
                    uid=identifier,
                    display_name=display_name,
                    **extra_fields
                )

                # Sinh link VietQR chuẩn (ẩn domain qua proxy nội bộ)
                qr_url = _get_masked_vietqr_url(amount=price, add_info=f"ORDER_{order_id}")

                # Gửi thông báo đến Admin qua Telegram Bot (siêu tốc <0.2s, đa kênh)
                dispatch_admin_order_alert(order_id, pv, plnv, display_name, identifier, price, orig_price, applied_code, discount_amount)

                self._send_json(200, {
                    "ok": True,
                    "order_id": order_id,
                    "memo": f"ORDER_{order_id}",
                    "price": price,
                    "qr_url": qr_url,
                    "bank_id": getattr(config, "BANK_ID", "TPB"),
                    "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                    "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                    "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                    "product": product,
                    "plan": plan,
                    "product_name": pv["name"],
                    "plan_label": plnv["label"],
                    "expires_at_ms": int(payment_deadline(order) * 1000),
                })
                return
            except Exception as e_create:
                logger.error(f"Error in /api/create_order: {e_create}", exc_info=True)
                self._send_json(500, {"ok": False, "error": f"Lỗi tạo đơn hàng: {e_create}"})
                return

        # 2.1 API Tạo đơn phụ nâng cấp Studio Chú Thích & Khung Viền (+10.000đ)
        if path == "/api/create_studio_order":
            parent_order_id = str(body.get("parent_order_id", "") or body.get("order_id", "")).strip()
            identifier = str(body.get("identifier", "") or body.get("username", "") or body.get("uid", "")).strip()
            display_name = str(body.get("display_name", "")).strip() or identifier
            p_ord = db.get_order(parent_order_id) if parent_order_id else None
            if not identifier and p_ord:
                identifier = p_ord.get("display_name") or p_ord.get("uid") or p_ord.get("username")
                display_name = identifier

            if not identifier:
                self._send_json(400, {"ok": False, "error": "Thiếu tài khoản Locket cần mở Studio"})
                return

            has_parent_done = bool(p_ord and p_ord.get("status") == "done")
            is_vip, info = self._verify_customer_locket_vip(identifier)
            if not is_vip and not has_parent_done:
                self._send_json(403, {"ok": False, "error": "Tài khoản chưa mua gói Locket Gold VIP hợp lệ tại shop!"})
                return

            from order_service import payment_deadline
            clean_ident = utils.clean_input(identifier).lower().lstrip("@")
            pending_count_user = 0
            for od in db.get_orders().values():
                deadline = payment_deadline(od)
                if od.get("status") in ("waiting_payment", "pending") and deadline is not None and time.time() < deadline:
                    if clean_ident in (str(od.get("uid", "")).lower().lstrip("@"), str(od.get("account_target", "")).lower().lstrip("@")):
                        pending_count_user += 1
            if pending_count_user >= 5:
                self._send_json(429, {"ok": False, "error": "Bạn đang có quá nhiều đơn chưa thanh toán. Vui lòng hoàn tất đơn cũ hoặc chờ 5 phút."})
                return

            sub_order_id = utils.gen_order_id()
            studio_price = getattr(config, "STUDIO_CAPTION_PRICE", 10000)

            order = db.create_order(
                order_id=sub_order_id,
                user_id=0,
                username=f"web_{clean_ident[:15]}",
                product="studio_caption",
                plan="extra",
                price=studio_price,
                uid=identifier,
                display_name=display_name,
                account_target=identifier,
                parent_order_id=parent_order_id,
                source="web",
                status="waiting_payment"
            )
            dispatch_admin_order_alert(
                sub_order_id,
                {"name": "Studio Chú Thích & Khung Viền"},
                {"label": "Gói Studio"},
                display_name,
                identifier,
                studio_price,
                studio_price,
            )

            qr_url = _get_masked_vietqr_url(amount=studio_price, add_info=f"ORDER_{sub_order_id}")
            self._send_json(200, {
                "ok": True,
                "order_id": sub_order_id,
                "memo": f"ORDER_{sub_order_id}",
                "price": studio_price,
                "qr_url": qr_url,
                "bank_id": getattr(config, "BANK_ID", "TPB"),
                "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                "product": "studio_caption",
                "product_name": "Studio Chỉnh Chú Thích & Khung Viền",
                "plan_label": "Gói Studio",
                "expires_at_ms": int(payment_deadline(order) * 1000)
            })
            return

        # 2.2 API Tạo đơn Nạp Lượt Filter AI cho người dùng cuối (20: 7.000đ, 50: 17.000đ, 100: 33.000đ)
        if path == "/api/create_filter_order":
            pack = str(body.get("pack") or body.get("plan") or "").strip()
            raw_ident = str(body.get("identifier") or body.get("username") or body.get("uid") or "").strip()
            packs_map = getattr(config, "FILTER_TOPUP_PACKS", {})
            pack_cfg = packs_map.get(pack)
            if not pack_cfg:
                self._send_json(400, {"ok": False, "error": "Gói lượt Filter AI không hợp lệ (hỗ trợ 20, 50 hoặc 100 lượt)."})
                return
            if not raw_ident:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username Locket của bạn!"})
                return
            if re.search(r"(https?://|/|spotify\.com|locket\.cam)", raw_ident, re.I):
                self._send_json(400, {"ok": False, "error": "Chỉ điền Username Locket (ví dụ: AloPremiumShop), không dán đường link!"})
                return

            cleaned = utils.clean_input(raw_ident).lstrip("@")
            if not cleaned or len(cleaned) < 2 or " " in cleaned:
                self._send_json(400, {"ok": False, "error": "Username Locket không hợp lệ! Vui lòng kiểm tra lại."})
                return

            is_vip, info = self._verify_customer_locket_vip(cleaned)
            if "error" in info:
                self._send_json(400, {"ok": False, "error": info["error"]})
                return
            if not is_vip:
                self._send_json(403, {
                    "ok": False,
                    "error": f"Tài khoản @{info['username']} chưa mua gói VIP tại cửa hàng! Vui lòng mua gói Locket Gold VIP (từ 5.000đ) trước khi dùng Tính Năng VIP.",
                })
                return
            locket_username = str(info.get("username") or cleaned).lstrip("@")
            locket_uid = str(info.get("uid") or locket_username)
            avatar = info.get("avatar") or ""

            from order_service import payment_deadline
            clean_ident = locket_username.lower()
            existing_orders = db.get_orders()
            pending_same_order = None
            pending_count_user = 0
            for od in existing_orders.values():
                deadline = payment_deadline(od)
                if (od.get("status") in ("waiting_payment", "pending")
                        and deadline is not None and time.time() < deadline):
                    od_ident = str(od.get("uid", "")).lower().lstrip("@")
                    od_target = str(od.get("account_target", "")).lower().lstrip("@")
                    if clean_ident in (od_ident, od_target):
                        pending_count_user += 1
                        if od.get("product") == "filter_topup" and od.get("plan") == pack and od.get("source") == "web":
                            pending_same_order = od

            if pending_count_user >= 5 and not pending_same_order:
                self._send_json(429, {
                    "ok": False,
                    "error": "Bạn đang có nhiều đơn hàng chưa thanh toán! Vui lòng hoàn tất chuyển khoản đơn trước đó hoặc chờ 5 phút."
                })
                return

            price = int(pack_cfg["price"])
            if pending_same_order:
                p_id = pending_same_order["order_id"]
                p_price = pending_same_order["price"]
                qr_url = _get_masked_vietqr_url(amount=p_price, add_info=f"ORDER_{p_id}")
                self._send_json(200, {
                    "ok": True,
                    "order_id": p_id,
                    "memo": f"ORDER_{p_id}",
                    "price": p_price,
                    "qr_url": qr_url,
                    "bank_id": getattr(config, "BANK_ID", "TPB"),
                    "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                    "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                    "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                    "product": "filter_topup",
                    "plan": pack,
                    "product_name": "Nạp Lượt Filter AI",
                    "plan_label": pack_cfg["label"],
                    "display_name": locket_username,
                    "is_reused": True,
                    "expires_at_ms": int(payment_deadline(pending_same_order) * 1000)
                })
                return

            sub_order_id = utils.gen_order_id()
            order = db.create_order(
                order_id=sub_order_id,
                user_id=0,
                username=f"web_{locket_username[:15]}",
                product="filter_topup",
                plan=pack,
                plan_label=pack_cfg["label"],
                price=price,
                uid=locket_username,
                display_name=locket_username,
                account_target=locket_username,
                locket_uid=locket_uid,
                filter_turns=pack_cfg["turns"],
                avatar=avatar,
                source="web",
                status="waiting_payment"
            )
            dispatch_admin_order_alert(
                sub_order_id,
                {"name": "Nạp Lượt Filter AI"},
                {"label": pack_cfg["label"]},
                locket_username,
                locket_username,
                price,
                price
            )
            qr_url = _get_masked_vietqr_url(amount=price, add_info=f"ORDER_{sub_order_id}")
            self._send_json(200, {
                "ok": True,
                "order_id": sub_order_id,
                "memo": f"ORDER_{sub_order_id}",
                "price": price,
                "qr_url": qr_url,
                "bank_id": getattr(config, "BANK_ID", "TPB"),
                "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                "product": "filter_topup",
                "plan": pack,
                "product_name": "Nạp Lượt Filter AI",
                "plan_label": pack_cfg["label"],
                "display_name": locket_username,
                "expires_at_ms": int(payment_deadline(order) * 1000)
            })
            return

        # 2.3 API Tạo đơn Mua Thêm Gói Caption VIP (+10 Caption: 5.000đ, +30 Caption: 10.000đ)
        if path == "/api/create_caption_order":
            pack = str(body.get("pack") or body.get("plan") or "").strip()
            raw_ident = str(body.get("identifier") or body.get("username") or body.get("uid") or "").strip()
            packs_map = getattr(config, "CAPTION_TOPUP_PACKS", {})
            pack_cfg = packs_map.get(pack)
            if not pack_cfg:
                self._send_json(400, {"ok": False, "error": "Gói mua thêm Caption không hợp lệ (chọn 10 hoặc 30 caption)."})
                return
            if not raw_ident:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập và kết nối Username Locket VIP trước!"})
                return
            if re.search(r"(https?://|/|spotify\.com|locket\.cam)", raw_ident, re.I):
                self._send_json(400, {"ok": False, "error": "Chỉ điền Username Locket, không dán đường link!"})
                return

            is_vip, info = self._verify_customer_locket_vip(raw_ident)
            if "error" in info:
                self._send_json(400, {"ok": False, "error": info["error"]})
                return
            if not is_vip:
                self._send_json(403, {
                    "ok": False,
                    "error": f"Tài khoản @{info['username']} chưa kích hoạt gói Locket Gold VIP tại cửa hàng! Vui lòng mua gói VIP trước.",
                })
                return

            locket_username = str(info.get("username") or raw_ident).lstrip("@")
            locket_uid = str(info.get("uid") or locket_username)
            avatar = info.get("avatar") or ""

            from order_service import payment_deadline
            clean_ident = locket_username.lower()
            existing_orders = db.get_orders()
            pending_same_order = None
            pending_count_user = 0
            for od in existing_orders.values():
                deadline = payment_deadline(od)
                if (od.get("status") in ("waiting_payment", "pending")
                        and deadline is not None and time.time() < deadline):
                    od_ident = str(od.get("uid", "")).lower().lstrip("@")
                    od_target = str(od.get("account_target", "")).lower().lstrip("@")
                    if clean_ident in (od_ident, od_target):
                        pending_count_user += 1
                        if od.get("product") == "caption_pack" and od.get("plan") == pack and od.get("source") == "web":
                            pending_same_order = od

            if pending_count_user >= 5 and not pending_same_order:
                self._send_json(429, {
                    "ok": False,
                    "error": "Bạn đang có nhiều đơn hàng chưa thanh toán! Vui lòng hoàn tất đơn trước hoặc chờ 5 phút."
                })
                return

            price = int(pack_cfg["price"])
            if pending_same_order:
                p_id = pending_same_order["order_id"]
                p_price = pending_same_order["price"]
                qr_url = _get_masked_vietqr_url(amount=p_price, add_info=f"ORDER_{p_id}")
                self._send_json(200, {
                    "ok": True,
                    "order_id": p_id,
                    "memo": f"ORDER_{p_id}",
                    "price": p_price,
                    "qr_url": qr_url,
                    "bank_id": getattr(config, "BANK_ID", "TPB"),
                    "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                    "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                    "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                    "product": "caption_pack",
                    "plan": pack,
                    "product_name": "Mua Thêm Caption VIP",
                    "plan_label": pack_cfg["label"],
                    "display_name": locket_username,
                    "is_reused": True,
                    "expires_at_ms": int(payment_deadline(pending_same_order) * 1000)
                })
                return

            cap_order_id = utils.gen_order_id()
            order = db.create_order(
                order_id=cap_order_id,
                user_id=0,
                username=f"web_{locket_username[:15]}",
                product="caption_pack",
                plan=pack,
                plan_label=pack_cfg["label"],
                price=price,
                uid=locket_username,
                display_name=locket_username,
                account_target=locket_username,
                locket_uid=locket_uid,
                caption_amount=pack_cfg["captions"],
                avatar=avatar,
                source="web",
                status="waiting_payment"
            )
            dispatch_admin_order_alert(
                cap_order_id,
                {"name": "Mua Thêm Caption VIP"},
                {"label": pack_cfg["label"]},
                locket_username,
                locket_username,
                price,
                price
            )
            qr_url = _get_masked_vietqr_url(amount=price, add_info=f"ORDER_{cap_order_id}")
            self._send_json(200, {
                "ok": True,
                "order_id": cap_order_id,
                "memo": f"ORDER_{cap_order_id}",
                "price": price,
                "qr_url": qr_url,
                "bank_id": getattr(config, "BANK_ID", "TPB"),
                "bank_name": getattr(config, "BANK_NAME", "TPBank"),
                "bank_account": getattr(config, "ACCOUNT_NO", "34528022007"),
                "account_holder": getattr(config, "ACCOUNT_NAME", "NGUYEN NHU QUYNH"),
                "product": "caption_pack",
                "plan": pack,
                "product_name": "Mua Thêm Caption VIP",
                "plan_label": pack_cfg["label"],
                "display_name": locket_username,
                "expires_at_ms": int(payment_deadline(order) * 1000)
            })
            return

        # 3. API Reset thiết bị Spotify (BẮT BUỘC ĐÃ TỪNG MUA GÓI HỢP LỆ)
        if path == "/api/reset_spotify":
            raw_sp = str(body.get("uid", "")).strip()
            if not raw_sp:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập UID hoặc Link Profile Spotify cần reset"})
                return
            sp_uid = utils.extract_spotify_uid(raw_sp) or raw_sp
            sp_clean = sp_uid.lower().strip()
            raw_clean = raw_sp.lower().strip()
            has_paid_sp = False
            for od in db.get_orders().values():
                if od.get("status") == "done" and od.get("product") in ("spotify", "combo", "locket_spotify", "locket_ai"):
                    cands = {
                        str(od.get("uid", "")).lower().strip(),
                        str(od.get("spotify_uid", "")).lower().strip(),
                        str(od.get("identifier", "")).lower().strip(),
                        str(od.get("account_target", "")).lower().strip(),
                        str(od.get("display_name", "")).lower().strip(),
                    }
                    if sp_clean in cands or raw_clean in cands:
                        has_paid_sp = True
                        break
            if not has_paid_sp:
                try:
                    sp_chk = api.check_uid_details(sp_uid, "spotify")
                    dt = sp_chk.get("data", {}) if isinstance(sp_chk, dict) else {}
                    if (dt.get("active") is True or dt.get("status") == "ACTIVE") and (dt.get("isMine") is True):
                        has_paid_sp = True
                except Exception:
                    pass
            if not has_paid_sp:
                self._send_json(403, {
                    "ok": False,
                    "error": "Tài khoản Spotify này chưa từng mua gói Spotify Premium tại cửa hàng hoặc chưa kích hoạt!"
                })
                return
            try:
                res = api.spotify_reset(sp_uid)
                self._send_json(200, {
                    "ok": True,
                    "message": "Reset phiên IP thiết bị Spotify thành công! Bạn có thể kết nối ngay trên thiết bị mới."
                })
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
            return

        # 3.1. API Reset / Đổi máy Locket Gold (BẢO MẬT: BẮT BUỘC ĐÃ TỪNG MUA GÓI BẢN QUYỀN)
        if path == "/api/reset_locket":
            raw_id = str(body.get("username", "") or body.get("identifier", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username hoặc Link Locket cần chuyển máy"})
                return
            cleaned = utils.clean_input(raw_id)
            cleaned_l = cleaned.lower().lstrip("@")
            try:
                # Kiểm tra tài khoản này đã từng mua gói bản quyền Locket hợp lệ chưa (gồm cả locket_spotify)
                has_paid_order = False
                for od in db.get_orders().values():
                    if od.get("product") in ("locket", "combo", "locket_spotify", "locket_ai") and od.get("status") == "done":
                        cands = {
                            str(od.get("identifier", "")).lower().lstrip("@"),
                            str(od.get("uid", "")).lower().lstrip("@"),
                            str(od.get("display_name", "")).lower().lstrip("@"),
                            str(od.get("account_target", "")).lower().lstrip("@"),
                            str(od.get("locket_username", "")).lower().lstrip("@"),
                        }
                        if cleaned_l in cands:
                            has_paid_order = True
                            break

                if not has_paid_order:
                    is_vip, _ = self._verify_customer_locket_vip(cleaned)
                    has_paid_order = bool(is_vip)

                if not has_paid_order:
                    self._send_json(403, {
                        "ok": False,
                        "error": f"Tài khoản '{cleaned}' chưa từng mua gói Locket Gold VIP tại cửa hàng hoặc chưa thanh toán! Vui lòng đặt mua gói trước khi đổi máy."
                    })
                    return

                display_name = cleaned
                uid = cleaned
                try:
                    res = api.locket_resolve(cleaned)
                    data = res.get("data") if isinstance(res.get("data"), dict) else res
                    uid = data.get("uid") or data.get("id") or cleaned
                    display_name = data.get("displayName") or data.get("username") or cleaned
                except Exception:
                    pass

                download_url = f"/api/download_profile?username={urllib.parse.quote(cleaned)}"
                self._send_json(200, {
                    "ok": True,
                    "service": "locket",
                    "uid": uid,
                    "display_name": display_name,
                    "download_url": download_url,
                    "message": f"Tài khoản Locket: {display_name} đã sẵn sàng cài đặt sang iPhone mới!"
                })
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
            return

        # 4. Webhook SePay (Bảo mật 5 lớp tuyệt đối: Xác thực 2 chiều với API Ngân hàng SePay)
        if path in ("/sepay/webhook", "/api/sepay/webhook"):
            client_ip = self.client_address[0] if hasattr(self, 'client_address') else 'unknown'
            auth_header = self.headers.get("Authorization", "")
            expected_token = getattr(config, "SEPAY_API_TOKEN", "").strip()

            # Lớp 1: Bắt buộc xác thực bí mật SePay API Token trong Header Authorization
            accepted_headers = (f"Apikey {expected_token}", f"Bearer {expected_token}", expected_token)
            if not expected_token or not any(
                hmac.compare_digest(auth_header.encode(), value.encode()) for value in accepted_headers
            ):
                logger.warning(f"🚨 [CẢNH BÁO BẢO MẬT] Phát hiện request giả mạo webhook SePay từ IP: {client_ip}!")
                self._send_json(401, {"ok": False, "error": "Unauthorized: Invalid SePay authentication token"})
                return

            # Lớp 2: Kiểm tra số tài khoản nhận tiền phải là tài khoản chính chủ của shop
            account_num = str(body.get("accountNumber", "")).strip()
            shop_acc = str(getattr(config, "ACCOUNT_NO", "34528022007")).strip()
            if account_num and shop_acc and account_num != shop_acc:
                logger.warning(f"🚨 Webhook SePay sai tài khoản nhận tiền: {account_num} != {shop_acc}")
                self._send_json(400, {"ok": False, "error": "Invalid recipient account"})
                return

            # Lớp 3: Chiều giao dịch phải là tiền vào ('in')
            transfer_type = str(body.get("transferType", "in")).lower()
            if transfer_type != "in":
                self._send_json(200, {"success": True, "message": "Ignored outgoing transfer"})
                return

            from order_service import payment_matches_order, register_verified_payment, process_registered_payment
            tx_id = str(body.get("id", "")).strip()
            if not tx_id or not tx_id.isascii() or not tx_id.isdecimal():
                self._send_json(400, {"ok": False, "error": "Invalid transaction ID"})
                return
            if db.is_tx_used(tx_id):
                db.recover_order_payments()
                self._send_json(200, {"success": True, "message": "Transaction already recorded"})
                return
            try:
                amount_in = float(body.get("transferAmount") or 0)
            except (ValueError, TypeError):
                self._send_json(400, {"ok": False, "error": "Invalid transfer amount"})
                return

            matches = [
                order for order in db.get_orders().values()
                if order and order.get("status") in (*db.UNPAID_ORDER_STATUSES, "cancelled", "rejected")
                and payment_matches_order(order, account_num, str(body.get("content", "")), amount_in)
            ]
            if len(matches) != 1:
                self._send_json(200, {"success": True, "message": "No unique matching order"})
                return
            matched_order = matches[0]
            matched_order_id = matched_order["order_id"]

            # Lớp 5: XÁC THỰC 2 CHIỀU ĐỘC LẬP VỚI SEPAY API SERVER
            # Gọi trực tiếp SePay API để kiểm tra xem TPBank thực sự có tiền về hay không!
            try:
                v_url = f"https://my.sepay.vn/userapi/transactions/details/{tx_id}"
                v_req = urllib.request.Request(
                    v_url,
                    headers={"Authorization": f"Bearer {expected_token}", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(v_req, timeout=8) as v_res:
                    if v_res.status == 200:
                        v_json = json.loads(v_res.read().decode("utf-8"))
                        real_tx = v_json.get("transaction") or {}
                        real_acc = str(real_tx.get("account_number", "")).strip()
                        real_amount = float(real_tx.get("amount_in", 0) or 0)
                        real_content = str(real_tx.get("transaction_content", "")).upper()

                        if not payment_matches_order(matched_order, real_acc, real_content, real_amount):
                            self._send_json(403, {"ok": False, "error": "Verification failed: Bank data mismatch"})
                            return
                    else:
                        logger.error(f"🚨 Giao dịch {tx_id} không tìm thấy trên SePay API (Status {v_res.status})")
                        self._send_json(403, {"ok": False, "error": "Transaction not verified by SePay API"})
                        return
            except Exception as e_verify:
                logger.error(f"🚨 Lỗi gọi SePay API verify: {e_verify}. Chặn kích hoạt để bảo vệ shop!")
                self._send_json(503, {"ok": False, "error": "Could not verify payment with SePay"})
                return

            action = register_verified_payment(matched_order, tx_id, real_amount)
            if action:
                processing = process_registered_payment(BOT_INSTANCE, matched_order_id, action)
                if BOT_LOOP and BOT_LOOP.is_running():
                    asyncio.run_coroutine_threadsafe(processing, BOT_LOOP)
                else:
                    asyncio.run(processing)
            self._send_json(200, {"success": True, "message": "Payment checked"})
            return

        self._send_json(404, {"ok": False, "error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Giữ log sạch sẽ, che PIN/token khỏi URL query string nếu có
        msg = format % args
        if "GET /health" not in msg and "HEAD" not in msg and "GET /ping" not in msg:
            msg_safe = re.sub(r"([?&](?:pin|token|apikey|secret)=)[^&\s\"]+", r"\1***", msg, flags=re.I)
            logger.info(f"HTTP: {msg_safe}")


def start_web_server(bot=None, loop=None, port=None):
    set_bot_context(bot, loop)
    if port is None:
        port = int(os.environ.get("PORT", 8080))
    server = ThreadedHTTPServer(("0.0.0.0", port), WebAppHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"🌐 Web App & API Server đã khởi động thành công trên cổng {port}!")
    try:
        from order_service import sync_upstream_orders
        threading.Thread(target=sync_upstream_orders, daemon=True).start()
    except Exception as e_sync:
        logger.warning(f"Initial upstream sync failed: {e_sync}")
    # Nếu chạy web server độc lập không qua bot.py, tự khởi chạy luồng SePay autobank dự phòng
    if bot is None and getattr(config, "SEPAY_API_TOKEN", ""):
        def _standalone_sepay_worker():
            from order_service import check_sepay_payments, cancel_expired_pending_orders
            cnt = 0
            while True:
                try:
                    asyncio.run(check_sepay_payments(BOT_INSTANCE))
                    cnt += 1
                    if cnt >= 5:
                        cnt = 0
                        cancel_expired_pending_orders()
                except Exception as e_sp:
                    logger.warning(f"Standalone SePay worker error: {e_sp}")
                time.sleep(4)
        threading.Thread(target=_standalone_sepay_worker, daemon=True).start()
        logger.info("⚡ Đã khởi chạy SePay autobank worker dự phòng trên Web Server.")
    return server


if __name__ == "__main__":
    import time
    port = int(os.environ.get("PORT", 8080))
    srv = start_web_server(port=port)
    print(f"\n=======================================================")
    print(f"🚀 Web Server đang chạy tại: http://localhost:{port}")
    print(f"Nhấn Ctrl + C để dừng server.")
    print(f"=======================================================\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nĐang tắt Web Server...")
        srv.shutdown()


