import json
import os
import random
import time
from urllib.parse import quote
import config

ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

def load_orders() -> dict:
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_orders(orders: dict):
    try:
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save orders: {e}")

def create_order(chat_id: int, tg_user: str, locket_data: dict) -> dict:
    orders = load_orders()
    rand_id = random.randint(1000, 9999)
    order_id = f"VIP{rand_id}"
    memo = f"VIP{rand_id} {locket_data.get('username', '')[:10]}"

    order = {
        "order_id": order_id,
        "chat_id": chat_id,
        "tg_user": tg_user,
        "username": locket_data.get("username"),
        "full_name": locket_data.get("full_name"),
        "uid": locket_data.get("uid"),
        "token": locket_data.get("token"),
        "download_url": locket_data.get("download_url"),
        "avatar": locket_data.get("avatar"),
        "amount": config.PRICE_VND,
        "memo": memo,
        "status": "pending",  # pending, paid, approved, cancelled
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    orders[order_id] = order
    save_orders(orders)
    return order

def get_order(order_id: str) -> dict | None:
    orders = load_orders()
    return orders.get(order_id)

def update_order_status(order_id: str, status: str) -> dict | None:
    orders = load_orders()
    if order_id in orders:
        orders[order_id]["status"] = status
        orders[order_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_orders(orders)
        return orders[order_id]
    return None

def get_pending_orders() -> list:
    """Lấy danh sách các đơn hàng đang chờ hoặc đã bấm chuyển khoản"""
    orders = load_orders()
    return [o for o in orders.values() if o.get("status") in ("pending", "paid")]

def build_qr_url(bank_code: str, acc_no: str, amount: int, memo: str) -> str:
    """Tạo link mã QR VietQR (chuẩn PNG hỗ trợ mọi ngân hàng)"""
    safe_memo = quote(memo)
    return f"https://qr.sepay.vn/img?bank={bank_code}&acc={acc_no}&amount={amount}&des={safe_memo}"

