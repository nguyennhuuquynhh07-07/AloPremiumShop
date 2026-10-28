"""
order_service.py – Logic kích hoạt và hoàn tất đơn hàng tập trung
Dùng chung cho:
1. Admin duyệt đơn thủ công (bấm nút hoặc lệnh /duyet)
2. Tự động duyệt khi khách bấm "Tôi đã chuyển khoản" (nếu bật AUTO_APPROVE)
3. Tự động duyệt qua SePay quét biến động Techcombank
"""

import io
import logging
from datetime import datetime
from telegram.constants import ParseMode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import api_client as api
import utils
import config
from config import PRODUCTS, DNS_BASE_URL, DNS_SLUG, SERVER_BASE_URL
from locket_service import build_mobileconfig_xml

logger = logging.getLogger(__name__)


def build_guide_3in1_text(order: dict, download_url: str) -> str:
    """Tạo nội dung hướng dẫn kích hoạt chuẩn 3 bước cho gói 3-in-1"""
    return (
        f"🎉 <b>KÍCH HOẠT THÀNH CÔNG GÓI SIÊU VIP 3-IN-1!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Tài khoản:</b> {order.get('display_name')} (<code>@{order.get('uid')}</code>)\n"
        f"👑 <b>Gói dịch vụ đã mở:</b>\n"
        f"  • 💛 <b>Locket Gold Pro</b> (Vĩnh viễn)\n"
        f"  • 🎵 <b>Spotify Premium</b>\n"
        f"  • ▶️ <b>YouTube Premium</b> (Chặn QC + PiP nền)\n"
        f"🛡️ <b>Trạng thái:</b> ✅ <i>Đã thanh toán {utils.fmt_price(order['price'])}</i>\n\n"
        f"📋 <b>Link Tải Hồ Sơ Cấu Hình (Chạm để sao chép):</b>\n"
        f"<code>{download_url}</code>\n\n"
        f"📲 <b>HƯỚNG DẪN CÀI ĐẶT 3 BƯỚC TRÊN IPHONE:</b>\n"
        f"1️⃣ Copy link trên rồi mở <b>Safari</b> dán vào thanh địa chỉ để tải hồ sơ.\n"
        f"2️⃣ Bấm <b>Cho phép (Allow)</b> khi Safari hỏi.\n"
        f"3️⃣ Mở <b>Cài đặt (Settings) iPhone</b> → chọn <b>Đã tải về hồ sơ</b> (ngay dòng đầu) → bấm <b>Cài đặt</b>.\n"
        f"4️⃣ <b>Bật tin cậy Root CA:</b> Vào <b>Cài đặt chung</b> → <b>Giới thiệu</b> → <b>Cài đặt tin cậy chứng nhận</b> → Bật <b>XANH</b> công tắc cho <b>Locket Gold Root CA</b>.\n\n"
        f"✨ <i>Xong! Mở Locket, Spotify hoặc YouTube lên trải nghiệm ngay!</i>"
    )


async def execute_order_activation(bot, order_id: str) -> tuple[bool, str]:
    """
    Thực hiện kích hoạt gói và giao hàng tự động cho khách:
    - Gói 3-in-1: Tạo profile DoH + Root CA 2099 và gửi file .mobileconfig
    - Gói Locket / Spotify: Gọi API locket.2707226.xyz trừ Coin và gửi DNS Profile
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
        if product_key == "combo3in1":
            token = order.get("token") or order.get("uid") or "vip"
            download_url = order.get("download_url") or f"{SERVER_BASE_URL}/d/{token}"
            xml_str = build_mobileconfig_xml(
                username=order.get("display_name") or order.get("uid"),
                token=token,
                cf_url=SERVER_BASE_URL
            )

            db.update_order(order_id, status="done", done_at=datetime.now().isoformat(), download_url=download_url)
            db.record_sale(product_key, plan_key, order["price"])

            guide_text = build_guide_3in1_text(order, download_url)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Copy Link Tải Hồ Sơ", api_kwargs={"copy_text": {"text": download_url}})],
                [
                    InlineKeyboardButton("📖 Hướng Dẫn Cài Đặt Chi Tiết", callback_data="show_guide"),
                    InlineKeyboardButton("🏠 Menu Chính", callback_data="back_main")
                ]
            ])

            buf = io.BytesIO(xml_str.encode("utf-8"))
            buf.name = f"VipPro3in1_{order.get('uid', 'vip')}.mobileconfig"
            buf.seek(0)

            if bot and isinstance(order.get("user_id"), int) and order.get("user_id") > 0:
                try:
                    await bot.send_document(
                        chat_id=order["user_id"],
                        document=buf,
                        filename=buf.name,
                        caption=guide_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb
                    )
                except Exception:
                    try:
                        await bot.send_message(
                            chat_id=order["user_id"],
                            text=guide_text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=kb
                        )
                    except Exception:
                        pass

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
            return True, "Kích hoạt 3-in-1 thành công!"

        else:
            # Gói Locket Gold hoặc Spotify Premium qua API CTV
            target_account = order.get("account_target") or order.get("display_name") or order["uid"]
            result = api.create_subscription(
                uid=target_account,
                package_code=plnv["packageCode"],
                service=pv["service"],
                note=f"Order {order_id} via Telegram Bot"
            )

            dns_link = f"{DNS_BASE_URL}/{DNS_SLUG}"
            db.update_order(order_id, status="done", done_at=datetime.now().isoformat(), dns_link=dns_link)
            db.record_sale(product_key, plan_key, order["price"])

            from handlers.user_handlers import _build_success_message
            from keyboards import success_kb
            success_text = _build_success_message(order, pv, plnv, dns_link)

            if bot and isinstance(order.get("user_id"), int) and order.get("user_id") > 0:
                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=success_kb(dns_link)
                    )

                    profile_file = utils.generate_mobileconfig(
                        service_name=pv["name"],
                        display_name=order.get("display_name") or order.get("uid"),
                        dns_link=dns_link
                    )
                    safe_uid = (order.get("uid") or "vip").replace(" ", "_")
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

