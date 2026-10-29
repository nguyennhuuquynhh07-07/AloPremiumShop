"""
web_server.py – Máy chủ Web & API Cổng Thanh Toán VIP 3-in-1
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
import logging
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
import urllib.parse

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
from collections import defaultdict

_IP_REQUESTS = defaultdict(list)
_IP_BANNED = {}

def check_ip_rate_limit(ip: str, max_requests: int = 60, window_secs: int = 60) -> tuple[bool, str]:
    now = time.time()
    if ip in _IP_BANNED:
        remaining = int(_IP_BANNED[ip] - now)
        if remaining > 0:
            return False, f"IP bị tạm khóa do gửi yêu cầu quá nhanh. Vui lòng thử lại sau {remaining} giây."
        else:
            del _IP_BANNED[ip]

    timestamps = [t for t in _IP_REQUESTS[ip] if now - t < window_secs]
    timestamps.append(now)
    _IP_REQUESTS[ip] = timestamps
    if len(timestamps) > max_requests:
        _IP_BANNED[ip] = now + 900
        return False, "Tần suất yêu cầu bất thường. IP của bạn đã bị tạm khóa 15 phút để đảm bảo an toàn."

    return True, ""

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_data = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_data)
        except Exception as e:
            logger.warning(f"Failed to parse JSON body: {e}")
            return {}

    def do_HEAD(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        client_ip = self._get_client_ip()

        # Kiểm tra Rate Limit (ngoại trừ ping keep-alive và ảnh)
        if not path.startswith(("/health", "/ping")) and not path.endswith((".png", ".jpg", ".jpeg", ".ico", ".svg")):
            allowed, reason = check_ip_rate_limit(client_ip, max_requests=60, window_secs=60)
            if not allowed:
                self._send_json(429, {"ok": False, "error": reason})
                return

        # 1. Health check & Render keep-alive
        if path in ("/health", "/ping"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b"Bot Locket Gold + Spotify is running 24/7!")
            return

        # 1.1 Phục vụ Static Images & Logo trang web
        if path.endswith((".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp")) and ".." not in path:
            file_name = os.path.basename(path)
            if file_name == "favicon.ico":
                file_name = "favicon.png"
            file_path = os.path.join(os.path.dirname(__file__), file_name)
            if os.path.exists(file_path):
                ext = file_name.rsplit(".", 1)[-1].lower()
                mime = "image/x-icon" if ext == "ico" else f"image/{ext}" if ext != "svg" else "image/svg+xml"
                with open(file_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
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

        # 3. API Danh sách gói cước & bảng giá
        if path == "/api/packages":
            self._send_json(200, {
                "ok": True,
                "products": config.PRODUCTS
            })
            return

        # 4. API Tra cứu trạng thái đơn hàng (Polling từ Web)
        if path == "/api/order_status":
            order_id = params.get("order_id", [""])[0].strip()
            if not order_id:
                self._send_json(400, {"ok": False, "error": "Thiếu mã đơn hàng order_id"})
                return
            order = db.get_order(order_id)
            if not order:
                self._send_json(404, {"ok": False, "error": "Không tìm thấy đơn hàng"})
                return
            
            is_done = order.get("status") == "done"
            download_url = f"/api/download_profile?order_id={order_id}" if is_done else None
            self._send_json(200, {
                "ok": True,
                "order_id": order_id,
                "status": order.get("status", "waiting_payment"),
                "is_paid": is_done,
                "product": order.get("product"),
                "plan": order.get("plan"),
                "price": order.get("price"),
                "uid": order.get("uid"),
                "display_name": order.get("display_name"),
                "download_url": download_url,
                "created_at": order.get("created_at"),
            })
            return

        # 5. API Tải file .mobileconfig trực tiếp vào Cài đặt iOS Safari (CHỈ CHO ĐƠN ĐÃ THANH TOÁN)
        if path == "/api/download_profile" or path.endswith(".mobileconfig"):
            order_id = params.get("order_id", [""])[0].strip()
            username = params.get("username", [""])[0].strip() or params.get("uid", [""])[0].strip()

            order = db.get_order(order_id) if order_id else None
            if not order and username:
                clean_u = utils.clean_input(username).lower()
                for od in db.get_orders().values():
                    if od.get("status") == "done":
                        if str(od.get("identifier", "")).lower() == clean_u or str(od.get("uid", "")).lower() == clean_u or str(od.get("display_name", "")).lower() == clean_u:
                            order = od
                            break

            if not order and not username and not order_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng cung cấp order_id hoặc username"})
                return

            product_key = order.get("product", "locket") if order else "locket"
            safe_name = (order.get("display_name") if order else None) or (order.get("uid") if order else None) or username or "VIP"
            clean_token = (order.get("token") if order else None) or (order.get("uid") if order else None) or "vip"

            pv = config.PRODUCTS.get(product_key, {})
            svc_name = pv.get("name", "Locket Gold VIP")
            dns_link = (order.get("dns_link") if order else None) or f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
            bio = utils.generate_mobileconfig(
                service_name=svc_name,
                display_name=safe_name,
                dns_link=dns_link
            )
            xml_str = bio.getvalue().decode("utf-8")

            payload_bytes = xml_str.encode("utf-8")
            file_name = f"{product_key.capitalize()}_{safe_name}.mobileconfig"

            self.send_response(200)
            self.send_header("Content-Type", "application/x-apple-aspen-config; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
            self.send_header("Content-Length", str(len(payload_bytes)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(payload_bytes)
            return

        # 6. API Tra cứu đơn hàng bảo mật (Khớp chính xác Order ID hoặc UID >= 6 ký tự)
        if path == "/api/lookup":
            q = params.get("q", [""])[0].strip()
            if len(q) < 6:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập chính xác Mã đơn hàng hoặc UID (tối thiểu 6 ký tự)"})
                return

            orders = db.get_orders()
            results = []
            q_lower = q.lower()
            for oid, od in orders.items():
                # Chỉ cho phép khớp chính xác Mã đơn hàng hoặc UID, không quét bừa
                if oid.lower() == q_lower or str(od.get("uid", "")).lower() == q_lower:
                    results.append({
                        "order_id": oid,
                        "product": od.get("product"),
                        "plan": od.get("plan"),
                        "price": od.get("price"),
                        "status": od.get("status"),
                        "uid": od.get("uid"),
                        "display_name": od.get("display_name"),
                        "created_at": od.get("created_at"),
                        "download_url": f"/api/download_profile?order_id={oid}" if od.get("status") == "done" else None
                    })
            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            self._send_json(200, {"ok": True, "orders": results[:5]})
            return

        # API Tạo Mã QR Code động định dạng PNG từ link tải / dữ liệu bất kỳ
        if path == "/api/qr":
            raw_data = params.get("data", [""])[0].strip()
            if not raw_data:
                self._send_json(400, {"ok": False, "error": "Thiếu tham số data"})
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
                with open(admin_path, "rb") as f:
                    html_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            else:
                self._send_json(404, {"ok": False, "error": "admin.html not found"})
                return

        # API Admin: Lấy thông tin đồng bộ API CTV & Gói cước
        if path == "/api/admin/api_info":
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return
            try:
                acc = api.get_account_info().get("data", {})
            except Exception as e:
                acc = {"error": str(e), "balanceCoin": 0}

            try:
                pkgs = api.get_packages("all").get("data", [])
            except Exception as e:
                pkgs = []

            codes = list(db.get_codes().values())
            self._send_json(200, {
                "ok": True,
                "account": acc,
                "packages": pkgs,
                "codes": codes,
                "api_base_url": config.API_BASE_URL,
            })
            return

        # API Admin: Lấy danh sách mã giảm giá
        if path == "/api/admin/codes":
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return
            codes = list(db.get_codes().values())
            self._send_json(200, {"ok": True, "codes": codes})
            return

        # 7. Phục vụ Trang chủ Web App (index.html)
        if path in ("/", "/index.html"):
            index_path = os.path.join(os.path.dirname(__file__), "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    html_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"PremiumStore VIP Web Storefront is ready.")
                return

        # Mặc định 404
        self._send_json(404, {"ok": False, "error": "Endpoint not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()
        client_ip = self._get_client_ip()

        # Kiểm tra Rate Limit cho các API POST
        allowed, reason = check_ip_rate_limit(client_ip, max_requests=40, window_secs=60)
        if not allowed:
            self._send_json(429, {"ok": False, "error": reason})
            return

        # API Admin: Đăng nhập mã PIN
        if path == "/api/admin/login":
            pin = str(body.get("pin", "")).strip()
            admin_pin = getattr(config, "ADMIN_PIN", "2802")
            if pin == admin_pin:
                self._send_json(200, {"ok": True})
            else:
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
            return

        # API Admin: Tạo mã giảm giá mới
        if path == "/api/admin/add_code":
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return
            code = str(body.get("code", "")).strip().upper()
            try:
                discount_pct = int(body.get("discount_pct", 0))
                if not (1 <= discount_pct <= 100):
                    raise ValueError()
            except Exception:
                self._send_json(400, {"ok": False, "error": "Phần trăm giảm giá phải từ 1 đến 100"})
                return
            max_uses = int(body.get("max_uses", 0) or 0)
            item = db.add_code(code, discount_pct, max_uses)
            self._send_json(200, {"ok": True, "item": item})
            return

        # API Admin: Xóa mã giảm giá
        if path == "/api/admin/del_code":
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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

        # 1. API Kiểm tra tài khoản Locket / Spotify trước khi mua
        if path == "/api/check_account":
            service = body.get("service", "locket")
            raw_id = str(body.get("identifier", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username hoặc Link tài khoản"})
                return

            try:
                if service == "spotify":
                    res = api.spotify_check(raw_id)
                    data = res.get("data") if isinstance(res.get("data"), dict) else res
                    uid = data.get("uid") or data.get("id") or raw_id
                    display = data.get("displayName") or data.get("username") or data.get("name") or uid
                    avatar = data.get("avatar") or data.get("image") or data.get("avatarUrl")
                    plan = data.get("plan") or data.get("product") or "Free"
                    is_bound = data.get("isBound", False)
                    self._send_json(200, {
                        "ok": True,
                        "service": "spotify",
                        "uid": uid,
                        "display_name": display,
                        "avatar": avatar,
                        "plan": plan,
                        "is_bound": is_bound,
                        "status_text": "Đã kết nối IP thiết bị" if is_bound else "Chưa khóa IP (Sẵn sàng nâng cấp)"
                    })
                    return

                else:
                    # Gói Locket Gold
                    cleaned = utils.clean_input(raw_id)
                    try:
                        res = api.locket_resolve(cleaned)
                        data = res.get("data") if isinstance(res.get("data"), dict) else res
                        uid = data.get("uid") or data.get("id") or cleaned
                        display = data.get("displayName") or data.get("username") or data.get("name") or cleaned
                        avatar = data.get("avatar") or data.get("avatarUrl")
                    except Exception as e:
                        logger.warning(f"Locket resolve error: {e}")
                        uid = cleaned
                        display = cleaned
                        avatar = None

                    self._send_json(200, {
                        "ok": True,
                        "service": "locket",
                        "uid": uid,
                        "display_name": display,
                        "avatar": avatar,
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
            
            pv = config.PRODUCTS.get(product, {})
            plnv = pv.get("plans", {}).get(plan, {})
            orig_price = plnv.get("price", 149000)

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
            product = body.get("product")
            plan = body.get("plan")
            identifier = str(body.get("identifier", "")).strip()
            display_name = str(body.get("display_name", "")).strip() or identifier
            avatar = body.get("avatar", "")
            token = body.get("token", "")

            if not product or not plan or not identifier:
                self._send_json(400, {"ok": False, "error": "Thiếu thông tin gói hoặc tài khoản khách"})
                return

            pv = config.PRODUCTS.get(product)
            if not pv or plan not in pv.get("plans", {}):
                self._send_json(400, {"ok": False, "error": "Gói cước không hợp lệ"})
                return

            plnv = pv["plans"][plan]
            price = plnv["price"]
            orig_price = price
            order_id = utils.gen_order_id()

            coupon = str(body.get("discount_code", "") or body.get("coupon", "")).strip().upper()
            discount_amount = 0
            applied_code = ""

            if coupon:
                chk = utils.check_and_apply_coupon(coupon, orig_price)
                if chk.get("ok"):
                    discount_amount = chk["discount_amount"]
                    price = chk["final_price"]
                    applied_code = chk["code"]
                    if chk.get("is_db"):
                        db.use_code(applied_code)

            # Lưu vào Database dùng chung với Bot Telegram
            extra_fields = {
                "source": "web",
                "avatar": avatar,
                "token": token,
                "account_target": display_name or identifier,
                "discount_code": applied_code,
                "discount_amount": discount_amount,
                "original_price": orig_price,
            }

            db.create_order(
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

            # Sinh link VietQR chuẩn
            qr_url = utils.get_vietqr_url(amount=price, add_info=f"ORDER_{order_id}")

            # Gửi thông báo đến Admin qua Telegram Bot (nếu đang chạy)
            if BOT_INSTANCE and BOT_LOOP:
                msg_admin = (
                    f"🛒 <b>[ĐƠN HÀNG WEB MỚI]</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• Mã đơn: <code>ORDER_{order_id}</code>\n"
                    f"• Dịch vụ: <b>{pv['name']} - {plnv['label']}</b>\n"
                    f"• Khách: {display_name} (<code>@{identifier}</code>)\n"
                    f"• Số tiền: <b>{utils.fmt_price(price)}</b>\n"
                    f"• Đang chờ chuyển khoản VietQR..."
            )
                for aid in config.ADMIN_IDS:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            BOT_INSTANCE.send_message(chat_id=aid, text=msg_admin, parse_mode="HTML"),
                            BOT_LOOP
                        )
                    except Exception:
                        pass

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
                "product_name": pv["name"],
                "plan_label": plnv["label"],
            })
            return

        # 3. API Reset thiết bị Spotify
        if path == "/api/reset_spotify":
            uid = str(body.get("uid", "")).strip()
            if not uid:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập UID Spotify cần reset"})
                return
            try:
                res = api.spotify_reset(uid)
                self._send_json(200, {
                    "ok": True,
                    "message": "Reset phiên IP thiết bị Spotify thành công! Bạn có thể kết nối ngay trên thiết bị mới."
                })
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
            return

        # 3.1. API Reset / Đổi máy Locket Gold
        if path == "/api/reset_locket":
            raw_id = str(body.get("username", "") or body.get("identifier", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username hoặc Link Locket cần chuyển máy"})
                return
            cleaned = utils.clean_input(raw_id)
            try:
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

        # 4. Webhook SePay (Nhận thông báo chuyển khoản tức thì 0.1s)
        if path in ("/sepay/webhook", "/api/sepay/webhook"):
            logger.info(f"Nhận webhook SePay: {body}")
            content = str(body.get("content", "")).upper()
            amount_in = float(body.get("transferAmount", 0) or 0)

            orders = db.get_orders()
            matched_order_id = None
            for oid, od in orders.items():
                if (oid.upper() in content or f"ORDER_{oid.upper()}" in content) and od.get("status") != "done":
                    if amount_in >= float(od.get("price", 0)):
                        matched_order_id = oid
                        break

            if matched_order_id:
                from order_service import execute_order_activation
                if BOT_LOOP:
                    asyncio.run_coroutine_threadsafe(
                        execute_order_activation(BOT_INSTANCE, matched_order_id),
                        BOT_LOOP
                    )
                else:
                    asyncio.run(execute_order_activation(BOT_INSTANCE, matched_order_id))
                self._send_json(200, {"success": True, "message": f"Activated order {matched_order_id}"})
                return

            self._send_json(200, {"success": True, "message": "Ignored or no matching order"})
            return

        self._send_json(404, {"ok": False, "error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Giữ log sạch sẽ, chỉ log lỗi hoặc request API
        msg = format % args
        if "GET /health" not in msg and "HEAD" not in msg and "GET /ping" not in msg:
            logger.info(f"HTTP: {msg}")


def start_web_server(bot=None, loop=None, port=None):
    set_bot_context(bot, loop)
    if port is None:
        port = int(os.environ.get("PORT", 8080))
    server = ThreadedHTTPServer(("0.0.0.0", port), WebAppHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"🌐 Web App & API Server đã khởi động thành công trên cổng {port}!")
    return server

