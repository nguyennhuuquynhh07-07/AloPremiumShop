"""
database.py – Quản lý dữ liệu JSON (đơn hàng, thống kê, người dùng, mã giảm giá)
"""

import json
import os
from datetime import datetime

from config import DB_ORDERS, DB_STATS

DB_USERS = "data/users.json"
DB_CODES = "data/codes.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _ensure(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _load(path: str, default):
    _ensure(path)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def _save(path: str, data):
    _ensure(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── ORDERS ────────────────────────────────────────────────────────────────────

def get_orders() -> dict:
    return _load(DB_ORDERS, {})


def save_orders(orders: dict):
    _save(DB_ORDERS, orders)


def create_order(order_id: str, user_id: int, username: str,
                 product: str, plan: str, price: int,
                 uid: str = "", display_name: str = "", **kwargs) -> dict:
    orders = get_orders()
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
    orders[order_id] = order
    save_orders(orders)
    return order


def update_order(order_id: str, **kwargs):
    orders = get_orders()
    if order_id in orders:
        orders[order_id].update(kwargs)
        save_orders(orders)


def get_order(order_id: str) -> dict | None:
    return get_orders().get(order_id)


def get_user_orders(user_id: int) -> list:
    return [o for o in get_orders().values() if o["user_id"] == user_id]


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

