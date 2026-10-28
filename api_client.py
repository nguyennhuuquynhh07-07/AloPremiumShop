"""
api_client.py – Gọi API locket.2707226.xyz
Tích hợp bảng tra cứu và phân loại mã lỗi HTTP chuẩn:
  400, 401, 402, 403, 404, 409, 429
"""

import httpx
from config import API_KEY, API_BASE_URL


# ─── BẢNG TRA CỨU MÃ LỖI HTTP TỪ HỆ THỐNG ────────────────────────────────────

API_ERROR_CODES = {
    400: {
        "title": "HTTP 400",
        "sample": "Thiếu username hoặc uid",
        "cause": "Body hoặc Query gửi lên thiếu trường bắt buộc hoặc sai định dạng.",
        "solution": "Kiểm tra lại tên key trong JSON body và chắc chắn có Content-Type: application/json.",
    },
    401: {
        "title": "HTTP 401",
        "sample": "Unauthorized",
        "cause": "Secret Key sai, đã bị rotate đổi mới hoặc thiếu header Bearer.",
        "solution": "Lấy lại Secret Token trong tab Mã API. Gửi header Authorization: Bearer sk_....",
    },
    402: {
        "title": "HTTP 402",
        "sample": "Không đủ coin. Cần 15, bạn có 8",
        "cause": "Số dư tài khoản CTV không đủ để thanh toán gói này.",
        "solution": "Nạp thêm coin trong tab Nạp Coin của Dashboard.",
    },
    403: {
        "title": "HTTP 403",
        "sample": "Tài khoản chưa kích hoạt",
        "cause": "Tài khoản CTV mới tạo chưa nạp đủ 150.000đ kích hoạt ban đầu.",
        "solution": "Nạp tối thiểu 150.000đ để kích hoạt tài khoản.",
    },
    404: {
        "title": "HTTP 404",
        "sample": "Gói không tồn tại hoặc đã ẩn",
        "cause": "Mã gói packageCode viết sai (Ví dụ nhầm SPOTIFY_1Y).",
        "solution": "Gọi GET /api/packages để lấy đúng mã gói (SPT, SP6M, SPOTIFY1Y, SPVV).",
    },
    409: {
        "title": "HTTP 409",
        "sample": "UID thuộc về người khác",
        "cause": "UID này đã được mua bởi CTV khác và vẫn đang còn hạn dùng.",
        "solution": "Khách phải chờ hết hạn cũ hoặc dùng đúng tài khoản CTV ban đầu gia hạn.",
    },
    429: {
        "title": "HTTP 429",
        "sample": "Tra cứu quá nhiều – thử lại sau",
        "cause": "Vượt quá tần suất rate limit cho phép trong 1 giờ.",
        "solution": "Thêm cache ở bot (ví dụ cache 30 giây cho cùng một khách) để giảm tải request.",
    },
}


def parse_api_error(resp: httpx.Response) -> str:
    """Chuyển đổi lỗi HTTP trả về từ API thành thông báo chuẩn theo bảng tra cứu."""
    status = resp.status_code
    msg = ""
    try:
        data = resp.json()
        msg = data.get("message") or data.get("error") or ""
    except Exception:
        msg = resp.text

    info = API_ERROR_CODES.get(status)
    if info:
        detail = f"[{info['title']}] {msg or info['sample']}\n"
        detail += f"• Nguyên nhân: {info['cause']}\n"
        detail += f"• Cách xử lý: {info['solution']}"
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
    resp = httpx.get(url, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def get_packages(service: str = "all") -> dict:
    """
    GET /api/packages?service=all|spotify|locket
    Lấy danh sách các gói cước và giá coin từ máy chủ.
    """
    url = f"{API_BASE_URL}/api/packages"
    resp = httpx.get(url, params={"service": service}, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def check_uid_details(username: str, service: str = "locket") -> dict:
    """
    GET /api/uid/check?username=...&service=...
    Kiểm tra thông tin chi tiết gói, hạn dùng, trạng thái kích hoạt của UID.
    """
    url = f"{API_BASE_URL}/api/uid/check"
    resp = httpx.get(url, params={"username": username, "service": service}, headers=_headers(), timeout=15)
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
    resp = httpx.get(url, params={"uid": uid_or_link}, headers=_headers(), timeout=15)
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
    resp = httpx.post(url, json={"uid": uid}, headers=_headers(), timeout=15)
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
    resp = httpx.post(
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
    resp = httpx.post(
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
