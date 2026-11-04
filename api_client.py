"""
api_client.py – Gọi API locket.2707226.xyz
Tích hợp bảng tra cứu và phân loại mã lỗi HTTP chuẩn:
  400, 401, 402, 403, 404, 409, 429
"""

import httpx
from config import API_KEY, API_BASE_URL

_client = httpx.Client(
    timeout=httpx.Timeout(12.0, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    headers={"User-Agent": "AloPremiumBot/2.0"}
)


# ─── BẢNG TRA CỨU MÃ LỖI THEO TÀI LIỆU API CTV ─────────────────────────────

API_ERROR_CODES = {
    # Mã lỗi trả về dạng chuỗi (String Error Codes)
    "UNAUTHORIZED": "Secret Key bị sai, thiếu hoặc tài khoản CTV chưa được kích hoạt.",
    "INVALID_IDENTIFIER": "Link Spotify hoặc Username Locket không hợp lệ / không tìm thấy.",
    "INSUFFICIENT_BALANCE": "Số dư Coin không đủ để thanh toán gói cước. Cần nạp thêm Coin trên Dashboard.",
    "PACKAGE_NOT_FOUND": "Mã gói cước (packageCode) không tồn tại hoặc đã ngừng bán.",
    "UID_NOT_FOUND": "Không tìm thấy UID trên hệ thống khi gọi kiểm tra hoặc reset.",
    "RATE_LIMIT_EXCEEDED": "Bot gửi request quá nhanh. Cần giãn cách request (1-2s).",
    "INTERNAL_SERVER_ERROR": "Lỗi máy chủ API xử lý. Liên hệ Admin hệ thống để được hỗ trợ.",

    # Mã lỗi HTTP Status Code
    400: "Dữ liệu gửi lên không hợp lệ, UID/Username không tồn tại hoặc không đủ Coin.",
    401: "Secret Key sai, hết hạn hoặc chưa kích hoạt tài khoản CTV.",
    402: "Số dư tài khoản CTV không đủ để thanh toán gói này.",
    403: "Tài khoản CTV mới tạo chưa nạp đủ 150.000đ kích hoạt ban đầu.",
    404: "Gói cước hoặc UID không tồn tại trên hệ thống.",
    409: "UID này đã được mua bởi CTV khác và vẫn đang còn hạn dùng.",
    429: "Thao tác quá nhanh, vượt quá tần suất cho phép trong 1 giờ. Vui lòng thử lại sau.",
    500: "Lỗi máy chủ API. Vui lòng liên hệ Admin để được hỗ trợ.",
}


def parse_api_error(resp: httpx.Response) -> str:
    """Chuyển đổi lỗi HTTP trả về từ API thành thông báo chuẩn theo bảng tra cứu."""
    status = resp.status_code
    err_code = ""
    msg = ""
    try:
        data = resp.json()
        err_code = data.get("error") or ""
        msg = data.get("message") or ""
    except Exception:
        msg = resp.text

    # Ưu tiên bắt theo mã lỗi chuỗi từ hệ thống
    if err_code and err_code in API_ERROR_CODES:
        return f"[{err_code}] {API_ERROR_CODES[err_code]}"

    # Bắt theo mã HTTP Status
    if status in API_ERROR_CODES:
        detail = f"[HTTP {status}] {API_ERROR_CODES[status]}"
        if msg:
            detail += f"\n• Chi tiết: {msg}"
        return detail

    return f"Lỗi máy chủ API (Mã {status}): {msg or resp.text}"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


# ─── THÔNG TIN TÀI KHOẢN CTV & SỐ DƯ COIN ────────────────────────────────────

def get_account_info() -> dict:
    """
    GET /api/keys/me
    Tra cứu thông tin tài khoản CTV: username, email, balanceCoin, role...
    """
    url = f"{API_BASE_URL}/api/keys/me"
    resp = _client.get(url, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def get_packages(service: str = "all") -> dict:
    """
    GET /api/packages?service=all|spotify|locket
    Lấy danh sách các gói cước và giá coin từ máy chủ.
    """
    url = f"{API_BASE_URL}/api/packages"
    resp = _client.get(url, params={"service": service}, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def check_uid_details(username: str, service: str = "locket") -> dict:
    """
    GET /api/uid/check?username=...&service=...
    Kiểm tra thông tin chi tiết gói, hạn dùng, trạng thái kích hoạt của UID.
    """
    url = f"{API_BASE_URL}/api/uid/check"
    resp = _client.get(url, params={"username": username, "service": service}, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


# ─── SPOTIFY ──────────────────────────────────────────────────────────────────

def spotify_check(uid_or_link: str) -> dict:
    """
    GET /api/spotify/check?uid=...
    Kiểm tra tài khoản & Profile Spotify.
    """
    url = f"{API_BASE_URL}/api/spotify/check"
    resp = _client.get(url, params={"uid": uid_or_link}, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def spotify_reset(uid: str) -> dict:
    """
    POST /api/spotify/reset
    Giải phóng phiên IP Spotify (chuyển máy tức thì).
    Body: {"uid": "<uid>"}
    """
    url = f"{API_BASE_URL}/api/spotify/reset"
    resp = _client.post(url, json={"uid": uid}, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


# ─── LOCKET ───────────────────────────────────────────────────────────────────

def locket_resolve(identifier: str) -> dict:
    """
    POST /api/uid/resolve
    Tra cứu Link / Username ra UID & Avatar.
    """
    url = f"{API_BASE_URL}/api/uid/resolve"
    resp = _client.post(
        url,
        json={"identifier": identifier, "service": "locket"},
        headers=_headers(),
        timeout=15,
    )
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


# ─── MUA GÓI / GIA HẠN (Trừ Coin CTV) ────────────────────────────────────────

def create_subscription(uid: str, package_code: str, service: str, note: str = "Order from Telegram Bot") -> dict:
    """
    POST /api/uid/create
    Mua gói mới / Gia hạn (Trừ Coin CTV)
    Body: { "username": "<uid>", "packageCode": "<code>", "service": "<service>", "note": "..." }
    """
    url = f"{API_BASE_URL}/api/uid/create"
    resp = _client.post(
        url,
        json={
            "username": uid,
            "packageCode": package_code,
            "service": service,
            "note": note,
        },
        headers=_headers(),
        timeout=20,
    )
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


import time

_uids_cache = []
_uids_cache_time = 0.0

def get_activated_uids(force_refresh: bool = False) -> list:
    """
    GET /api/uid/list
    Lấy danh sách tài khoản đã kích hoạt trên máy chủ API CTV (có bộ nhớ đệm cache 2 phút tránh nghẽn server).
    """
    global _uids_cache, _uids_cache_time
    now = time.time()
    if not force_refresh and _uids_cache and (now - _uids_cache_time < 120):
        return _uids_cache

    url = f"{API_BASE_URL}/api/uid/list"
    try:
        resp = _client.get(url, headers=_headers(), timeout=5)
        if resp.is_success:
            data = resp.json().get("data", [])
            if data:
                _uids_cache = data
                _uids_cache_time = now
                return _uids_cache
    except Exception:
        pass
    return _uids_cache or []
