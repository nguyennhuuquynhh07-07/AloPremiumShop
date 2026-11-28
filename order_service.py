"""
order_service.py – Logic xử lý đơn hàng tập trung (Locket Gold & Spotify Premium)
Tự động kích hoạt bản quyền qua API CTV, cấp DNS profile và thông báo.
"""

import io
import logging
import math
import asyncio
import re
import threading
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
PAYMENT_WINDOW_SECONDS = 300
AUTO_ACTIVATE_WINDOW_SECONDS = 1800  # 30 phút ân hạn tự động kích hoạt nếu khách chuyển chậm vài phút
_processing_orders = set()
_processing_lock = threading.Lock()
_sepay_fetch_lock = threading.Lock()
_sepay_scan_lock = threading.Lock()


def _resolve_dns_url() -> str:
    """Lấy URL DNS hồ sơ chính chủ từ cấu hình động."""
    cur_base = str(getattr(config, "DNS_BASE_URL", DNS_BASE_URL) or "").strip()
    cur_slug = str(getattr(config, "DNS_SLUG", DNS_SLUG) or "").strip()
    if cur_base and cur_slug:
        return f"{cur_base}/{cur_slug}"
    return str(getattr(config, "DNS_COMBO_URL", "https://doh.2707226.xyz/alopremiumshop") or "https://doh.2707226.xyz/alopremiumshop").strip()


def resolve_order_product_meta(order: dict) -> tuple[dict, dict]:
    """Lấy metadata (name, emoji, label, price) an toàn cho mọi loại đơn (bao gồm studio_caption, filter_topup)."""
    product_key = order.get("product", "")
    plan_key = order.get("plan", "")
    if product_key == "studio_caption":
        return (
            {"name": "Studio Chỉnh Chú Thích & Khung Viền", "emoji": "🎨", "service": "studio"},
            {"label": "Bản Quyền Vĩnh Viễn", "packageCode": "STUDIO", "price": order.get("price", 10000)},
        )
    if product_key == "filter_topup":
        pack_info = getattr(config, "FILTER_TOPUP_PACKS", {}).get(str(plan_key), {})
        turns = pack_info.get("turns") or (int(plan_key) if str(plan_key).isdigit() else 20)
        label = order.get("plan_label") or pack_info.get("label") or f"Gói {turns} Lượt Filter AI"
        return (
            {"name": "Nạp Lượt Filter AI", "emoji": "🎭", "service": "filter_topup"},
            {"label": label, "packageCode": f"FILTER_{plan_key}", "price": order.get("price", pack_info.get("price", 7000))},
        )
    if product_key == "caption_pack":
        pack_info = getattr(config, "CAPTION_TOPUP_PACKS", {}).get(str(plan_key), {})
        caps = pack_info.get("captions") or (int(plan_key) if str(plan_key).isdigit() else 10)
        label = order.get("plan_label") or pack_info.get("label") or f"Gói +{caps} Caption VIP"
        return (
            {"name": "Mua Thêm Caption VIP", "emoji": "💬", "service": "caption_pack"},
            {"label": label, "packageCode": f"CAPTION_{plan_key}", "price": order.get("price", pack_info.get("price", 5000))},
        )
    pv = PRODUCTS.get(product_key, {"name": str(product_key or "Dịch vụ VIP"), "emoji": "📦", "plans": {}})
    plnv = pv.get("plans", {}).get(plan_key, {"label": order.get("plan_label") or str(plan_key or "VIP"), "price": order.get("price", 0)})
    return pv, plnv


def payment_deadline(order: dict) -> float | None:
    try:
        return datetime.fromisoformat(order["created_at"].replace("Z", "+00:00")).timestamp() + PAYMENT_WINDOW_SECONDS
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


def auto_activate_deadline(order: dict) -> float | None:
    try:
        return datetime.fromisoformat(order["created_at"].replace("Z", "+00:00")).timestamp() + AUTO_ACTIVATE_WINDOW_SECONDS
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


def payment_matches_order(order: dict, account: str, content: str, amount: float) -> bool:
    shop_account = str(getattr(config, "ACCOUNT_NO", "")).strip()
    raw_oid = str(order.get("order_id") or "").upper().strip()
    if not raw_oid or not shop_account or str(account or "").strip() != shop_account:
        return False
    if not (math.isfinite(amount) and 0 < order.get("price", 0) <= amount):
        return False

    norm_content = re.sub(r"\s+", " ", str(content or "").upper()).strip()
    escaped_oid = re.escape(raw_oid)
    # TPBank / VietQR hay bỏ dấu gạch dưới "_" (ORDER_KIENI1D7 -> ORDERKIENI1D7) hoặc thay bằng dấu cách
    if re.search(rf"(?<![A-Z0-9])(?:ORDER[_\s-]?)?{escaped_oid}(?![A-Z0-9])", norm_content):
        return True

    # Hỗ trợ thêm các mã đơn cũ từng sinh ký tự 0/O hoặc 1/I nếu ngân hàng/khách gõ nhầm
    if len(raw_oid) >= 6:
        fuzzy_oid = "".join(
            "[0O]" if ch in ("0", "O") else ("[1I]" if ch in ("1", "I") else re.escape(ch))
            for ch in raw_oid
        )
        if re.search(rf"(?<![A-Z0-9])(?:ORDER[_\s-]?)?{fuzzy_oid}(?![A-Z0-9])", norm_content):
            return True
    return False


def is_zalo_group_eligible_order(order: dict | None) -> bool:
    """Chỉ gửi nhắc nhở tham gia Nhóm Zalo cho gói 6 Tháng, 1 Năm hoặc Vĩnh Viễn (ẩn với gói 5k / Test 3 Ngày / gói lẻ)."""
    if not isinstance(order, dict):
        return False
    prod = str(order.get("product") or "").strip().lower()
    plan = str(order.get("plan") or "").strip().lower()
    if prod in ("filter_topup", "caption_pack", "studio_caption"):
        return False
    if plan == "test":
        return False
    if prod == "locket_ai":
        return True
    if plan in ("6m", "1y", "ltm"):
        return True
    return False


async def _send_zalo_group_reminder(bot, chat_id: int) -> None:
    """Gửi nhắc nhở khách tham gia nhóm Zalo kèm ảnh QR (nếu có) sau khi thanh toán thành công."""
    zalo_url = getattr(config, "ZALO_GROUP_URL", "").strip()
    zalo_qr = getattr(config, "ZALO_GROUP_QR", "zalo_group_qr.png").strip()

    # Tạo nội dung tin nhắn nhắc nhở
    reminder_text = (
        "👥 <b>THAM GIA NHÓM ZALO HỖ TRỢ — ALOPREMIUM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 Cảm ơn bạn đã mua hàng tại AloPremium!\n\n"
        "📢 Hãy tham gia <b>Nhóm Zalo</b> của chúng tôi để:\n"
        "• Nhận <b>hỗ trợ kỹ thuật nhanh nhất</b> 24/7\n"
        "• Cập nhật <b>khuyến mãi & mã giảm giá VIP</b> độc quyền\n"
        "• Giao lưu cùng cộng đồng người dùng AloPremium\n"
    )
    if zalo_url:
        reminder_text += f"\n🔗 Link tham gia: <a href='{zalo_url}'>{zalo_url}</a>"
    reminder_text += "\n\n📱 <i>Quét mã QR bên dưới bằng Zalo để vào nhóm ngay!</i>"

    # Tạo nút bấm
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = []
        if zalo_url:
            buttons.append([InlineKeyboardButton("👥 Vào Nhóm Zalo Ngay", url=zalo_url)])
        support_phone = getattr(config, "SUPPORT_PHONE", "").strip()
        if support_phone:
            buttons.append([InlineKeyboardButton(f"📞 Hotline / Zalo CSKH: {support_phone}", url=f"https://zalo.me/{support_phone}")])
        kb = InlineKeyboardMarkup(buttons) if buttons else None
    except Exception:
        kb = None

    # Gửi ảnh QR nhóm Zalo nếu tồn tại file
    qr_sent = False
    if zalo_qr:
        import os
        # Thử tìm file QR ở nhiều vị trí
        qr_candidates = [
            zalo_qr,
            os.path.join(os.path.dirname(__file__), zalo_qr),
            os.path.join(os.path.dirname(__file__), "assets", zalo_qr),
        ]
        for qr_path in qr_candidates:
            if os.path.isfile(qr_path):
                try:
                    with open(qr_path, "rb") as f:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=f,
                            caption=reminder_text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=kb,
                        )
                    qr_sent = True
                    break
                except Exception as e_qr:
                    logger.warning(f"Could not send Zalo QR photo: {e_qr}")

    # Nếu không gửi được ảnh QR, gửi tin nhắn text thường
    if not qr_sent:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=reminder_text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception as e_txt:
            logger.warning(f"Could not send Zalo group reminder: {e_txt}")


async def execute_order_activation(bot, order_id: str) -> tuple[bool, str]:
    with _processing_lock:
        if order_id in _processing_orders:
            return False, "Đơn hàng đang được xử lý."
        _processing_orders.add(order_id)
    try:
        return await _execute_order_activation(bot, order_id)
    finally:
        with _processing_lock:
            _processing_orders.discard(order_id)


async def _execute_order_activation(bot, order_id: str) -> tuple[bool, str]:
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
    elif product_key == "filter_topup":
        pack_info = getattr(config, "FILTER_TOPUP_PACKS", {}).get(str(plan_key), {})
        turns = pack_info.get("turns") or (int(plan_key) if str(plan_key).isdigit() else 20)
        label = pack_info.get("label") or f"Gói {turns} Lượt Filter AI"
        pv = {"name": "Nạp Lượt Filter AI", "emoji": "🎭", "service": "filter_topup"}
        plnv = {"label": label, "packageCode": f"FILTER_{plan_key}", "price": order.get("price", pack_info.get("price", 7000))}
    elif product_key == "caption_pack":
        pack_info = getattr(config, "CAPTION_TOPUP_PACKS", {}).get(str(plan_key), {})
        caps = pack_info.get("captions") or (int(plan_key) if str(plan_key).isdigit() else 10)
        label = order.get("plan_label") or pack_info.get("label") or f"Gói +{caps} Caption VIP"
        pv = {"name": "Mua Thêm Caption VIP", "emoji": "💬", "service": "caption_pack"}
        plnv = {"label": label, "packageCode": f"CAPTION_{plan_key}", "price": order.get("price", pack_info.get("price", 5000))}
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
        dns_link = _resolve_dns_url()
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
        elif product_key == "filter_topup":
            # Gói nạp thêm lượt Filter AI (7k/17k/33k) - đối soát tự động SePay và Admin cộng lượt trực tiếp
            db.update_order(
                order_id,
                status="done",
                done_at=datetime.now().isoformat(),
            )
        elif product_key == "caption_pack":
            # Gói mua thêm Caption VIP (+10: 5.000đ, +30: 10.000đ) -> cộng quota tự động 100%
            pack_caps = int(order.get("caption_amount") or (30 if str(plan_key) == "30" else 10))
            locket_uid = str(order.get("locket_uid") or "").strip()
            uname = str(order.get("account_target") or order.get("display_name") or order.get("uid") or "").strip().lstrip("@")
            db.add_caption_quota(uid=locket_uid, extra_captions=pack_caps, username=uname, order_id=order_id)
            db.update_order(
                order_id,
                status="done",
                done_at=datetime.now().isoformat(),
            )
        elif product_key in ("combo", "locket_spotify"):
            # GÓI COMBO DUO CHÍNH CHỦ (LOCKET + SPOTIFY QUA API CTV locket.2707226.xyz)
            dns_base = _resolve_dns_url()
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

            # 1. Kích hoạt Locket trên web chính
            locket_ok = False
            last_lk_err = None
            lk_res = None
            for acc in candidate_accounts:
                try:
                    lk_res = await asyncio.to_thread(
                        api.create_subscription,
                        uid=acc,
                        package_code=pkg_map["locket"],
                        service="locket",
                        note=f"Combo {order_id} Locket"
                    )
                    locket_ok = True
                    target_account = acc
                    break
                except Exception as e_lk:
                    last_lk_err = e_lk
                    logger.warning(f"Combo Locket API ({acc}): {e_lk}")

            # 2. Kích hoạt Spotify trên web chính (ưu tiên spotify_uid khách điền ở dòng 2)
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

            spotify_ok = False
            last_sp_err = None
            sp_res = None
            for sp_acc in sp_candidates:
                try:
                    sp_res = await asyncio.to_thread(
                        api.create_subscription,
                        uid=sp_acc,
                        package_code=pkg_map["spotify"],
                        service="spotify",
                        note=f"Combo {order_id} Spotify"
                    )
                    spotify_ok = True
                    break
                except Exception as e_sp:
                    last_sp_err = e_sp
                    logger.warning(f"Combo Spotify API ({sp_acc}): {e_sp}")

            if not locket_ok and last_lk_err:
                logger.error(f"Combo Locket activation failed: {last_lk_err}")
                if not spotify_ok:
                    return False, str(last_lk_err or "Kích hoạt Combo thất bại")

            combo_update = {
                "status": "done",
                "done_at": datetime.now().isoformat(),
                "dns_link": dns_base,
                "dns_link_locket": dns_base,
                "dns_link_spotify": dns_base,
            }
            total_coin = 0
            for sub_res, sub_key in ((lk_res, "locket"), (sp_res, "spotify")):
                if not isinstance(sub_res, dict):
                    continue
                sub_data = sub_res.get("data") if isinstance(sub_res.get("data"), dict) else sub_res
                u_obj = sub_data.get("uid") if isinstance(sub_data.get("uid"), dict) else {}
                o_obj = sub_data.get("order") if isinstance(sub_data.get("order"), dict) else {}
                exp_val = u_obj.get("expiresAt") or o_obj.get("expiresAt")
                if exp_val and not combo_update.get("expires_at"):
                    combo_update["expires_at"] = exp_val
                if sub_key == "locket" and u_obj.get("uidString"):
                    combo_update["locket_uid"] = str(u_obj["uidString"]).strip()
                if sub_key == "spotify" and u_obj.get("uidString"):
                    combo_update["spotify_uid"] = str(u_obj["uidString"]).strip()
                try:
                    total_coin += float(o_obj.get("priceCoin") or 0)
                except (TypeError, ValueError):
                    pass
            if total_coin > 0:
                combo_update["ctv_cost_coin"] = total_coin

            db.update_order(order_id, **combo_update)
        else:
            pkg_code = str(plnv.get("packageCode") or "").strip().upper()
            is_test_3d = (plan_key == "test" or pkg_code in ("LKGT3D", "SPT"))
            if is_test_3d:
                # Mỗi tài khoản chỉ được dùng thử gói Test 3 Ngày duy nhất 1 lần (chặn lần 2)
                trial_cands = list(candidate_accounts)
                if order.get("locket_uid"):
                    trial_cands.append(str(order["locket_uid"]))
                if utils.has_used_test_trial(product_key, trial_cands, exclude_order_id=order_id):
                    return False, "Mỗi tài khoản chỉ được dùng thử gói Test 3 Ngày 1 lần! Tài khoản này đã dùng thử trước đó."

            # Gói Locket hoặc Spotify đơn lẻ: tự động fallback các candidate nếu dính 404
            act_success = False
            last_err = None
            result = None
            for acc in candidate_accounts:
                try:
                    result = await asyncio.to_thread(
                        api.create_subscription,
                        uid=acc,
                        package_code=plnv["packageCode"],
                        service=pv["service"],
                        note=f"Order {order_id} via {order.get('source', 'Bot/Web')}"
                    )
                    act_success = True
                    target_account = acc
                    if acc != order.get("uid"):
                        db.update_order(order_id, uid=acc, account_target=acc)
                    break
                except Exception as e_act:
                    last_err = e_act
                    err_status = getattr(e_act, "status_code", None)
                    err_str = str(e_act).lower()
                    if err_status != 404 and "404" not in err_str and "không tồn tại" not in err_str:
                        # Nếu không phải lỗi 404 không tồn tại (vd: hết coin 402, 401, 409...) thì ngắt ngay
                        break
            if not act_success:
                return False, str(last_err or "Kích hoạt thất bại")

            single_update = {
                "status": "done",
                "done_at": datetime.now().isoformat(),
                "dns_link": dns_link,
            }
            if isinstance(result, dict):
                res_data = result.get("data") if isinstance(result.get("data"), dict) else result
                u_obj = res_data.get("uid") if isinstance(res_data.get("uid"), dict) else {}
                o_obj = res_data.get("order") if isinstance(res_data.get("order"), dict) else {}
                exp_val = u_obj.get("expiresAt") or o_obj.get("expiresAt")
                if exp_val:
                    single_update["expires_at"] = exp_val
                if u_obj.get("uidString"):
                    single_update["upstream_uid"] = str(u_obj["uidString"]).strip()
                    if product_key == "locket" and not order.get("locket_uid"):
                        single_update["locket_uid"] = str(u_obj["uidString"]).strip()
                if o_obj.get("priceCoin") is not None:
                    single_update["ctv_cost_coin"] = o_obj.get("priceCoin")

            db.update_order(order_id, **single_update)

        order = db.get_order(order_id) or order
        db.record_sale(product_key, plan_key, order["price"])

        # Trừ lượt mã giảm giá chỉ khi thanh toán & kích hoạt thành công (chống spam đốt mã)
        applied_coupon = str(order.get("discount_code") or "").strip().upper()
        if applied_coupon and not order.get("coupon_counted"):
            db.use_code(applied_coupon)
            db.update_order(order_id, coupon_counted=True)

        # Tự động dọn tin nhắn [ĐƠN HÀNG WEB MỚI] cũ (có nút Duyệt/Từ chối) để tránh nhầm lẫn
        if bot and order.get("admin_alert_messages"):
            for alert_ref in order.get("admin_alert_messages", []):
                try:
                    c_id = alert_ref.get("chat_id")
                    m_id = alert_ref.get("message_id")
                    if c_id and m_id:
                        await bot.delete_message(chat_id=c_id, message_id=m_id)
                except Exception:
                    pass
            db.update_order(order_id, admin_alert_messages=[])

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

            elif product_key == "filter_topup":
                from keyboards import locket_ai_success_kb
                username_target = utils.clean_input(str(order.get("uid") or order.get("username") or order.get("account_target") or order.get("display_name") or "")).lstrip("@")
                filter_msg = (
                    f"🎭 <b>THANH TOÁN THÀNH CÔNG GÓI NẠP LƯỢT FILTER AI!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📦 <b>Gói:</b> {plnv['label']}\n"
                    f"👤 <b>Tài khoản Locket:</b> @{username_target}\n"
                    f"🆔 <b>Mã đơn hàng:</b> <code>ORDER_{order.get('order_id')}</code>\n"
                    f"💵 <b>Số tiền đã thanh toán:</b> {utils.fmt_price(order['price'])}\n"
                    f"⚡ <i>Hệ thống đã ghi nhận thanh toán. Admin sẽ cộng lượt chụp Filter AI vào tài khoản cho bạn ngay!</i>"
                )
                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=filter_msg,
                        parse_mode=ParseMode.HTML,
                        reply_markup=locket_ai_success_kb(order_id=order.get('order_id'))
                    )
                except Exception as e_ft_send:
                    logger.error(f"Error sending Filter Topup delivery: {e_ft_send}")

            elif product_key in ("combo", "locket_spotify"):
                dns_base = _resolve_dns_url()
                try:
                    qr_combo = utils.generate_qr_code(dns_base)
                    await bot.send_photo(
                        chat_id=order["user_id"],
                        photo=qr_combo,
                        caption=(
                            f"👑 <b>MÃ QR CẤU HÌNH: COMBO DUO VIP</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 Khách hàng: <b>@{uid_display}</b>\n"
                            f"📦 Gói: <b>Combo Duo VIP ({plnv.get('label', 'Vĩnh Viễn')})</b>\n\n"
                            f"⚡ <b>Cách cài đặt:</b>\n"
                            f"1️⃣ Dùng <b>Camera iPhone</b> quét mã QR trên màn hình.\n"
                            f"2️⃣ Chạm vào thông báo vàng <b>\"Mở trong Safari\"</b> để cài cấu hình dùng song song cả Locket Gold & Spotify!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e_qr:
                    logger.warning(f"Could not send Combo Duo QR photo: {e_qr}")

                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=combo_success_kb(dns_base, dns_base)
                    )
                except Exception as e:
                    logger.error(f"Error sending Combo Duo delivery: {e}")

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
        # ── GỬI NHẮC NHỞ THAM GIA NHÓM ZALO SAU KHI THANH TOÁN THÀNH CÔNG (CHỈ GÓI 6M / 1Y / LTM) ──
        if bot and isinstance(order.get("user_id"), int) and order.get("user_id") > 0 and is_zalo_group_eligible_order(order):
            await _send_zalo_group_reminder(bot, order["user_id"])

        if bot:
            if product_key == "filter_topup":
                admin_header = "🎭 <b>[CẦN CỘNG LƯỢT FILTER AI — ĐÃ THANH TOÁN]</b>"
            elif product_key == "caption_pack":
                admin_header = "💬 <b>[ĐÃ CỘNG QUOTA CAPTION TỰ ĐỘNG]</b>"
            else:
                admin_header = "💰 <b>[KÍCH HOẠT THÀNH CÔNG]</b>"
            coin_line = f"\n• Phí API: <b>{order.get('ctv_cost_coin')} Coin</b>" if order.get("ctv_cost_coin") is not None else ""
            exp_line = f"\n• Hết hạn: <code>{utils.fmt_datetime(order.get('expires_at'))}</code>" if order.get("expires_at") and not str(order.get("expires_at")).startswith("2099") else ""
            for aid in config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=aid,
                        text=(
                            f"{admin_header}\n"
                            f"• Mã đơn: <code>ORDER_{order_id}</code>\n"
                            f"• Gói: <b>{pv['name']} ({plnv['label']})</b>\n"
                            f"• Khách: {order.get('display_name')} (<code>@{order.get('uid')}</code>)\n"
                            f"• Nguồn: <b>{order.get('source', 'Telegram').upper()}</b>\n"
                            f"• Số tiền: <b>{utils.fmt_price(order['price'])}</b>{coin_line}{exp_line}"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

        if product_key == "filter_topup":
            return True, "Đã xác nhận thanh toán gói Nạp Lượt Filter AI!"
        if product_key == "caption_pack":
            return True, f"Đã cộng thêm lượt Caption ({plnv['label']}) tự động!"
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
    """Tải danh sách 20 giao dịch mới nhất từ SePay API, có bộ nhớ đệm 3s và khóa chống gọi trùng"""
    token = getattr(config, "SEPAY_API_TOKEN", "")
    if not token:
        return []

    with _sepay_fetch_lock:
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
                    _SEPAY_CACHE["timestamp"] = time.time()
                    _SEPAY_CACHE["transactions"] = txs
                    return txs
                logger.warning(f"SePay API returned HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"Error fetching SePay transactions: {e}")
        return _SEPAY_CACHE.get("transactions", [])


def register_verified_payment(order: dict, tx_id: str, amount: float) -> str | None:
    deadline = auto_activate_deadline(order)
    return db.register_order_payment(
        order["order_id"], tx_id, amount, on_time=deadline is not None and time.time() < deadline
    )


async def process_registered_payment(bot, order_id: str, action: str) -> None:
    err_detail = ""
    if action == "process":
        ok, err_detail = await execute_order_activation(bot, order_id)
        if ok:
            return
    if not bot:
        return

    order = db.get_order(order_id)
    if not order:
        return
    try:
        from keyboards import admin_approval_kb
        adm_kb = admin_approval_kb(order_id)
    except Exception:
        adm_kb = None

    reason_line = f"\n⚠️ Lý do chưa tự kích hoạt: <code>{err_detail}</code>" if err_detail else ""
    err_low = str(err_detail or "").lower()
    hint_line = ""
    if "402" in err_low or "coin" in err_low or "insufficient" in err_low:
        hint_line = "\n🚨 <b>KHẨN: Ví Coin CTV không đủ! Vui lòng nạp Coin trên locket.2707226.xyz rồi bấm Duyệt lại.</b>"
    elif "401" in err_low or "403" in err_low or "unauthorized" in err_low:
        hint_line = "\n🚨 <b>KHẨN: Lỗi Secret Key hoặc tài khoản CTV chưa kích hoạt 150K!</b>"
    elif "409" in err_low or "người khác" in err_low:
        hint_line = "\n⚠️ <b>Lưu ý: UID đang thuộc về CTV khác còn hạn dùng!</b>"

    for aid in getattr(config, "ADMIN_IDS", []):
        try:
            await bot.send_message(
                chat_id=aid,
                text=(
                    f"💳 <b>ĐÃ NHẬN TIỀN ĐƠN <code>ORDER_{order_id}</code> (CẦN KIỂM TRA)</b>\n"
                    f"• Tài khoản: <b>{order.get('display_name') or order.get('uid')}</b>\n"
                    f"• Số tiền: <b>{utils.fmt_price(order.get('price', 0))}</b>{reason_line}{hint_line}\n"
                    f"👉 Bấm nút bên dưới để kích hoạt lại nếu cần."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=adm_kb,
            )
        except Exception:
            logger.warning("Could not send admin payment review alert for %s", order_id)

    if order.get("user_id", 0) > 0:
        try:
            await bot.send_message(
                chat_id=order["user_id"],
                text=f"Đã nhận tiền cho đơn ORDER_{order_id}. Đơn đang chờ đối soát. "
                     "Vui lòng giữ mã đơn và không chuyển khoản lại.",
            )
        except Exception:
            logger.warning("Could not send buyer payment review alert for %s", order_id)


def _scan_and_register_sepay_sync(force_refresh: bool = False) -> list[tuple[str, str]]:
    """Quét SePay và ghi nhận giao dịch đồng bộ dưới khóa luồng (không giữ khóa qua await)."""
    with _sepay_scan_lock:
        db.recover_order_payments()
        orders = db.get_orders()
        candidates = [
            order for order in orders.values()
            if order and order.get("status") in (*db.UNPAID_ORDER_STATUSES, "cancelled", "rejected")
        ]
        if not candidates:
            return []

        transactions = fetch_sepay_transactions(force_refresh=force_refresh)
        used_ids = db.get_used_tx_ids()
        matched_actions = []
        for tx in transactions:
            tx_id = str(tx.get("id", "")).strip()
            try:
                amount = float(tx.get("amount_in") or 0)
            except (ValueError, TypeError):
                continue
            if not tx_id or tx_id in used_ids:
                continue
            matches = [
                order for order in candidates if payment_matches_order(
                    order, str(tx.get("account_number", "")).strip(),
                    str(tx.get("transaction_content", "")), amount
                )
            ]
            if len(matches) == 1:
                order = matches[0]
                action = register_verified_payment(order, tx_id, amount)
                if action:
                    used_ids[tx_id] = {"order_id": order["order_id"]}
                    matched_actions.append((order["order_id"], action))
        return matched_actions


async def check_sepay_payments(bot=None, order_id=None, force_refresh: bool = False) -> None:
    if order_id:
        cur_order = db.get_order(order_id)
        if cur_order and cur_order.get("status") in ("done", "paid_review"):
            return

    matched_actions = await asyncio.to_thread(_scan_and_register_sepay_sync, force_refresh)
    for matched_oid, act in matched_actions:
        await process_registered_payment(bot, matched_oid, act)


def cancel_expired_pending_orders() -> list[str]:
    expired_ids = []
    now = time.time()
    for order_id, order in db.get_orders().items():
        if order.get("status") not in ("waiting_payment", "pending"):
            continue
        deadline = payment_deadline(order)
        if deadline is not None and now >= deadline and db.update_order(
            order_id, expected_statuses=("waiting_payment", "pending"),
            status="cancelled", cancel_reason="Hết thời gian thanh toán (5 phút)",
        ):
            expired_ids.append(order_id)
    return expired_ids


_pkg_sync_lock = threading.Lock()
_last_pkg_sync_ts = 0.0
_PKG_SYNC_TTL = 300.0


def sync_upstream_package_specs(force: bool = False) -> bool:
    """
    Đồng bộ thời hạn (durationDays) và tên gói Test từ web chính (https://locket.2707226.xyz/api/packages?service=all)
    về config.PRODUCTS trong RAM (giữ nguyên giá bán lẻ VNĐ của shop).
    """
    global _last_pkg_sync_ts
    now = time.time()
    if not force and (now - _last_pkg_sync_ts) < _PKG_SYNC_TTL:
        return False
    if not _pkg_sync_lock.acquire(blocking=False):
        return False
    try:
        if not force and (time.time() - _last_pkg_sync_ts) < _PKG_SYNC_TTL:
            return False
        import api_client
        res = api_client.get_packages("all")
        items = res.get("data") or []
        if not isinstance(items, list) or not items:
            return False
        by_code = {
            str(item.get("code") or "").strip().upper(): item
            for item in items if isinstance(item, dict) and item.get("code")
        }
        updated = False
        for prod_val in config.PRODUCTS.values():
            plans = prod_val.get("plans") or {}
            for plan_key, plan_val in plans.items():
                if not isinstance(plan_val, dict):
                    continue
                code = str(plan_val.get("packageCode") or "").strip().upper()
                upstream = by_code.get(code)
                if not upstream:
                    continue
                try:
                    days = int(upstream.get("durationDays") or 0)
                except (TypeError, ValueError):
                    days = 0
                if days > 0:
                    plan_val["durationDays"] = days
                    if plan_key == "test" and days < 30:
                        new_label = f"Test {days} Ngày"
                        if plan_val.get("label") != new_label:
                            plan_val["label"] = new_label
                            updated = True
                if "priceCoin" in upstream:
                    plan_val["priceCoin"] = upstream.get("priceCoin", 0)
        _last_pkg_sync_ts = time.time()
        if updated:
            logger.info("🔄 Đã đồng bộ nhãn & thời hạn gói Test từ web chính API.")
        return True
    except Exception as e:
        logger.debug(f"sync_upstream_package_specs skipped: {e}")
        return False
    finally:
        _pkg_sync_lock.release()


def trigger_upstream_package_sync_bg() -> None:
    """Kích hoạt đồng bộ gói cước ở thread nền nếu cache đã hết hạn (không chặn request)."""
    if (time.time() - _last_pkg_sync_ts) < _PKG_SYNC_TTL:
        return
    threading.Thread(target=sync_upstream_package_specs, daemon=True).start()


def sync_upstream_orders() -> int:
    """
    Đồng bộ toàn bộ danh sách tài khoản đã kích hoạt từ máy chủ API CTV (web chủ)
    vào cơ sở dữ liệu nội bộ để khách hàng cũ có thể tra cứu và tải lại DNS bất cứ lúc nào.
    """
    sync_upstream_package_specs(force=True)
    try:
        import api_client
        uids = api_client.get_activated_uids(force_refresh=True)
        if not uids:
            return 0

        orders = db.get_orders()
        synced_count = 0
        changes = {}

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
            elif pkg_code in ("LKGT3D", "SPT") or "T3D" in pkg_code or "TEST" in pkg_name.upper():
                plan_key = "test"

            clean_u = username.lower().lstrip("@")
            clean_uid = uid_str.lower()
            matched_oid = None

            for oid, od in orders.items():
                if od.get("status") != "done":
                    continue
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
                changes[matched_oid] = orders[matched_oid]
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
                changes[new_oid] = orders[new_oid]
                synced_count += 1

        db.save_synced_orders(changes)
        logger.info(f"🔄 [SYNC WEB CHỦ] Đã đồng bộ thành công {len(uids)} tài khoản ({synced_count} đơn mới)!")
        return len(uids)
    except Exception as e:
        logger.error(f"Lỗi đồng bộ từ web chủ: {e}")
        return 0
