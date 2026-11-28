"""
database.py – Quản lý dữ liệu JSON (đơn hàng, thống kê, người dùng, mã giảm giá)
"""

import json
import os
import tempfile
import threading
from datetime import datetime

_db_lock = threading.RLock()
UNPAID_ORDER_STATUSES = ("pending", "waiting_payment", "pending_approval")

from config import DB_ORDERS, DB_STATS

DB_USERS = "data/users.json"
DB_CODES = "data/codes.json"
DB_PRICES = "data/prices.json"
DB_BANNER = "data/banner.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _ensure(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _load(path: str, default):
    with _db_lock:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default


def _save(path: str, data):
    _ensure(path)
    with _db_lock:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(path), delete=False
        ) as f:
            temp_path = f.name
            try:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.close()
                os.replace(temp_path, path)
            finally:
                f.close()
                if os.path.exists(temp_path):
                    os.unlink(temp_path)


# ── ORDERS ────────────────────────────────────────────────────────────────────

def get_orders() -> dict:
    return _load(DB_ORDERS, {})


def save_orders(orders: dict):
    _save(DB_ORDERS, orders)


def save_synced_orders(changes: dict) -> None:
    if not changes:
        return
    with _db_lock:
        orders = get_orders()
        for order_id, order in changes.items():
            if order_id not in orders or orders[order_id].get("status") == "done":
                orders[order_id] = order
        save_orders(orders)


def create_order(order_id: str, user_id: int, username: str,
                 product: str, plan: str, price: int,
                 uid: str = "", display_name: str = "", **kwargs) -> dict:
    order = {
        "order_id":    order_id,
        "user_id":     user_id,
        "username":    username,
        "product":     product,
        "plan":        plan,
        "price":       price,
        "uid":         uid,           # UID / link tài khoản khách
        "display_name": display_name, # Tên hiển thị (lấy từ API check)
        "status":      "pending",     # pending | done | failed | rejected | cancelled
        "created_at":  datetime.now().isoformat(),
        "done_at":     None,
    }
    order.update(kwargs)
    with _db_lock:
        orders = get_orders()
        orders[order_id] = order
        save_orders(orders)
    return order


def update_order(order_id: str, *, expected_statuses=None, **kwargs) -> bool:
    with _db_lock:
        orders = get_orders()
        order = orders.get(order_id)
        if not order or (
            expected_statuses is not None and order.get("status") not in expected_statuses
        ):
            return False
        order.update(kwargs)
        save_orders(orders)
        return True


def get_order(order_id: str) -> dict | None:
    return get_orders().get(order_id)


def get_user_orders(user_id: int) -> list:
    return [o for o in get_orders().values() if o.get("user_id") == user_id]


# ── STATS ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    return _load(DB_STATS, {"total_orders": 0, "total_revenue": 0, "products": {}})


def record_sale(product: str, plan: str, price: int):
    with _db_lock:
        stats = get_stats()
        stats["total_orders"]  += 1
        stats["total_revenue"] += price
        prod = stats["products"].setdefault(product, {})
        entry = prod.setdefault(plan, {"orders": 0, "revenue": 0})
        entry["orders"]  += 1
        entry["revenue"] += price
        _save(DB_STATS, stats)


# ── USERS ─────────────────────────────────────────────────────────────────────

def get_users() -> dict:
    with _db_lock:
        users = _load(DB_USERS, None)
        if users is None:
            users = {}
            # Tự động đồng bộ các user đã từng đặt đơn hàng từ trước
            orders = get_orders()
            for o in orders.values():
                uid = str(o.get("user_id"))
                if uid and uid not in users:
                    users[uid] = {
                        "user_id": o.get("user_id"),
                        "username": o.get("username", ""),
                        "first_name": o.get("username", "Người dùng"),
                        "last_name": "",
                        "lang": "vi",
                        "joined_at": o.get("created_at", datetime.now().isoformat()),
                        "is_banned": False,
                        "ban_reason": "",
                    }
            _save(DB_USERS, users)
        return users


def save_users(users: dict):
    _save(DB_USERS, users)


def get_user(user_id: int | str) -> dict | None:
    users = get_users()
    return users.get(str(user_id))


def upsert_user(user_id: int | str, username: str = "", first_name: str = "", last_name: str = "") -> dict:
    with _db_lock:
        users = get_users()
        key = str(user_id)
        if key not in users:
            users[key] = {
                "user_id": int(user_id),
                "username": username or "",
                "first_name": first_name or "",
                "last_name": last_name or "",
                "lang": "vi",
                "joined_at": datetime.now().isoformat(),
                "is_banned": False,
                "ban_reason": "",
            }
        else:
            if username:
                users[key]["username"] = username
            if first_name:
                users[key]["first_name"] = first_name
            if last_name:
                users[key]["last_name"] = last_name
        save_users(users)
        return users[key]


def ban_user(user_id: int | str, reason: str = "Vi phạm chính sách bot") -> bool:
    with _db_lock:
        users = get_users()
        key = str(user_id)
        if key not in users:
            users[key] = {
                "user_id": int(user_id),
                "username": "",
                "first_name": f"User {user_id}",
                "last_name": "",
                "lang": "vi",
                "joined_at": datetime.now().isoformat(),
                "is_banned": True,
                "ban_reason": reason,
            }
        else:
            users[key]["is_banned"] = True
            users[key]["ban_reason"] = reason
        save_users(users)
        return True


def unban_user(user_id: int | str) -> bool:
    with _db_lock:
        users = get_users()
        key = str(user_id)
        if key in users:
            users[key]["is_banned"] = False
            users[key]["ban_reason"] = ""
            save_users(users)
            return True
        return False


def is_banned(user_id: int | str) -> tuple[bool, str]:
    user = get_user(user_id)
    if user and user.get("is_banned", False):
        return True, user.get("ban_reason", "Vi phạm điều khoản dịch vụ")
    return False, ""


def set_user_lang(user_id: int | str, lang: str):
    with _db_lock:
        users = get_users()
        key = str(user_id)
        if key in users:
            users[key]["lang"] = lang
            save_users(users)


def get_user_lang(user_id: int | str) -> str:
    user = get_user(user_id)
    if user:
        return user.get("lang", "vi")
    return "vi"


# ── DISCOUNT CODES ────────────────────────────────────────────────────────────

def get_codes() -> dict:
    return _load(DB_CODES, {})


def save_codes(codes: dict):
    _save(DB_CODES, codes)


def add_codes_batch(code_list: list, discount_pct: int, max_uses: int = 0) -> list:
    with _db_lock:
        codes = get_codes()
        created = []
        now_iso = datetime.now().isoformat()
        for code in code_list:
            code_clean = (code or "").strip().upper()
            if len(code_clean) >= 2:
                data = {
                    "code": code_clean,
                    "discount_pct": discount_pct,
                    "max_uses": max_uses,
                    "used_count": 0,
                    "created_at": now_iso,
                    "active": True,
                }
                codes[code_clean] = data
                created.append(data)
        save_codes(codes)
        return created


def add_code(code: str, discount_pct: int, max_uses: int = 0) -> dict:
    code_clean = (code or "").strip().upper()
    if not code_clean:
        return {}
    with _db_lock:
        codes = get_codes()
        data = {
            "code": code_clean,
            "discount_pct": discount_pct,
            "max_uses": max_uses,
            "used_count": 0,
            "created_at": datetime.now().isoformat(),
            "active": True,
        }
        codes[code_clean] = data
        save_codes(codes)
        return data


def del_code(code: str) -> bool:
    with _db_lock:
        codes = get_codes()
        code_clean = code.strip().upper()
        if code_clean in codes:
            del codes[code_clean]
            save_codes(codes)
            return True
        return False


def get_code(code: str) -> dict | None:
    codes = get_codes()
    return codes.get(code.strip().upper())


def use_code(code: str) -> bool:
    with _db_lock:
        codes = get_codes()
        code_clean = code.strip().upper()
        if code_clean in codes:
            item = codes[code_clean]
            if item.get("max_uses", 0) > 0 and item.get("used_count", 0) >= item["max_uses"]:
                return False
            item["used_count"] = item.get("used_count", 0) + 1
            save_codes(codes)
            return True
        return False


# ── SEARCH / FIND ─────────────────────────────────────────────────────────────

def find_all(query: str) -> dict:
    """
    Tìm kiếm theo: telegram id, username, order_id, uid locket/spotify
    """
    q = query.strip().lower()
    matched_users = []
    matched_orders = []

    # Tìm trong Users
    for u in get_users().values():
        if (q in str(u.get("user_id", "")).lower() or
            q in str(u.get("username", "")).lower() or
            q in str(u.get("first_name", "")).lower()):
            matched_users.append(u)

    # Tìm trong Orders
    for o in get_orders().values():
        if (q in str(o.get("order_id", "")).lower() or
            q in str(o.get("uid", "")).lower() or
            q in str(o.get("username", "")).lower() or
            q in str(o.get("display_name", "")).lower() or
            q in str(o.get("user_id", "")).lower()):
            matched_orders.append(o)

    return {
        "users": matched_users,
        "orders": matched_orders,
    }


# ── TRANSACTIONS (CHỐNG REPLAY ATTACK & GIAN LẬN THANH TOÁN) ──────────────────

DB_TX = "data/used_transactions.json"

def get_used_tx_ids() -> dict:
    return _load(DB_TX, {})

def is_tx_used(tx_id: str) -> bool:
    if not tx_id:
        return False
    return str(tx_id) in get_used_tx_ids()

def mark_tx_used(tx_id: str, order_id: str):
    if not tx_id:
        return
    with _db_lock:
        txs = get_used_tx_ids()
        txs[str(tx_id)] = {
            "order_id": order_id,
            "used_at": datetime.now().isoformat()
        }
        _save(DB_TX, txs)


def register_order_payment(order_id: str, tx_id: str, amount: float, *, on_time: bool) -> str | None:
    """Persist verified payment before handing a new, on-time or grace-period order off for processing."""
    if not tx_id:
        return None
    with _db_lock:
        order = get_order(order_id)
        if not order or not (0 < order.get("price", 0) <= amount):
            return None
        status = order.get("status")
        if status not in (*UNPAID_ORDER_STATUSES, "cancelled", "rejected"):
            return None
        existing = get_used_tx_ids().get(tx_id)
        if existing and existing.get("order_id") != order_id:
            return None
        if not existing:
            mark_tx_used(tx_id, order_id)
        update_order(order_id, status="paid_review", payment_tx_id=str(tx_id), paid_amount=amount)
        # Đơn quá hạn 5 phút nhưng chưa bị Admin từ chối (tự hủy timeout) vẫn cho phép autobank kích hoạt tự động trong cửa sổ ân hạn
        eligible_statuses = (*UNPAID_ORDER_STATUSES, "cancelled")
        return "process" if not existing and on_time and status in eligible_statuses else "review"


def recover_order_payments() -> None:
    """Restore paid status from the existing ledger after an interrupted write or older failure."""
    with _db_lock:
        orders = get_orders()
        changed = False
        for payment in get_used_tx_ids().values():
            order = orders.get(payment.get("order_id"))
            if order and order.get("status") in (*UNPAID_ORDER_STATUSES, "cancelled", "rejected"):
                order["status"] = "paid_review"
                changed = True
        if changed:
            save_orders(orders)



# ── CAPTION QUOTA MANAGEMENT (5 MIỄN PHÍ + MUA THÊM 10/30 CAPTION) ──────────

DB_CAPTION_QUOTAS = "data/caption_quotas.json"


def _normalize_caption_quota_keys(uid: str = "", username: str = "") -> tuple[str, str]:
    uid_clean = str(uid or "").strip()
    uname_clean = str(username or "").strip().lower().lstrip("@")
    return uid_clean, uname_clean


def get_caption_quota_info(uid: str, username: str = "") -> dict:
    import config
    free_quota = int(getattr(config, "FREE_CAPTION_QUOTA", 5))
    uid_k, uname_k = _normalize_caption_quota_keys(uid, username)
    with _db_lock:
        quotas = _load(DB_CAPTION_QUOTAS, {})
        extra_total = 0
        granted_orders = []
        seen_orders = set()
        for k in dict.fromkeys([x for x in (uid_k, uname_k) if x]):
            entry = quotas.get(k)
            if not isinstance(entry, dict):
                continue
            entry_orders = entry.get("granted_orders") or []
            if entry_orders:
                for oid in entry_orders:
                    if oid not in seen_orders:
                        seen_orders.add(oid)
                        granted_orders.append(oid)
                extra_total += int(entry.get("extra_quota", 0))
            else:
                extra_total = max(extra_total, int(entry.get("extra_quota", 0)))
        return {
            "free_quota": free_quota,
            "extra_quota": extra_total,
            "total_quota": free_quota + extra_total,
            "granted_orders": granted_orders,
        }


def add_caption_quota(uid: str, extra_captions: int, username: str = "", order_id: str = "") -> dict:
    import config
    free_quota = int(getattr(config, "FREE_CAPTION_QUOTA", 5))
    uid_k, uname_k = _normalize_caption_quota_keys(uid, username)
    primary_key = uid_k or uname_k
    if not primary_key or int(extra_captions) <= 0:
        return get_caption_quota_info(uid, username)

    with _db_lock:
        quotas = _load(DB_CAPTION_QUOTAS, {})
        # Chống cộng trùng theo order_id trên cả key uid và username
        if order_id:
            for k in (uid_k, uname_k):
                if k and isinstance(quotas.get(k), dict) and order_id in (quotas[k].get("granted_orders") or []):
                    return get_caption_quota_info(uid, username)

        entry = quotas.get(primary_key)
        if not isinstance(entry, dict):
            entry = {"uid": uid_k, "username": uname_k, "extra_quota": 0, "granted_orders": []}

        # Gộp record cũ lưu theo username nếu lần này đã có Firebase UID chuẩn
        if uid_k and uname_k and uid_k != uname_k and isinstance(quotas.get(uname_k), dict):
            old_e = quotas.pop(uname_k)
            entry["extra_quota"] = int(entry.get("extra_quota", 0)) + int(old_e.get("extra_quota", 0))
            for old_oid in (old_e.get("granted_orders") or []):
                if old_oid not in entry.setdefault("granted_orders", []):
                    entry["granted_orders"].append(old_oid)

        entry["uid"] = uid_k or entry.get("uid", "")
        entry["username"] = uname_k or entry.get("username", "")
        entry["extra_quota"] = int(entry.get("extra_quota", 0)) + int(extra_captions)
        if order_id:
            entry.setdefault("granted_orders", []).append(order_id)
        entry["updated_at"] = datetime.now().isoformat()

        quotas[primary_key] = entry
        _save(DB_CAPTION_QUOTAS, quotas)
        return {
            "free_quota": free_quota,
            "extra_quota": entry["extra_quota"],
            "total_quota": free_quota + entry["extra_quota"],
            "granted_orders": list(entry.get("granted_orders") or []),
        }


# ── PRICING MANAGEMENT (ĐỒNG BỘ WEB & TELEGRAM BOT) ───────────────────────────

DEFAULT_PRICES = {
    "locket": {"test": 5000, "6m": 40000, "1y": 60000, "ltm": 160000},
    "spotify": {"test": 5000, "6m": 40000, "1y": 60000, "ltm": 180000},
    "combo": {"6m": 65000, "1y": 99000, "ltm": 259000},
    "locket_spotify": {"6m": 65000, "1y": 99000, "ltm": 259000},
    "locket_ai": {"ltm": 250000},
    "filter_topup": {"20": 7000, "50": 17000, "100": 33000},
    "caption_pack": {"10": 5000, "30": 10000},
}


def get_custom_prices() -> dict:
    return _load(DB_PRICES, {})


def save_custom_prices(prices: dict):
    _save(DB_PRICES, prices)


def _apply_addon_pack_price(packs_map: dict, plan_key: str, val: int) -> None:
    if isinstance(packs_map, dict) and plan_key in packs_map and isinstance(packs_map[plan_key], dict):
        packs_map[plan_key]["price"] = val


def apply_custom_prices():
    prices = get_custom_prices()
    import config
    from config import PRODUCTS
    filter_packs = getattr(config, "FILTER_TOPUP_PACKS", {})
    caption_packs = getattr(config, "CAPTION_TOPUP_PACKS", {})

    for prod_key, plans in prices.items():
        if not isinstance(plans, dict):
            continue
        for plan_key, price_val in plans.items():
            try:
                p_int = int(price_val.get("price") if isinstance(price_val, dict) else price_val)
            except (ValueError, TypeError):
                continue
            if p_int < 0:
                continue
            if prod_key in PRODUCTS and plan_key in PRODUCTS[prod_key].get("plans", {}):
                PRODUCTS[prod_key]["plans"][plan_key]["price"] = p_int
            elif prod_key == "filter_topup":
                _apply_addon_pack_price(filter_packs, plan_key, p_int)
            elif prod_key == "caption_pack":
                _apply_addon_pack_price(caption_packs, plan_key, p_int)


def get_prices() -> dict:
    """Đồng bộ giá tùy chỉnh và trả về toàn bộ cấu trúc PRODUCTS."""
    apply_custom_prices()
    from config import PRODUCTS
    return PRODUCTS


def get_all_admin_pricing() -> dict:
    """Trả về toàn bộ PRODUCTS + gói Add-ons (Filter AI, Caption VIP) phục vụ Admin quản lý giá."""
    apply_custom_prices()
    import config
    combined = {}
    for pk, pv in config.PRODUCTS.items():
        combined[pk] = pv
    filter_packs = getattr(config, "FILTER_TOPUP_PACKS", {})
    if filter_packs:
        combined["filter_topup"] = {
            "name": "Nạp Lượt Filter AI (Studio)",
            "emoji": "🎭",
            "service": "filter_topup",
            "description": "Các gói nạp thêm lượt chụp Filter AI trong Locket Custom Studio.",
            "plans": {
                k: {
                    "label": v.get("label", f"{k} Lượt"),
                    "packageCode": f"FILTER_{k}",
                    "price": v.get("price", 0),
                }
                for k, v in filter_packs.items()
            },
        }
    caption_packs = getattr(config, "CAPTION_TOPUP_PACKS", {})
    if caption_packs:
        combined["caption_pack"] = {
            "name": "Mua Thêm Caption VIP (Studio)",
            "emoji": "💬",
            "service": "caption_pack",
            "description": "Gói cộng thêm slot lưu Caption cá nhân (ngoài 5 Caption miễn phí).",
            "plans": {
                k: {
                    "label": v.get("label", f"+{k} Caption"),
                    "packageCode": f"CAPTION_{k}",
                    "price": v.get("price", 0),
                }
                for k, v in caption_packs.items()
            },
        }
    return combined


def update_plan_price(prod_key: str, plan_key: str, new_price: int) -> bool:
    import config
    from config import PRODUCTS
    valid = (
        (prod_key in PRODUCTS and plan_key in PRODUCTS[prod_key].get("plans", {}))
        or (prod_key == "filter_topup" and plan_key in getattr(config, "FILTER_TOPUP_PACKS", {}))
        or (prod_key == "caption_pack" and plan_key in getattr(config, "CAPTION_TOPUP_PACKS", {}))
    )
    if not valid:
        return False
    try:
        new_price = int(new_price)
        if new_price < 0:
            return False
    except (ValueError, TypeError):
        return False

    with _db_lock:
        prices = get_custom_prices()
        if prod_key not in prices or not isinstance(prices[prod_key], dict):
            prices[prod_key] = {}
        prices[prod_key][plan_key] = new_price
        save_custom_prices(prices)
        apply_custom_prices()
        return True


def update_all_prices(price_map: dict) -> bool:
    import config
    from config import PRODUCTS
    filter_packs = getattr(config, "FILTER_TOPUP_PACKS", {})
    caption_packs = getattr(config, "CAPTION_TOPUP_PACKS", {})
    with _db_lock:
        prices = get_custom_prices()
        for prod_key, plans in price_map.items():
            if not isinstance(plans, dict):
                continue
            is_valid_prod = (prod_key in PRODUCTS) or prod_key in ("filter_topup", "caption_pack")
            if not is_valid_prod:
                continue
            if prod_key not in prices or not isinstance(prices[prod_key], dict):
                prices[prod_key] = {}
            for plan_key, price_val in plans.items():
                valid_plan = (
                    (prod_key in PRODUCTS and plan_key in PRODUCTS[prod_key].get("plans", {}))
                    or (prod_key == "filter_topup" and plan_key in filter_packs)
                    or (prod_key == "caption_pack" and plan_key in caption_packs)
                )
                if not valid_plan:
                    continue
                try:
                    p_int = int(price_val.get("price") if isinstance(price_val, dict) else price_val)
                    if p_int >= 0:
                        prices[prod_key][plan_key] = p_int
                except (ValueError, TypeError):
                    pass
        save_custom_prices(prices)
        apply_custom_prices()
        return True


def reset_default_prices() -> bool:
    with _db_lock:
        save_custom_prices({})
        import config
        from config import PRODUCTS
        filter_packs = getattr(config, "FILTER_TOPUP_PACKS", {})
        caption_packs = getattr(config, "CAPTION_TOPUP_PACKS", {})
        for pk, plans in DEFAULT_PRICES.items():
            for pl, val in plans.items():
                if pk in PRODUCTS and pl in PRODUCTS[pk]["plans"]:
                    PRODUCTS[pk]["plans"][pl]["price"] = val
                elif pk == "filter_topup":
                    _apply_addon_pack_price(filter_packs, pl, val)
                elif pk == "caption_pack":
                    _apply_addon_pack_price(caption_packs, pl, val)
        return True

# ── BANNER / THÔNG BÁO ƯU ĐÃI WEB ───────────────────────────────────────────
DEFAULT_BANNER = {
    "enabled": True,
    "tag": "✨ UY TÍN",
    "text": "Một Chữ Tín - Vạn Niềm Tin"
}

def get_banner_config() -> dict:
    cfg = _load(DB_BANNER, None)
    if not isinstance(cfg, dict):
        return DEFAULT_BANNER.copy()
    return cfg

def update_banner_config(tag: str, text: str, enabled: bool = True) -> dict:
    data = {
        "enabled": bool(enabled),
        "tag": str(tag).strip() or "🔥 HOT ƯU ĐÃI",
        "text": str(text).strip()
    }
    _save(DB_BANNER, data)
    return data

# Tự động đồng bộ bảng giá tuỳ chỉnh ngay khi nạp module
try:
    apply_custom_prices()
except Exception:
    pass
