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


def dispatch_admin_order_alert(order_id: str, pv: dict, plnv: dict, display_name: str, identifier: str, price: int, orig_price: int, applied_code: str = "", discount_amount: int = 0):
    """Gửi thông báo đơn hàng mới từ Web sang Bot Telegram siêu tốc (< 0.2s, đa kênh dự phòng)"""
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

        # 1. Thử gửi qua Telegram Bot loop nếu có
        sent_any = False
        if BOT_INSTANCE and BOT_LOOP and BOT_LOOP.is_running():
            for aid in config.ADMIN_IDS:
                try:
                    asyncio.run_coroutine_threadsafe(
                        BOT_INSTANCE.send_message(
                            chat_id=aid,
                            text=msg_admin,
                            parse_mode="HTML",
                            reply_markup=kb
                        ),
                        BOT_LOOP
                    )
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
                            client.post(url, json={
                                "chat_id": aid,
                                "text": msg_admin,
                                "parse_mode": "HTML",
                                "reply_markup": kb_dict
                            })
            except Exception as e_http:
                logger.warning(f"Telegram HTTP direct notification failed: {e_http}")

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
        if not path.startswith(("/health", "/ping")) and not path.endswith((".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp", ".mp4")):
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

        # 1.1 Phục vụ Static Images, Videos, Assets & Logo trang web
        if path.endswith((".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp", ".mp4", ".js", ".css")) and ".." not in path:
            file_name = os.path.basename(path)
            if file_name == "favicon.ico":
                file_name = "favicon.png"
            clean_rel = path.lstrip("/")
            file_path = os.path.join(os.path.dirname(__file__), clean_rel)
            if not os.path.exists(file_path):
                file_path = os.path.join(os.path.dirname(__file__), file_name)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                ext = file_name.rsplit(".", 1)[-1].lower()
                if ext == "mp4":
                    mime = "video/mp4"
                elif ext == "ico":
                    mime = "image/x-icon"
                elif ext == "svg":
                    mime = "image/svg+xml"
                elif ext == "js":
                    mime = "application/javascript; charset=utf-8"
                elif ext == "css":
                    mime = "text/css; charset=utf-8"
                else:
                    mime = f"image/{ext}"

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
                "dns_slug": getattr(config, "DNS_SLUG", "alopremiumshop"),
                "dns_url": f"{getattr(config, 'DNS_BASE_URL', 'https://doh.2707226.xyz')}/{getattr(config, 'DNS_SLUG', 'alopremiumshop')}",
            })
            return

        # 3. API Danh sách gói cước & bảng giá (kèm cấu hình Banner ưu đãi)
        if path == "/api/packages":
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
            })
            return

        # 3.0 API Đồng bộ đơn hàng từ máy chủ CTV (Web Chủ)
        if path == "/api/sync_upstream":
            from order_service import sync_upstream_orders
            cnt = sync_upstream_orders()
            self._send_json(200, {
                "ok": True,
                "message": f"Đã đồng bộ {cnt} tài khoản từ máy chủ CTV thành công!",
                "synced_count": cnt
            })
            return

        # 3.1 API Danh sách đơn hàng vừa kích hoạt thành công (Đồng bộ máy chủ CTV + Đơn nội bộ)
        if path == "/api/recent_purchases":
            recent_list = []
            
            # 1. Đơn hàng nội bộ đã hoàn tất
            orders = list(db.get_orders().values())
            done_orders = [o for o in orders if o.get("status") == "done"]
            done_orders.sort(key=lambda x: x.get("done_at") or x.get("created_at") or "", reverse=True)

            for o in done_orders[:10]:
                raw_name = str(o.get("display_name") or o.get("username") or o.get("uid") or "Khách").strip()
                if raw_name.startswith("web_"):
                    raw_name = raw_name[4:]
                masked_name = raw_name[:4] + "***" if len(raw_name) > 4 else raw_name + "***"

                prod = config.PRODUCTS.get(o.get("product"), {})
                prod_name = prod.get("name", "Gói VIP")
                plan = prod.get("plans", {}).get(o.get("plan"), {})
                plan_label = plan.get("label", "")
                full_pkg = f"{prod_name} {plan_label}".strip()

                t_str = o.get("done_at") or o.get("created_at")
                time_ago = "Vừa xong"
                if t_str:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                        mins = max(1, int((datetime.now().astimezone() - dt).total_seconds() / 60))
                        if mins < 60:
                            time_ago = f"{mins} phút trước"
                        elif mins < 1440:
                            time_ago = f"{mins // 60} giờ trước"
                        else:
                            time_ago = f"{mins // 1440} ngày trước"
                    except Exception:
                        pass

                recent_list.append({
                    "user": masked_name,
                    "pkg": full_pkg,
                    "time": time_ago,
                    "avatar": o.get("avatar"),
                    "is_real": True
                })

            # 2. Đồng bộ TẤT CẢ người đã kích hoạt từ Máy chủ API CTV (/api/uid/list)
            try:
                server_uids = api.get_activated_uids()
                for item in server_uids:
                    u_name = str(item.get("username") or item.get("uidString") or "VIP").strip()
                    masked_u = u_name[:4] + "***" if len(u_name) > 4 else u_name + "***"

                    pkg_obj = item.get("package") or {}
                    pkg_name = pkg_obj.get("name") or "Locket Gold VIP"
                    if "test" in pkg_name.lower():
                        pkg_name = "Locket Gold VIP"

                    created_at = item.get("createdAt")
                    time_ago = "Vừa xong"
                    if created_at:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            mins = max(1, int((datetime.now().astimezone() - dt).total_seconds() / 60))
                            if mins < 60:
                                time_ago = f"{mins} phút trước"
                            elif mins < 1440:
                                time_ago = f"{mins // 60} giờ trước"
                            else:
                                time_ago = f"{mins // 1440} ngày trước"
                        except Exception:
                            pass

                    recent_list.append({
                        "user": masked_u,
                        "pkg": pkg_name,
                        "time": time_ago,
                        "avatar": item.get("avatarUrl"),
                        "is_real": True
                    })
            except Exception as e_srv:
                logger.warning(f"Error syncing server UIDs to recent purchases: {e_srv}")

            self._send_json(200, {"ok": True, "purchases": recent_list})
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

            # Tự động quét giao dịch SePay trong luồng phụ (không làm nghẽn phản hồi HTTP của Web)
            if order.get("status") in ("pending", "waiting_payment", "pending_approval"):
                # Kiểm tra nếu đơn hàng đã quá 5 phút (300 giây) chưa thanh toán -> Tự động hủy
                created_str = order.get("created_at")
                if created_str:
                    try:
                        from datetime import datetime, timezone
                        dt_str = created_str.replace("Z", "+00:00")
                        parsed_dt = datetime.fromisoformat(dt_str)
                        if parsed_dt.tzinfo is not None:
                            age = (datetime.now(timezone.utc) - parsed_dt).total_seconds()
                        else:
                            age = (datetime.now() - parsed_dt).total_seconds()

                        if age > 300:
                            db.update_order(order_id, status="cancelled", cancel_reason="Hết thời gian thanh toán (5 phút)")
                            order["status"] = "cancelled"
                    except Exception as e_expire_chk:
                        logger.warning(f"Error checking expire for order {order_id}: {e_expire_chk}")

                if order.get("status") in ("pending", "waiting_payment", "pending_approval"):
                    try:
                        from order_service import check_and_activate_sepay_order
                        threading.Thread(target=check_and_activate_sepay_order, args=(order_id, BOT_INSTANCE), daemon=True).start()
                    except Exception as e_poll_sp:
                        logger.warning(f"Error checking SePay during order_status: {e_poll_sp}")

            is_done = order.get("status") == "done"
            prod_key = order.get("product")
            is_locket_ai = (prod_key == "locket_ai")
            has_studio = order.get("has_studio", False) or (prod_key == "studio_caption")
            username_target = utils.clean_input(str(order.get("uid") or order.get("username") or order.get("account_target") or order.get("display_name") or "")).lstrip("@")
            studio_url = f"https://locket.jayteam.click/caption.html?u={username_target}" if has_studio else None
            vip_download_url = None

            download_url = None if is_locket_ai else (f"/api/download_profile?order_id={order_id}" if is_done else None)
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
                "is_locket_ai": is_locket_ai,
                "contact_admin": is_locket_ai,
                "has_studio": has_studio,
                "studio_url": studio_url if is_done else None,
                "vip_download_url": None,
            })
            return

        # 5. API Tải file .mobileconfig (BẢO VỆ CHẶT CHẼ: CHỈ CHO ĐƠN ĐÃ THANH TOÁN THẬT)
        if path == "/api/download_profile" or path.endswith(".mobileconfig"):
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
                # Fallback: kiểm tra trực tiếp trên máy chủ API CTV
                if not order and len(clean_u) >= 3:
                    try:
                        ctv_info = api.check_uid_details(clean_u, "locket")
                        dt = ctv_info.get("data", {}) if isinstance(ctv_info, dict) else {}
                        if dt.get("active") or dt.get("status") == "ACTIVE":
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
            if product_key == "locket_ai":
                vip_url = getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
                self.send_response(302)
                self.send_header("Location", vip_url)
                self._send_cors_headers()
                self.end_headers()
                return

            # Chuyển hướng trực tiếp về hồ sơ chính chủ AloPremiumShop trên server CTV (https://doh.2707226.xyz/alopremiumshop)
            official_dns_url = f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
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
                    o_user == q_clean or
                    o_ident == q_clean or
                    o_disp == q_clean or
                    o_target == q_clean or
                    o_uid == q_clean or
                    (len(q_clean) >= 4 and (q_clean in o_user or q_clean in o_ident or q_clean in o_disp))
                )

                if match:
                    is_done = od.get("status") == "done"
                    prod_k = od.get("product") or "locket"
                    is_ai = (prod_k == "locket_ai")
                    u_disp = od.get("display_name") or od.get("username") or od.get("identifier") or "Khách VIP"
                    u_clean = utils.clean_input(str(u_disp)).lstrip("@")
                    results.append({
                        "order_id": oid,
                        "product": prod_k,
                        "plan": od.get("plan") or "VIP",
                        "price": od.get("price", 0),
                        "status": od.get("status"),
                        "uid": od.get("uid"),
                        "display_name": u_disp,
                        "avatar": od.get("avatar"),
                        "created_at": od.get("created_at"),
                        "download_url": None if is_ai else (f"/api/download_profile?order_id={oid}" if is_done else None),
                        "direct_safari_url": None if is_ai else (f"{config.DNS_BASE_URL}/{config.DNS_SLUG}" if is_done else None),
                        "studio_url": None,
                        "contact_admin": is_ai
                    })

            # Nếu chưa thấy trong database local nhưng tài khoản đã kích hoạt trên máy chủ API CTV (web chủ)
            if len(results) == 0 and len(q_clean) >= 3:
                # 1. Quét nhanh trong danh sách UIDs đã kích hoạt từ web chủ
                try:
                    uids = api.get_activated_uids()
                    for it in uids:
                        it_u = str(it.get("username", "")).lower().lstrip("@")
                        it_uid = str(it.get("uidString", "")).lower()
                        if q_clean == it_u or q_clean == it_uid or (len(q_clean) >= 4 and (q_clean in it_u or q_clean in it_uid)):
                            pkg_it = it.get("package") or {}
                            svc_it = it.get("service") or "locket"
                            safe_suffix = (it_uid[:8] if len(it_uid) >= 8 else it_u[:8]).upper()
                            oid_it = f"CTV_{safe_suffix}"

                            # Tự động đồng bộ ngay vào database nội bộ
                            db.update_order(
                                oid_it,
                                order_id=oid_it,
                                user_id=0,
                                username=it.get("username") or it_u,
                                display_name=it.get("username") or it_u,
                                account_target=it.get("username") or it_u,
                                uid=it.get("uidString") or q_clean,
                                product=svc_it,
                                plan=pkg_it.get("name") or "VIP",
                                plan_label=pkg_it.get("name") or "VIP",
                                status="done",
                                created_at=it.get("createdAt") or datetime.now().isoformat(),
                                done_at=it.get("createdAt") or datetime.now().isoformat(),
                                expires_at=it.get("expiresAt"),
                                avatar=it.get("avatarUrl"),
                                dns_link=f"{config.DNS_BASE_URL}/{config.DNS_SLUG}",
                                source="web_chu"
                            )
                            results.append({
                                "order_id": oid_it,
                                "product": svc_it,
                                "plan": pkg_it.get("name") or "VIP",
                                "price": 0,
                                "status": "done",
                                "uid": it.get("uidString") or q_clean,
                                "display_name": it.get("username") or q_clean,
                                "avatar": it.get("avatarUrl"),
                                "expires_at": it.get("expiresAt"),
                                "created_at": it.get("createdAt") or datetime.now().isoformat(),
                                "download_url": f"/api/download_profile?order_id={oid_it}",
                                "direct_safari_url": f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
                            })
                            break
                except Exception as e_q_uids:
                    logger.warning(f"Error checking active UIDs during lookup: {e_q_uids}")

                # 2. Nếu vẫn chưa có, gọi tra cứu chi tiết UID (cả Locket và Spotify)
                if len(results) == 0:
                    for svc in ("locket", "spotify"):
                        try:
                            ctv_res = api.check_uid_details(q_clean, svc)
                            dt = ctv_res.get("data", {}) if isinstance(ctv_res, dict) else {}
                            if dt.get("active") or dt.get("status") == "ACTIVE" or dt.get("found"):
                                pkg_info = dt.get("package") or {}
                                ret_uid = dt.get("uid") or q_clean
                                ret_user = dt.get("username") or q_clean
                                safe_suffix = (ret_uid[:8] if len(ret_uid) >= 8 else ret_user[:8]).upper()
                                ret_oid = f"CTV_{safe_suffix}"

                                db.update_order(
                                    ret_oid,
                                    order_id=ret_oid,
                                    user_id=0,
                                    username=ret_user,
                                    display_name=ret_user,
                                    account_target=ret_user,
                                    uid=ret_uid,
                                    product=dt.get("service") or svc,
                                    plan=pkg_info.get("name") or "VIP",
                                    plan_label=pkg_info.get("name") or "VIP",
                                    status="done",
                                    created_at=dt.get("createdAt") or datetime.now().isoformat(),
                                    done_at=dt.get("createdAt") or datetime.now().isoformat(),
                                    expires_at=dt.get("expiresAt"),
                                    avatar=dt.get("avatarUrl"),
                                    dns_link=f"{config.DNS_BASE_URL}/{config.DNS_SLUG}",
                                    source="web_chu"
                                )
                                results.append({
                                    "order_id": ret_oid,
                                    "product": dt.get("service") or svc,
                                    "plan": pkg_info.get("name") or "VIP",
                                    "price": 0,
                                    "status": "done",
                                    "uid": ret_uid,
                                    "display_name": ret_user,
                                    "avatar": dt.get("avatarUrl"),
                                    "expires_at": dt.get("expiresAt"),
                                    "created_at": dt.get("createdAt") or datetime.now().isoformat(),
                                    "download_url": f"/api/download_profile?order_id={ret_oid}",
                                    "direct_safari_url": f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
                                })
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
                self.send_header("Cache-Control", "no-cache, must-revalidate")
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
            try:
                activated_uids = api.get_activated_uids()
            except Exception:
                activated_uids = []

            self._send_json(200, {
                "ok": True,
                "account": acc,
                "packages": pkgs,
                "codes": codes,
                "activated_uids": activated_uids,
                "api_base_url": config.API_BASE_URL,
            })
            return

        # API Admin: Lấy danh sách đơn hàng
        if path == "/api/admin/orders":
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return
            all_orders = list(db.get_orders().values())
            all_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            self._send_json(200, {"ok": True, "orders": all_orders[:50]})
            return

        # API Admin: Lấy danh sách bảng giá & mã gói (kèm cấu hình Banner)
        if path == "/api/admin/prices":
            pin = params.get("pin", [""])[0].strip() or self.headers.get("X-Admin-PIN", "").strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return
            codes = list(db.get_codes().values())
            self._send_json(200, {"ok": True, "codes": codes})
            return

        # API Admin: Thống kê doanh thu & tổng quan toàn diện
        if path == "/api/admin/stats":
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return

            orders = list(db.get_orders().values())
            users = db.get_users()
            done_orders = [o for o in orders if o.get("status") == "done"]
            pending_orders = [o for o in orders if o.get("status") in ("waiting_payment", "pending", "pending_approval")]
            rejected_orders = [o for o in orders if o.get("status") in ("cancelled", "rejected", "failed")]
            
            total_revenue = sum(o.get("price", 0) for o in done_orders)

            from datetime import datetime
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            today_orders = [o for o in done_orders if str(o.get("done_at", "")).startswith(today_str) or str(o.get("created_at", "")).startswith(today_str)]
            today_revenue = sum(o.get("price", 0) for o in today_orders)

            locket_done = [o for o in done_orders if o.get("product") == "locket"]
            spotify_done = [o for o in done_orders if o.get("product") == "spotify"]

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
                    }
                }
            })
            return

        # API Admin: Danh sách khách hàng & chi tiêu
        if path == "/api/admin/users":
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = params.get("pin", [""])[0].strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
        if path in ("/", "/index.html"):
            index_path = os.path.join(os.path.dirname(__file__), "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    html_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-cache, must-revalidate")
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

        # API Admin: Cập nhật thông báo ưu đãi (Banner Header Web)
        if path == "/api/admin/update_banner":
            pin = str(body.get("pin", "")).strip() or self.headers.get("X-Admin-PIN", "").strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip() or self.headers.get("X-Admin-PIN", "").strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip() or self.headers.get("X-Admin-PIN", "").strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip() or self.headers.get("X-Admin-PIN", "").strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            
            import re
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

        # API Admin: Kích hoạt gói thủ công trực tiếp lên máy chủ API CTV
        if path == "/api/admin/manual_activate":
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
                return
            order_id = str(body.get("order_id", "")).strip()
            reason = str(body.get("reason", "Admin hủy đơn thủ công")).strip()
            order = db.get_order(order_id)
            if not order:
                self._send_json(404, {"ok": False, "error": "Không tìm thấy đơn hàng"})
                return
            
            from datetime import datetime
            db.update_order(order_id, status="rejected", rejected_reason=reason, rejected_at=datetime.now().isoformat())
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
            pin = str(body.get("pin", "")).strip()
            if pin != getattr(config, "ADMIN_PIN", "2802"):
                self._send_json(401, {"ok": False, "error": "Mã PIN không chính xác"})
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

        # 1. API Kiểm tra tài khoản Locket / Spotify trước khi mua (TÁCH BIỆT NGHIÊM NGẶT)
        if path == "/api/check_account":
            service = body.get("service", "locket")
            raw_id = str(body.get("identifier", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập thông tin tài khoản!"})
                return

            try:
                if service == "spotify":
                    import re
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
                    # Gói Locket Gold / Combo (Dòng 1) / VIP All-in-One: CHỈ NHẬN USERNAME LOCKET, CHẶN MỌI ĐƯỜNG LINK
                    import re
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

                for od in existing_orders.values():
                    if od.get("status") in ("waiting_payment", "pending"):
                        od_ident = str(od.get("uid", "")).lower()
                        if od_ident == clean_ident or od_ident == identifier.lower():
                            pending_count_user += 1
                            if od.get("product") == product and od.get("plan") == plan:
                                pending_same_order = od

                # Nếu tài khoản này đã tạo từ 5 đơn trở lên mà chưa thanh toán đơn nào -> Chặn spam
                if pending_count_user >= 5 and not pending_same_order:
                    self._send_json(429, {
                        "ok": False,
                        "error": "Bạn đang có nhiều đơn hàng chưa thanh toán! Vui lòng hoàn tất chuyển khoản đơn hàng trước đó hoặc chờ 5 phút."
                    })
                    return

                # Nếu khách vừa tạo đơn cho cùng gói này -> Tái sử dụng đơn cũ, cập nhật lại giá nếu có mã giảm giá
                if pending_same_order:
                    p_id = pending_same_order["order_id"]
                    p_price = price if applied_code else pending_same_order.get("price", price)
                    p_code = applied_code or pending_same_order.get("discount_code", "")
                    p_disc = discount_amount if applied_code else pending_same_order.get("discount_amount", 0)
                    if applied_code and pending_same_order.get("discount_code") != applied_code:
                        db.update_order(p_id, price=p_price, discount_code=p_code, discount_amount=p_disc)
                    qr_url = utils.get_vietqr_url(amount=p_price, add_info=f"ORDER_{p_id}")
                    dispatch_admin_order_alert(p_id, pv, plnv, display_name, clean_ident or identifier, p_price, orig_price, p_code, p_disc)
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
                        "is_reused": True
                    })
                    return

                order_id = utils.gen_order_id()
                if applied_code:
                    chk_use = utils.check_and_apply_coupon(applied_code, orig_price)
                    if chk_use.get("ok") and chk_use.get("is_db"):
                        db.use_code(applied_code)

                # Lưu vào Database dùng chung với Bot Telegram
                extra_fields = {
                    "source": "web",
                    "avatar": avatar,
                    "token": token,
                    "account_target": identifier,  # Luôn lưu UID thực tế, không dùng display_name
                    "spotify_uid": spotify_uid,
                    "discount_code": applied_code,
                    "discount_amount": discount_amount,
                    "original_price": orig_price,
                    "has_studio": has_studio,
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
            if not identifier and parent_order_id:
                p_ord = db.get_order(parent_order_id)
                if p_ord:
                    identifier = p_ord.get("display_name") or p_ord.get("uid") or p_ord.get("username")
                    display_name = identifier

            if not identifier:
                self._send_json(400, {"ok": False, "error": "Thiếu tài khoản Locket cần mở Studio"})
                return

            sub_order_id = utils.gen_order_id()
            studio_price = getattr(config, "STUDIO_CAPTION_PRICE", 10000)

            db.create_order(
                order_id=sub_order_id,
                user_id=0,
                username=f"web_{identifier[:15]}",
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

            qr_url = utils.get_vietqr_url(amount=studio_price, add_info=f"ORDER_{sub_order_id}")
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
                "plan_label": "Bản Quyền Vĩnh Viễn"
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

        # 3.1. API Reset / Đổi máy Locket Gold (BẢO MẬT: BẮT BUỘC ĐÃ TỪNG MUA GÓI BẢN QUYỀN)
        if path == "/api/reset_locket":
            raw_id = str(body.get("username", "") or body.get("identifier", "")).strip()
            if not raw_id:
                self._send_json(400, {"ok": False, "error": "Vui lòng nhập Username hoặc Link Locket cần chuyển máy"})
                return
            cleaned = utils.clean_input(raw_id)
            try:
                # Kiểm tra tài khoản này đã từng mua gói bản quyền Locket hợp lệ chưa
                has_paid_order = False
                for od in db.get_orders().values():
                    if od.get("product") in ("locket", "combo", "locket_ai") and od.get("status") == "done":
                        if str(od.get("identifier", "")).lower() == cleaned.lower() or str(od.get("uid", "")).lower() == cleaned.lower() or str(od.get("display_name", "")).lower() == cleaned.lower() or str(od.get("account_target", "")).lower() == cleaned.lower():
                            has_paid_order = True
                            break

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
            if expected_token and expected_token not in auth_header:
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

            # Lớp 4: Chống Replay Attack (Mỗi mã giao dịch tx_id của ngân hàng chỉ được dùng đúng 1 lần)
            tx_id = str(body.get("id", "")).strip()
            if tx_id and db.is_tx_used(tx_id):
                logger.warning(f"🚨 Giao dịch SePay {tx_id} đã được sử dụng trước đó (Replay Attack). Bỏ qua!")
                self._send_json(200, {"success": True, "message": "Transaction already processed"})
                return

            tx_content = str(body.get("content", "")).upper()
            amount_in = float(body.get("transferAmount", 0) or 0)

            # Khớp đơn hàng trong database
            orders = db.get_orders()
            matched_order_id = None
            matched_order = None
            for oid, od in orders.items():
                if (oid.upper() in tx_content or f"ORDER_{oid.upper()}" in tx_content) and od.get("status") != "done":
                    if amount_in >= float(od.get("price", 0)):
                        matched_order_id = oid
                        matched_order = od
                        break

            if not matched_order_id:
                self._send_json(200, {"success": True, "message": "Ignored or no matching pending order"})
                return

            # Lớp 5: XÁC THỰC 2 CHIỀU ĐỘC LẬP VỚI SEPAY API SERVER
            # Gọi trực tiếp SePay API để kiểm tra xem TPBank thực sự có tiền về hay không!
            if tx_id and expected_token:
                try:
                    import urllib.request
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

                            # Kiểm tra chéo: Số tài khoản, số tiền và nội dung đơn phải trùng khớp
                            if real_acc != shop_acc or real_amount < float(matched_order.get("price", 0)):
                                logger.error(f"🚨 [GIAN LẬN PHÁT HIỆN] Dữ liệu SePay API không khớp! SePay: {real_acc}, {real_amount}")
                                self._send_json(403, {"ok": False, "error": "Verification failed: Bank data mismatch"})
                                return
                            if matched_order_id.upper() not in real_content and f"ORDER_{matched_order_id.upper()}" not in real_content:
                                logger.error(f"🚨 [GIAN LẬN PHÁT HIỆN] Nội dung SePay API không chứa mã đơn: {real_content}")
                                self._send_json(403, {"ok": False, "error": "Verification failed: Order ID mismatch"})
                                return
                        else:
                            logger.error(f"🚨 Giao dịch {tx_id} không tìm thấy trên SePay API (Status {v_res.status})")
                            self._send_json(403, {"ok": False, "error": "Transaction not verified by SePay API"})
                            return
                except Exception as e_verify:
                    logger.error(f"🚨 Lỗi gọi SePay API verify: {e_verify}. Chặn kích hoạt để bảo vệ shop!")
                    self._send_json(403, {"ok": False, "error": f"Verification error: {e_verify}"})
                    return

            # Đánh dấu transaction đã sử dụng
            if tx_id:
                db.mark_tx_used(tx_id, matched_order_id)

            logger.info(f"✅ Giao dịch hợp lệ 100% từ SePay! Tiến hành kích hoạt đơn ORDER_{matched_order_id}")
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
    try:
        from order_service import sync_upstream_orders
        threading.Thread(target=sync_upstream_orders, daemon=True).start()
    except Exception as e_sync:
        logger.warning(f"Initial upstream sync failed: {e_sync}")
    return server

