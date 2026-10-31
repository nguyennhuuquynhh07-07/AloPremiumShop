"""
order_service.py – Logic xử lý đơn hàng tập trung (Locket Gold & Spotify Premium)
Tự động kích hoạt bản quyền qua API CTV, cấp DNS profile và thông báo.
"""

import io
import logging
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
        target_account = order.get("account_target") or order.get("display_name") or order["uid"]
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
                api.create_subscription(uid=target_account, package_code=pkg_map["locket"], service="locket", note=f"Combo {order_id} Locket")
            except Exception as e_lk:
                logger.warning(f"Combo Locket API: {e_lk}")
            try:
                api.create_subscription(uid=target_account, package_code=pkg_map["spotify"], service="spotify", note=f"Combo {order_id} Spotify")
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
            # Gói Locket hoặc Spotify đơn lẻ
            result = api.create_subscription(
                uid=target_account,
                package_code=plnv["packageCode"],
                service=pv["service"],
                note=f"Order {order_id} via Telegram Bot"
            )
            db.update_order(order_id, status="done", done_at=datetime.now().isoformat(), dns_link=dns_link)

        db.record_sale(product_key, plan_key, order["price"])

        from handlers.user_handlers import _build_success_message
        from keyboards import success_kb, combo_success_kb
        success_text = _build_success_message(order, pv, plnv, dns_link)

        if bot and isinstance(order.get("user_id"), int) and order.get("user_id") > 0:
            # 1. Gửi ảnh Mã QR DNS Profile cho khách quét bằng Camera iPhone
            try:
                qr_buf = utils.generate_qr_code(dns_link)
                qr_caption = (
                    f"📷 <b>MÃ QR CÀI ĐẶT DNS PROFILE ({pv['name']})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 Khách hàng: <b>{order.get('display_name') or order.get('uid')}</b>\n"
                    f"📦 Gói: <b>{pv['name']} ({plnv['label']})</b>\n\n"
                    f"⚡ <b>Cách cài đặt siêu tốc:</b>\n"
                    f"1️⃣ Dùng <b>Camera iPhone</b> quét mã QR trên màn hình.\n"
                    f"2️⃣ Chạm vào thông báo vàng <b>\"Mở trong Safari\"</b> để cài đặt hồ sơ DNS!\n"
                    f"<i>(Hoặc bấm nút mở Safari trực tiếp bên dưới)</i>"
                )
                await bot.send_photo(
                    chat_id=order["user_id"],
                    photo=qr_buf,
                    caption=qr_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=success_kb(dns_link)
                )
            except Exception as e_qr:
                logger.warning(f"Could not send QR photo: {e_qr}")

            # 2. Gửi hướng dẫn và file .mobileconfig tách biệt
            try:
                reply_markup_used = combo_success_kb(dns_link_locket, dns_link_spotify) if product_key == "combo" else success_kb(dns_link)
                await bot.send_message(
                    chat_id=order["user_id"],
                    text=success_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup_used
                )

                safe_uid = (order.get("uid") or "vip").replace(" ", "_")

                if product_key == "combo":
                    # Gửi riêng file 1: Locket Gold
                    f_lk = utils.generate_mobileconfig(
                        service_name="Locket Gold VIP",
                        display_name=order.get("display_name") or order.get("uid"),
                        dns_link=dns_link_locket
                    )
                    await bot.send_document(
                        chat_id=order["user_id"],
                        document=f_lk,
                        filename=f"1_LocketGold_{safe_uid}.mobileconfig",
                        caption="💛 <b>HỒ SƠ 1: LOCKET GOLD VIP</b>\nBấm vào file trên để cài đặt vào iPhone.",
                        parse_mode=ParseMode.HTML
                    )

                    # Gửi riêng file 2: Spotify Premium
                    f_sp = utils.generate_mobileconfig(
                        service_name="Spotify Premium",
                        display_name=order.get("display_name") or order.get("uid"),
                        dns_link=dns_link_spotify
                    )
                    await bot.send_document(
                        chat_id=order["user_id"],
                        document=f_sp,
                        filename=f"2_SpotifyPremium_{safe_uid}.mobileconfig",
                        caption="🎵 <b>HỒ SƠ 2: SPOTIFY PREMIUM</b>\nBấm vào file trên để cài đặt vào iPhone.",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    profile_file = utils.generate_mobileconfig(
                        service_name=pv["name"],
                        display_name=order.get("display_name") or order.get("uid"),
                        dns_link=dns_link
                    )
                    file_name = f"{order['product'].capitalize()}_{safe_uid}.mobileconfig"
                    await bot.send_document(
                        chat_id=order["user_id"],
                        document=profile_file,
                        filename=file_name,
                        caption=(
                            f"📥 <b>HỒ SƠ CẤU HÌNH DNS ({pv['name']})</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Tài khoản: <b>@{order.get('display_name', order.get('uid'))}</b>\n\n"
                            f"⚡ <b>Cài đặt 1 chạm trên iPhone:</b>\n"
                            f"1️⃣ Bấm vào file đính kèm trên để tải về\n"
                            f"2️⃣ Bấm <b>\"Cho phép\" (Allow)</b>\n"
                            f"3️⃣ Mở <b>Cài đặt (Settings) iPhone</b> → <b>Đã tải về hồ sơ</b> → Bấm <b>Cài đặt</b> là xong!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.error(f"Error sending customer delivery: {e}")

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
