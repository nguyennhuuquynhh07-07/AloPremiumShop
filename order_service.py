"""
order_service.py – Logic xử lý đơn hàng tập trung (Locket Gold & Spotify Premium)
Tự động kích hoạt bản quyền qua API CTV, cấp DNS profile và thông báo.
"""

import io
import logging
import asyncio
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

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
    pv = PRODUCTS.get(product_key)
    if not pv:
        return False, f"Sản phẩm {product_key} không tồn tại."
    plnv = pv["plans"].get(plan_key)
    if not plnv:
        return False, f"Gói cước {plan_key} không tồn tại."

    try:
        # Danh sách tài khoản thử kích hoạt:
        # Đối với Locket: API yêu cầu Username Locket (ví dụ: thongtriloaimeo_00) chứ KHÔNG nhận UID Firebase 28 ký tự.
        # Do đó với Locket, ưu tiên display_name / account_target trước UID!
        if pv.get("service") == "locket" or product_key == "locket":
            raw_cands = [
                str(order.get("display_name") or "").strip(),
                str(order.get("account_target") or "").strip(),
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

        if product_key == "combo":
            # Tách biệt 2 mã API cho Locket và Spotify
            combo_map = {
                "6m":  {"locket": "LKG6M",  "spotify": "SP6M"},
                "1y":  {"locket": "LKG1Y",  "spotify": "SPOTIFY1Y"},
                "ltm": {"locket": "LKGVV",  "spotify": "SPVV"},
            }
            pkg_map = combo_map.get(plan_key, {"locket": "LKGVV", "spotify": "SPVV"})
            try:
                await asyncio.to_thread(api.create_subscription, uid=target_account, package_code=pkg_map["locket"], service="locket", note=f"Combo {order_id} Locket")
            except Exception as e_lk:
                logger.warning(f"Combo Locket API: {e_lk}")
            try:
                await asyncio.to_thread(api.create_subscription, uid=target_account, package_code=pkg_map["spotify"], service="spotify", note=f"Combo {order_id} Spotify")
            except Exception as e_sp:
                logger.warning(f"Combo Spotify API: {e_sp}")

            db.update_order(
                order_id, 
                status="done", 
                done_at=datetime.now().isoformat(), 
                dns_link=dns_link,
                dns_link_locket=dns_link_locket,
                dns_link_spotify=dns_link_spotify
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

            if product_key == "combo":
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