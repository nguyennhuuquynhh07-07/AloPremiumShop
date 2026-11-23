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
    txs = get_used_tx_ids()
    txs[str(tx_id)] = {
        "order_id": order_id,
        "used_at": datetime.now().isoformat()
    }
    _save(DB_TX, txs)


def register_order_payment(order_id: str, tx_id: str, amount: float, *, on_time: bool) -> str | None:
    """Persist verified payment before handing a new, on-time order off for processing."""
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
        update_order(order_id, status="paid_review")
        return "process" if not existing and on_time and status in UNPAID_ORDER_STATUSES else "review"


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



# ── PRICING MANAGEMENT (ĐỒNG BỘ WEB & TELEGRAM BOT) ───────────────────────────

DEFAULT_PRICES = {
    "locket": {"test": 5000, "6m": 40000, "1y": 60000, "ltm": 160000},
    "spotify": {"test": 5000, "6m": 40000, "1y": 60000, "ltm": 180000},
    "locket_spotify": {"ltm": 230000},
    "locket_ai": {"ltm": 250000},
}

def get_custom_prices() -> dict:
    return _load(DB_PRICES, {})

def save_custom_prices(prices: dict):
    _save(DB_PRICES, prices)

def apply_custom_prices():
    prices = get_custom_prices()
    from config import PRODUCTS
    for prod_key, plans in prices.items():
        if prod_key in PRODUCTS and isinstance(plans, dict):
            for plan_key, price_val in plans.items():
                if plan_key in PRODUCTS[prod_key].get("plans", {}):
                    try:
                        p_int = int(price_val.get("price") if isinstance(price_val, dict) else price_val)
                        if p_int >= 0:
                            PRODUCTS[prod_key]["plans"][plan_key]["price"] = p_int
                    except (ValueError, TypeError):
                        pass

def get_prices() -> dict:
    """Đồng bộ giá tùy chỉnh và trả về toàn bộ cấu trúc PRODUCTS."""
    apply_custom_prices()
    from config import PRODUCTS
    return PRODUCTS

def update_plan_price(prod_key: str, plan_key: str, new_price: int) -> bool:
    from config import PRODUCTS
    if prod_key not in PRODUCTS or plan_key not in PRODUCTS[prod_key].get("plans", {}):
        return False
    try:
        new_price = int(new_price)
    except (ValueError, TypeError):
        return False

    prices = get_custom_prices()
    if prod_key not in prices or not isinstance(prices[prod_key], dict):
        prices[prod_key] = {}
    prices[prod_key][plan_key] = new_price
    save_custom_prices(prices)
    apply_custom_prices()
    return True

def update_all_prices(price_map: dict) -> bool:
    from config import PRODUCTS
    prices = get_custom_prices()
    for prod_key, plans in price_map.items():
        if prod_key in PRODUCTS and isinstance(plans, dict):
            if prod_key not in prices or not isinstance(prices[prod_key], dict):
                prices[prod_key] = {}
            for plan_key, price_val in plans.items():
                if plan_key in PRODUCTS[prod_key].get("plans", {}):
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
    if os.path.exists(DB_PRICES):
        try:
            os.remove(DB_PRICES)
        except Exception:
            pass
    from config import PRODUCTS
    for pk, plans in DEFAULT_PRICES.items():
        for pl, val in plans.items():
            if pk in PRODUCTS and pl in PRODUCTS[pk]["plans"]:
                PRODUCTS[pk]["plans"][pl]["price"] = val
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
