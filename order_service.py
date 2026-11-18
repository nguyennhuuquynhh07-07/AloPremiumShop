"""
order_service.py – Logic xử lý đơn hàng tập trung (Locket Gold & Spotify Premium)
Tự động kích hoạt bản quyền qua API CTV, cấp DNS profile và thông báo.
"""

import io
import logging
import asyncio
from datetime import datetime
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode
except ImportError:
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
    class ParseMode:
        HTML = "HTML"

import database as db
import api_client as api
import utils
import config
from config import PRODUCTS, DNS_BASE_URL, DNS_SLUG

logger = logging.getLogger(__name__)


async def execute_order_activation(bot, order_id: str) -> tuple[bool, str]:
    """
    Thực hiện kích hoạt gói và giao hàng tự động cho khách:
    - Gọi API locket.2707226.xyz trừ Coin CTV và cấp DNS Profile Locket/Spotify
    - Gửi ảnh mã QR để khách quét cài bằng Camera iPhone
    - Gửi file cấu hình .mobileconfig và hướng dẫn cài đặt iOS
    """
    order = db.get_order(order_id)
    if not order:
        return False, "Không tìm thấy đơn hàng trong hệ thống."
    if order.get("status") == "done":
        return True, "Đơn hàng đã được duyệt trước đó."

    product_key = order["product"]
    plan_key = order["plan"]
    if product_key == "studio_caption":
        pv = {"name": "Studio Chỉnh Chú Thích & Khung Viền", "emoji": "🎨", "service": "studio"}
        plnv = {"label": "Bản Quyền Vĩnh Viễn", "packageCode": "STUDIO", "price": 10000}
    else:
        pv = PRODUCTS.get(product_key)
        if not pv:
            return False, f"Sản phẩm {product_key} không tồn tại."
        plnv = pv["plans"].get(plan_key)
        if not plnv:
            return False, f"Gói cước {plan_key} không tồn tại."

    try:
        # Danh sách tài khoản thử kích hoạt:
        # Đối với Locket & Combo: API yêu cầu Username Locket (ví dụ: nminhtruong) chứ KHÔNG nhận UID Firebase 28 ký tự hay Tên hiển thị có dấu.
        # Do đó với Locket và Combo, ưu tiên locket_username / account_target / display_name trước UID!
        if pv.get("service") in ("locket", "combo") or product_key in ("locket", "combo"):
            raw_cands = [
                str(order.get("locket_username") or "").strip().lstrip("@"),
                str(order.get("account_target") or "").strip().lstrip("@"),
                str(order.get("display_name") or "").strip().lstrip("@"),
                utils.clean_input(str(order.get("username") or "")),
                str(order.get("uid") or "").strip(),
            ]
        else:
            raw_cands = [
                str(order.get("uid") or "").strip(),
                str(order.get("account_target") or "").strip(),
                str(order.get("display_name") or "").strip(),
                utils.clean_input(str(order.get("username") or "")),
            ]

        candidate_accounts = []
        for cand in raw_cands:
            # Loại bỏ tiền tố web_ nếu có
            if cand.startswith("web_"):
                cand = cand[4:]
            if cand and cand not in candidate_accounts:
                candidate_accounts.append(cand)
        if not candidate_accounts:
            return False, "Đơn hàng thiếu thông tin tài khoản (UID / Username)."

        target_account = candidate_accounts[0]
        dns_link = f"{DNS_BASE_URL}/{DNS_SLUG}"
        dns_link_locket = dns_link
        dns_link_spotify = dns_link

        if product_key == "locket_ai":
            # Cấu hình VIP All-in-One độc lập, tự động cấp kèm luôn Link Studio cá nhân
            vip_url = getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
            username_target = utils.clean_input(str(order.get("uid") or order.get("username") or order.get("account_target") or order.get("display_name") or "")).lstrip("@")
            studio_url = f"https://locket.jayteam.click/caption.html?u={username_target}"
            db.update_order(
                order_id, 
                status="done", 
                done_at=datetime.now().isoformat(), 
                dns_link=vip_url,
                vip_download_url=vip_url,
                has_studio=True,
                studio_link=studio_url
            )
        elif product_key == "studio_caption":
            # Gói phụ 10.000đ Studio Chỉnh chú thích & Đổi khung viền
            username_target = utils.clean_input(str(order.get("uid") or order.get("username") or order.get("account_target") or order.get("display_name") or "")).lstrip("@")
            studio_url = f"https://locket.jayteam.click/caption.html?u={username_target}"
            db.update_order(
                order_id, 
                status="done", 
                done_at=datetime.now().isoformat(), 
                studio_link=studio_url
            )
        elif product_key == "combo":
            # GÓI COMBO DUO CHÍNH CHỦ (LOCKET + SPOTIFY QUA API CTV)
            dns_base = f"{DNS_BASE_URL}/{DNS_SLUG}" if DNS_BASE_URL and DNS_SLUG else "https://doh.2707226.xyz/alopremiumshop"
            dns_link = dns_base
            dns_link_locket = dns_base
            dns_link_spotify = dns_base

            # Tách biệt 2 mã API cho Locket (dùng Username Locket) và Spotify (dùng UID Spotify)
            combo_map = {
                "6m":  {"locket": "LKG6M",  "spotify": "SP6M"},
                "1y":  {"locket": "LKG1Y",  "spotify": "SPOTIFY1Y"},
                "ltm": {"locket": "LKGVV",  "spotify": "SPVV"},
            }
            pkg_map = combo_map.get(plan_key, {"locket": "LKGVV", "spotify": "SPVV"})
            locket_ok = False
            last_lk_err = None
            for acc in candidate_accounts:
                try:
                    await asyncio.to_thread(api.create_subscription, uid=acc, package_code=pkg_map["locket"], service="locket", note=f"Combo {order_id} Locket")
                    locket_ok = True
                    target_account = acc
                    break
                except Exception as e_lk:
                    last_lk_err = e_lk
                    logger.warning(f"Combo Locket API ({acc}): {e_lk}")

            # Danh sách tài khoản Spotify cho gói Combo (ưu tiên spotify_uid khách điền ở dòng 2)
            sp_raw = str(order.get("spotify_uid") or "").strip()
            sp_candidates = []
            if sp_raw:
                try:
                    clean_sp = utils.extract_spotify_uid(sp_raw)
                except Exception:
                    clean_sp = sp_raw
                if clean_sp:
                    sp_candidates.append(clean_sp)
                if sp_raw not in sp_candidates:
                    sp_candidates.append(sp_raw)
            for c in candidate_accounts:
                if c not in sp_candidates:
                    sp_candidates.append(c)

            for sp_acc in sp_candidates:
                try:
                    await asyncio.to_thread(api.create_subscription, uid=sp_acc, package_code=pkg_map["spotify"], service="spotify", note=f"Combo {order_id} Spotify")
                    break
                except Exception as e_sp:
                    logger.warning(f"Combo Spotify API ({sp_acc}): {e_sp}")

            if not locket_ok and last_lk_err:
                logger.error(f"Combo Locket activation failed for all candidates {candidate_accounts}: {last_lk_err}")

            db.update_order(
                order_id, 
                status="done", 
                done_at=datetime.now().isoformat(), 
                dns_link=dns_link,
                dns_link_locket=dns_link_locket,
                dns_link_spotify=dns_link_spotify
            )
        elif product_key == "locket_spotify":
            # GÓI MỚI: LOCKET & SPOTIFY (DNS https://dns3.is-cool.dev/g/ECXI6NSHgj, CHỈ CẦN KÍCH HOẠT USER LOCKET)
            dns_vip = getattr(config, "DNS_COMBO_URL", "https://dns3.is-cool.dev/g/ECXI6NSHgj")
            dns_link = dns_vip
            dns_link_locket = dns_vip
            dns_link_spotify = dns_vip

            act_success = False
            last_err = None
            for acc in candidate_accounts:
                try:
                    result = await asyncio.to_thread(
                        api.create_subscription,
                        uid=acc,
                        package_code=plnv.get("packageCode", "LKGVV"),
                        service="locket",
                        note=f"Order {order_id} Locket&Spotify DNS"
                    )
                    act_success = True
                    target_account = acc
                    if acc != order.get("uid"):
                        db.update_order(order_id, uid=acc, account_target=acc)
                    break
                except Exception as e_act:
                    last_err = e_act
                    err_str = str(e_act).lower()
                    if "404" not in err_str and "không tồn tại" not in err_str:
                        break

            db.update_order(
                order_id, 
                status="done", 
                done_at=datetime.now().isoformat(), 
                dns_link=dns_vip,
                dns_link_locket=dns_vip,
                dns_link_spotify=dns_vip
            )
        else:
            # Gói Locket hoặc Spotify đơn lẻ: tự động fallback các candidate nếu dính 404
            act_success = False
            last_err = None
            for acc in candidate_accounts:
                try:
                    result = await asyncio.to_thread(
                        api.create_subscription,
                        uid=acc,
                        package_code=plnv["packageCode"],
                        service=pv["service"],
                        note=f"Order {order_id} via Telegram Bot"
                    )
                    act_success = True
                    target_account = acc
                    if acc != order.get("uid"):
                        db.update_order(order_id, uid=acc, account_target=acc)
                    break
                except Exception as e_act:
                    last_err = e_act
                    err_str = str(e_act).lower()
                    if "404" not in err_str and "không tồn tại" not in err_str:
                        # Nếu không phải lỗi 404 không tồn tại (vd: hết coin 402, 401...) thì ngắt ngay
                        break
            if not act_success:
                return False, str(last_err or "Kích hoạt thất bại")

            db.update_order(order_id, status="done", done_at=datetime.now().isoformat(), dns_link=dns_link)

        db.record_sale(product_key, plan_key, order["price"])

        from handlers.user_handlers import _build_success_message
        from keyboards import success_kb, combo_success_kb
        success_text = _build_success_message(order, pv, plnv, dns_link)

        if bot and isinstance(order.get("user_id"), int) and order.get("user_id") > 0:
            uid_display = order.get('display_name') or order.get('uid')

            if product_key == "locket_ai":
                from keyboards import locket_ai_success_kb
                username_target = utils.clean_input(str(order.get("uid") or order.get("username") or order.get("account_target") or order.get("display_name") or "")).lstrip("@")
                
                ai_msg = (
                    f"🎉 <b>BẠN ĐÃ THANH TOÁN THÀNH CÔNG GÓI VIP ALL-IN-ONE!</b>\n\n"
                    f"📦 <b>Gói cước:</b> Gói Vĩnh Viễn (VIP ALL-IN-ONE)\n"
                    f"🆔 <b>Mã đơn hàng:</b> <code>ORDER_{order.get('order_id')}</code>\n"
                    f"👤 <b>Tài khoản Locket:</b> @{username_target}\n"
                    f"💵 <b>Số tiền đã thanh toán:</b> {utils.fmt_price(order['price'])}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🎁 <b>ĐẶC QUYỀN MỞ KHÓA TRỌN BỘ:</b>\n"
                    f"👑 <b>Locket Gold:</b> Viền vàng Avatar VIP, Video 60s, Kho 38 khung viền, Tải ảnh 4K.\n"
                    f"🎭 <b>AI Filters Mới:</b> Mở full 8 danh mục bộ lọc (Events, Goofy, Looks, Celebrate...).\n"
                    f"✨ <b>Nút [✨ Tạo diện mạo]:</b> Tự do nhập prompt sáng tạo diện mạo AI cá nhân.\n"
                    f"🎵 <b>Spotify Premium:</b> Chặn 100% Ads quảng cáo, Next bài vô hạn, Âm thanh 320kbps.\n"
                    f"🟠 <b>SoundCloud Go+:</b> Mở khóa SoundCloud Go+ (Plus), Tải nghe Offline.\n"
                    f"🎬 <b>YouTube Premium:</b> Chặn 100% Ads video, Phát âm thanh tắt màn hình & PiP.\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👑 <b>HƯỚNG DẪN KÍCH HOẠT:</b>\n"
                    f"Vì đây là gói VIP ALL-IN-ONE độc quyền, bạn vui lòng <b>bấm nút Liên hệ Admin bên dưới</b> kèm Mã đơn hàng <code>ORDER_{order.get('order_id')}</code> để Admin trực tiếp cấu hình và hỗ trợ kích hoạt ngay lập tức cho bạn nhé!"
                )
                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=ai_msg,
                        parse_mode=ParseMode.HTML,
                        reply_markup=locket_ai_success_kb(order_id=order.get('order_id'))
                    )
                except Exception as e_ai_send:
                    logger.error(f"Error sending Locket AI delivery: {e_ai_send}")

            elif product_key == "studio_caption":
                from keyboards import studio_success_kb
                username_target = utils.clean_input(str(order.get("uid") or order.get("username") or order.get("account_target") or order.get("display_name") or "")).lstrip("@")
                studio_url = f"https://locket.jayteam.click/caption.html?u={username_target}"
                studio_msg = (
                    f"🎉 <b>KÍCH HOẠT THÀNH CÔNG STUDIO CHÚ THÍCH & KHUNG VIỀN!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Tài khoản Locket:</b> @{username_target}\n"
                    f"🎨 <b>Link Studio Chỉnh Chú Thích & Đổi Khung Viền:</b>\n"
                    f"{studio_url}\n\n"
                    f"💵 <b>Số tiền thanh toán:</b> {utils.fmt_price(order['price'])}\n"
                    f"💡 <i>Mở link trên Safari để tạo chú thích độc quyền và đổi khung viền không giới hạn!</i>"
                )
                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=studio_msg,
                        parse_mode=ParseMode.HTML,
                        reply_markup=studio_success_kb(studio_url)
                    )
                except Exception as e_st_send:
                    logger.error(f"Error sending Studio delivery: {e_st_send}")

            elif product_key == "combo":
                # CHỈ KHI MUA COMBO DUO MỚI GỬI CẢ 2 CẤU HÌNH LOCKET VÀ SPOTIFY
                try:
                    # Gửi QR 1: Locket Gold
                    qr_lk = utils.generate_qr_code(dns_link_locket)
                    await bot.send_photo(
                        chat_id=order["user_id"],
                        photo=qr_lk,
                        caption=(
                            f"💛 <b>MÃ QR 1: LOCKET GOLD VIP</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Tài khoản: <b>@{uid_display}</b>\n"
                            f"⚡ Dùng <b>Camera iPhone</b> quét mã trên để cài đặt Locket Gold!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                    # Gửi QR 2: Spotify Premium
                    qr_sp = utils.generate_qr_code(dns_link_spotify)
                    await bot.send_photo(
                        chat_id=order["user_id"],
                        photo=qr_sp,
                        caption=(
                            f"🎵 <b>MÃ QR 2: SPOTIFY PREMIUM LOSSLESS</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Tài khoản: <b>@{uid_display}</b>\n"
                            f"⚡ Dùng <b>Camera iPhone</b> quét mã trên để cài đặt Spotify Premium!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e_qr:
                    logger.warning(f"Could not send Combo QR photos: {e_qr}")

                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=combo_success_kb(dns_link_locket, dns_link_spotify)
                    )
                except Exception as e:
                    logger.error(f"Error sending Combo delivery: {e}")

            elif product_key == "locket_spotify":
                # GÓI MỚI: LOCKET & SPOTIFY (DÙNG DNS https://dns3.is-cool.dev/g/ECXI6NSHgj)
                dns_vip = getattr(config, "DNS_COMBO_URL", "https://dns3.is-cool.dev/g/ECXI6NSHgj")
                try:
                    qr_vip = utils.generate_qr_code(dns_vip)
                    await bot.send_photo(
                        chat_id=order["user_id"],
                        photo=qr_vip,
                        caption=(
                            f"⚡ <b>MÃ QR CẤU HÌNH: LOCKET & SPOTIFY</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Khách hàng: <b>@{uid_display}</b>\n"
                            f"📦 Gói: <b>Locket & Spotify ({plnv['label']})</b>\n\n"
                            f"⚡ <b>Cách cài đặt:</b>\n"
                            f"1️⃣ Dùng <b>Camera iPhone</b> quét mã QR trên màn hình.\n"
                            f"2️⃣ Chạm vào thông báo vàng <b>\"Mở trong Safari\"</b> để cài cấu hình dùng cả 2 ứng dụng!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e_qr:
                    logger.warning(f"Could not send Locket&Spotify QR photo: {e_qr}")

                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=combo_success_kb(dns_vip, dns_vip)
                    )
                except Exception as e:
                    logger.error(f"Error sending Locket&Spotify delivery: {e}")

            elif product_key == "spotify":
                # GÓI ĐƠN LẺ: CHỈ KÍCH HOẠT VÀ GỬI DUY NHẤT SPOTIFY PREMIUM
                try:
                    qr_sp = utils.generate_qr_code(dns_link)
                    await bot.send_photo(
                        chat_id=order["user_id"],
                        photo=qr_sp,
                        caption=(
                            f"🎵 <b>MÃ QR CÀI ĐẶT SPOTIFY PREMIUM</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Khách hàng: <b>@{uid_display}</b>\n"
                            f"📦 Gói: <b>Spotify Premium ({plnv['label']})</b>\n\n"
                            f"⚡ <b>Cách cài đặt:</b>\n"
                            f"1️⃣ Dùng <b>Camera iPhone</b> quét mã QR trên màn hình.\n"
                            f"2️⃣ Chạm vào thông báo vàng <b>\"Mở trong Safari\"</b> để tải hồ sơ cấu hình Spotify!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e_qr:
                    logger.warning(f"Could not send Spotify QR photo: {e_qr}")

                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=success_kb(dns_link, service="spotify")
                    )
                except Exception as e:
                    logger.error(f"Error sending Spotify delivery: {e}")

            else:
                # GÓI ĐƠN LẺ: CHỈ KÍCH HOẠT VÀ GỬI DUY NHẤT LOCKET GOLD VIP
                try:
                    qr_lk = utils.generate_qr_code(dns_link)
                    await bot.send_photo(
                        chat_id=order["user_id"],
                        photo=qr_lk,
                        caption=(
                            f"💛 <b>MÃ QR CÀI ĐẶT LOCKET GOLD VIP</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Khách hàng: <b>@{uid_display}</b>\n"
                            f"📦 Gói: <b>Locket Gold VIP ({plnv['label']})</b>\n\n"
                            f"⚡ <b>Cách cài đặt siêu tốc:</b>\n"
                            f"1️⃣ Dùng <b>Camera iPhone</b> quét mã QR trên màn hình.\n"
                            f"2️⃣ Chạm vào thông báo vàng <b>\"Mở trong Safari\"</b> để tải hồ sơ Locket Gold!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e_qr:
                    logger.warning(f"Could not send Locket QR photo: {e_qr}")

                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=success_kb(dns_link, service="locket")
                    )
                except Exception as e:
                    logger.error(f"Error sending Locket delivery: {e}")
        if bot:
            for aid in config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=aid,
                        text=(
                            f"💰 <b>[KÍCH HOẠT THÀNH CÔNG]</b>\n"
                            f"• Mã đơn: <code>ORDER_{order_id}</code>\n"
                            f"• Gói: <b>{pv['name']} ({plnv['label']})</b>\n"
                            f"• Khách: {order.get('display_name')} (<code>@{order.get('uid')}</code>)\n"
                            f"• Nguồn: <b>{order.get('source', 'Telegram').upper()}</b>\n"
                            f"• Số tiền: <b>{utils.fmt_price(order['price'])}</b>"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

        return True, "Kích hoạt API CTV thành công!"

    except Exception as e:
        logger.error(f"Error activating order {order_id}: {e}")
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════════
#  CƠ CHẾ QUÉT THANH TOÁN SEPAY SIÊU TỐC (DÙNG CHUNG WEB & BOT)
# ═══════════════════════════════════════════════════════════════════════════════

import time
import httpx

_SEPAY_CACHE = {
    "timestamp": 0,
    "transactions": []
}

def fetch_sepay_transactions(force_refresh: bool = False) -> list:
    """Tải danh sách 20 giao dịch mới nhất từ SePay API, có bộ nhớ đệm 3s chống quá tải"""
    token = getattr(config, "SEPAY_API_TOKEN", "")
    if not token:
        return []

    now = time.time()
    if not force_refresh and (now - _SEPAY_CACHE["timestamp"] < 3.0):
        return _SEPAY_CACHE["transactions"]

    url = "https://my.sepay.vn/userapi/transactions/list?limit=20"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "AloPremiumEngine/2.0"}

    try:
        with httpx.Client(timeout=6.0) as client:
            r = client.get(url, headers=headers)
            if r.status_code == 200:
                txs = r.json().get("transactions", [])
                _SEPAY_CACHE["timestamp"] = now
                _SEPAY_CACHE["transactions"] = txs
                return txs
    except Exception as e:
        logger.warning(f"Error fetching SePay transactions: {e}")
    return _SEPAY_CACHE.get("transactions", [])


def check_and_activate_sepay_order(order_id: str, bot=None) -> tuple[bool, str]:
    """
    Kiểm tra nhanh giao dịch SePay cho một đơn hàng cụ thể.
    Nếu tiền đã về tài khoản TPBank -> Tự động kích hoạt ngay lập tức!
    """
    order = db.get_order(order_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"
    if order.get("status") == "done":
        return True, "Đơn hàng đã hoàn thành"

    transactions = fetch_sepay_transactions()
    if not transactions:
        return False, "Chưa tìm thấy giao dịch nào"

    req_amount = float(order.get("price", 0))
    clean_oid = order_id.upper().replace("ORDER_", "")
    shop_acc = str(getattr(config, "ACCOUNT_NO", "")).strip()

    for tx in transactions:
        tx_id = str(tx.get("id", "")).strip()
        if not tx_id or db.is_tx_used(tx_id):
            continue

        tx_acc = str(tx.get("account_number", "")).strip()
        if shop_acc and tx_acc and tx_acc != shop_acc:
            continue

        content = str(tx.get("transaction_content", "")).upper()
        amount_in = float(tx.get("amount_in", 0) or 0)

        # Khớp mã đơn: "976RF6B3", "ORDER_976RF6B3", "ORDER 976RF6B3"
        matched = (clean_oid in content or f"ORDER_{clean_oid}" in content or f"ORDER {clean_oid}" in content)
        if matched and amount_in >= req_amount:
            logger.info(f"⚡ [SEPAY AUTO-DETECT] Khớp đơn {order_id} ({amount_in}đ, TX: {tx_id})!")
            db.mark_tx_used(tx_id, order_id)
            
            # Kích hoạt đơn hàng
            import web_server
            active_bot = bot or getattr(web_server, "BOT_INSTANCE", None)
            active_loop = getattr(web_server, "BOT_LOOP", None)

            if active_loop and active_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    execute_order_activation(active_bot, order_id),
                    active_loop
                )
                try:
                    ok, msg = future.result(timeout=15)
                except Exception as e_wait:
                    logger.warning(f"Threadsafe future wait error: {e_wait}")
                    ok, msg = True, "Kích hoạt đang xử lý ngầm"
            else:
                try:
                    loop = asyncio.new_event_loop()
                    ok, msg = loop.run_until_complete(execute_order_activation(active_bot, order_id))
                    loop.close()
                except Exception as e_ev:
                    ok, msg = False, str(e_ev)

            return ok, msg

    return False, "Chưa nhận được giao dịch khớp mã đơn"


async def check_all_sepay_pending_payments(bot=None) -> list[str]:
    """Quét tất cả các đơn hàng đang chờ và tự động duyệt nếu tiền đã về"""
    orders = db.get_orders()
    pending = [
        o for o in orders.values() 
        if o.get("status") in ("waiting_payment", "pending_approval", "pending")
    ]
    if not pending:
        return []

    activated_list = []
    transactions = await asyncio.to_thread(fetch_sepay_transactions, True)
    if not transactions:
        return []

    shop_acc = str(getattr(config, "ACCOUNT_NO", "")).strip()

    for order in pending:
        order_id = order["order_id"]
        clean_oid = order_id.upper().replace("ORDER_", "")
        req_amount = float(order.get("price", 0))

        for tx in transactions:
            tx_id = str(tx.get("id", "")).strip()
            if not tx_id or db.is_tx_used(tx_id):
                continue

            tx_acc = str(tx.get("account_number", "")).strip()
            if shop_acc and tx_acc and tx_acc != shop_acc:
                continue

            content = str(tx.get("transaction_content", "")).upper()
            amount_in = float(tx.get("amount_in", 0) or 0)

            if (clean_oid in content or f"ORDER_{clean_oid}" in content or f"ORDER {clean_oid}" in content) and amount_in >= req_amount:
                logger.info(f"✅ SePay tự động phát hiện thanh toán cho đơn ORDER_{order_id} ({amount_in}đ, TX: {tx_id})!")
                db.mark_tx_used(tx_id, order_id)
                ok, msg = await execute_order_activation(bot, order_id)
                if ok:
                    activated_list.append(order_id)
                    if isinstance(order.get("user_id"), int) and order.get("user_id") > 0:
                        try:
                            await bot.send_message(
                                chat_id=order["user_id"],
                                text=(
                                    f"🔔 <b>HỆ THỐNG ĐÃ TỰ ĐỘNG NHẬN ĐƯỢC THANH TOÁN {utils.fmt_price(int(amount_in))}!</b>\n"
                                    f"Gói dịch vụ <b>{order['product']}</b> đã được kích hoạt thành công."
                                ),
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass
                break

    return activated_list


def cancel_expired_pending_orders(max_age_seconds: int = 300) -> list[str]:
    """
    Quét và tự động hủy các đơn hàng đang chờ thanh toán quá 5 phút (300s).
    Tránh tình trạng đơn hàng treo mãi và giải phóng phiên cho khách hàng.
    """
    from datetime import datetime, timezone
    orders = db.get_orders()
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    cancelled_ids = []

    for oid, o in list(orders.items()):
        if o.get("status") in ("waiting_payment", "pending"):
            created_str = o.get("created_at")
            if not created_str:
                continue
            try:
                # Hỗ trợ cả định dạng ISO có Z/UTC và ISO local
                dt_str = created_str.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(dt_str)
                if parsed_dt.tzinfo is not None:
                    age = (now_utc - parsed_dt).total_seconds()
                else:
                    age = (now_local - parsed_dt).total_seconds()

                if age > max_age_seconds:
                    o["status"] = "cancelled"
                    o["cancel_reason"] = f"Hết thời gian thanh toán ({int(max_age_seconds/60)} phút)"
                    cancelled_ids.append(oid)
                    logger.info(f"⏳ [TIMEOUT] Đơn hàng ORDER_{oid} đã quá 5 phút chưa thanh toán -> Tự động hủy.")
            except Exception as e_time:
                logger.warning(f"Error parsing date for order {oid}: {e_time}")

    if cancelled_ids:
        db.save_orders(orders)

    return cancelled_ids


# ═══════════════════════════════════════════════════════════════════════════════
#  ĐỒNG BỘ ĐƠN HÀNG TỪ MÁY CHỦ API CTV (WEB CHỦ) VỀ WEB & BOT NỘI BỘ
# ═══════════════════════════════════════════════════════════════════════════════

def sync_upstream_orders() -> int:
    """
    Đồng bộ toàn bộ danh sách tài khoản đã kích hoạt từ máy chủ API CTV (web chủ)
    vào cơ sở dữ liệu nội bộ để khách hàng cũ có thể tra cứu và tải lại DNS bất cứ lúc nào.
    """
    try:
        import api_client
        uids = api_client.get_activated_uids(force_refresh=True)
        if not uids:
            return 0

        orders = db.get_orders()
        synced_count = 0

        for item in uids:
            username = str(item.get("username") or "").strip()
            uid_str = str(item.get("uidString") or "").strip()
            if not username and not uid_str:
                continue

            service = item.get("service") or "locket"
            pkg = item.get("package") or {}
            pkg_name = pkg.get("name") or ("Locket Gold VIP" if service == "locket" else "Spotify Premium")
            pkg_code = (pkg.get("code") or "").upper()

            # Xác định plan key chuẩn (6m, 1y, ltm, test)
            plan_key = "ltm"
            if "6M" in pkg_code or "6 THÁNG" in pkg_name.upper():
                plan_key = "6m"
            elif "1Y" in pkg_code or "1 NĂM" in pkg_name.upper():
                plan_key = "1y"
            elif "T3D" in pkg_code or "TEST" in pkg_name.upper():
                plan_key = "test"

            clean_u = username.lower().lstrip("@")
            clean_uid = uid_str.lower()
            matched_oid = None

            for oid, od in orders.items():
                od_u = str(od.get("username", "")).lower().lstrip("@")
                od_disp = str(od.get("display_name", "")).lower().lstrip("@")
                od_uid = str(od.get("uid", "")).lower()
                od_target = str(od.get("account_target", "")).lower().lstrip("@")

                if (clean_u and (clean_u == od_u or clean_u == od_disp or clean_u == od_target)) or \
                   (clean_uid and (clean_uid == od_uid or clean_uid == od_target)):
                    matched_oid = oid
                    break

            dns_link = f"{config.DNS_BASE_URL}/{config.DNS_SLUG}"
            created_at = item.get("createdAt") or datetime.now().isoformat()
            expires_at = item.get("expiresAt")
            avatar_url = item.get("avatarUrl")

            if matched_oid:
                orders[matched_oid]["status"] = "done"
                if not orders[matched_oid].get("dns_link"):
                    orders[matched_oid]["dns_link"] = dns_link
                if expires_at:
                    orders[matched_oid]["expires_at"] = expires_at
                if avatar_url and not orders[matched_oid].get("avatar"):
                    orders[matched_oid]["avatar"] = avatar_url
                if not orders[matched_oid].get("uid"):
                    orders[matched_oid]["uid"] = uid_str
            else:
                safe_oid_suffix = (uid_str[:8] if len(uid_str) >= 8 else username[:8]).upper()
                new_oid = f"CTV_{safe_oid_suffix}"
                orders[new_oid] = {
                    "order_id": new_oid,
                    "user_id": 0,
                    "username": username or uid_str,
                    "display_name": username or uid_str,
                    "account_target": username or uid_str,
                    "uid": uid_str or username,
                    "product": service,
                    "plan": plan_key,
                    "plan_label": pkg_name,
                    "price": 0,
                    "status": "done",
                    "avatar": avatar_url,
                    "created_at": created_at,
                    "done_at": created_at,
                    "expires_at": expires_at,
                    "dns_link": dns_link,
                    "source": "web_chu"
                }
                synced_count += 1

        db.save_orders(orders)
        logger.info(f"🔄 [SYNC WEB CHỦ] Đã đồng bộ thành công {len(uids)} tài khoản ({synced_count} đơn mới)!")
        return len(uids)
    except Exception as e:
        logger.error(f"Lỗi đồng bộ từ web chủ: {e}")
        return 0
