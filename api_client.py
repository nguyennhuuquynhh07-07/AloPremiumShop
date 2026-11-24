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
    413: "Dung lượng file tải lên vượt quá giới hạn cho phép (tối đa 20MB).",
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


def _auth_only_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
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


# ─── TÍNH NĂNG CTV: KHUNG WIDGET, CAPTION, SF SYMBOLS & BỘ LỌC LUT ─────────────

_frames_cache = None
_frames_cache_time = 0.0
_filters_cache = None
_filters_cache_time = 0.0
_symbols_all_cache = None
_symbols_cache_time = 0.0


def ctv_get_frames(force_refresh: bool = False) -> dict:
    """
    GET /api/v1/ctv/frames
    Lấy toàn bộ khung widget mà CTV đã cấu hình cho khách hàng hoặc cá nhân hóa theo UID.
    """
    global _frames_cache, _frames_cache_time
    now = time.time()
    if not force_refresh and _frames_cache is not None and (now - _frames_cache_time < 30):
        return _frames_cache

    url = f"{API_BASE_URL}/api/v1/ctv/frames"
    resp = _client.get(url, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    data = resp.json()
    _frames_cache = data
    _frames_cache_time = now
    return data


def ctv_save_frame(
    url_img: str,
    name: str = "",
    target_uid: str = "ALL",
    target_uids: list | None = None,
    active: bool = True,
) -> dict:
    """
    POST /api/v1/ctv/frames
    Tạo mới hoặc chỉnh sửa khung widget tùy biến (ALL hoặc danh sách UID chỉ định).
    """
    global _frames_cache_time
    endpoint = f"{API_BASE_URL}/api/v1/ctv/frames"
    payload: dict = {
        "url": url_img.strip(),
        "active": bool(active),
    }
    if name:
        payload["name"] = name.strip()
    if target_uids is not None:
        payload["targetUids"] = [str(u).strip() for u in target_uids if str(u).strip()]
        if not target_uid and payload["targetUids"]:
            payload["targetUid"] = ",".join(payload["targetUids"])
    if target_uid:
        payload["targetUid"] = target_uid.strip()

    resp = _client.post(endpoint, json=payload, headers=_headers(), timeout=20)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    _frames_cache_time = 0.0
    return resp.json()


def ctv_get_captions(uid: str = "") -> dict:
    """
    GET /api/v1/ctv/captions?uid=...
    Tra cứu Brand Caption của CTV (khi không truyền uid) hoặc Caption riêng của khách hàng.
    """
    url = f"{API_BASE_URL}/api/v1/ctv/captions"
    req_params = {"uid": uid.strip()} if uid and uid.strip() else None
    resp = _client.get(url, params=req_params, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def ctv_save_caption(
    text: str,
    uid: str = "",
    icon: str = "",
    icon_type: str = "",
    symbol_name: str = "",
    colors: list | None = None,
    target_uid: str = "",
    active: bool = True,
) -> dict:
    """
    POST /api/v1/ctv/captions
    Thêm hoặc cập nhật Caption cho khách hàng (uid) hoặc Brand Caption CTV (targetUid='ALL').
    """
    url = f"{API_BASE_URL}/api/v1/ctv/captions"
    payload: dict = {
        "text": (text or "").strip()[:100],
        "active": bool(active),
    }
    if uid and uid.strip():
        payload["uid"] = uid.strip()
    if target_uid and target_uid.strip():
        payload["targetUid"] = target_uid.strip()
    if icon:
        payload["icon"] = icon.strip()
    if icon_type:
        payload["iconType"] = icon_type.strip()
    if symbol_name:
        payload["symbolName"] = symbol_name.strip()
    if colors and isinstance(colors, list):
        payload["colors"] = [str(c).strip() for c in colors if str(c).strip()][:2]

    resp = _client.post(url, json=payload, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def ctv_get_symbols(category: str = "all", q: str = "") -> dict:
    """
    GET /api/v1/ctv/captions/symbols?category=...&q=...
    Lấy thư viện 446+ Apple SF Symbols (hỗ trợ cache CDN nội bộ).
    """
    global _symbols_all_cache, _symbols_cache_time
    cat_clean = (category or "all").strip()
    q_clean = (q or "").strip()
    now = time.time()

    # Tận dụng cache danh sách đầy đủ khi tìm kiếm/lọc thông thường để phản hồi tức thì
    if _symbols_all_cache is None or (now - _symbols_cache_time >= 1800):
        url_all = f"{API_BASE_URL}/api/v1/ctv/captions/symbols"
        resp_all = _client.get(url_all, params={"category": "all"}, timeout=15)
        if resp_all.is_error:
            raise Exception(parse_api_error(resp_all))
        _symbols_all_cache = resp_all.json()
        _symbols_cache_time = now

    if (not cat_clean or cat_clean == "all") and not q_clean:
        return _symbols_all_cache

    # Nếu có từ khóa tiếng Việt đặc biệt hoặc yêu cầu filter, có thể gọi upstream để đồng bộ chính xác
    url = f"{API_BASE_URL}/api/v1/ctv/captions/symbols"
    req_params = {}
    if cat_clean:
        req_params["category"] = cat_clean
    if q_clean:
        req_params["q"] = q_clean
    resp = _client.get(url, params=req_params, timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def ctv_get_filters(force_refresh: bool = False) -> dict:
    """
    GET /api/v1/ctv/filters
    Lấy toàn bộ danh sách bộ lọc màu LUT mẫu (sampleLuts) và LUT tùy biến (customFilters).
    """
    global _filters_cache, _filters_cache_time
    now = time.time()
    if not force_refresh and _filters_cache is not None and (now - _filters_cache_time < 60):
        return _filters_cache

    url = f"{API_BASE_URL}/api/v1/ctv/filters"
    resp = _client.get(url, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    data = resp.json()
    _filters_cache = data
    _filters_cache_time = now
    return data


def ctv_toggle_filter(filter_id: str, enabled: bool = True) -> dict:
    """
    POST /api/v1/ctv/filters/toggle
    Bật hoặc tắt bộ lọc màu LUT đối với người dùng cuối trong cửa hàng CTV.
    """
    global _filters_cache_time
    url = f"{API_BASE_URL}/api/v1/ctv/filters/toggle"
    resp = _client.post(
        url,
        json={"filterId": filter_id.strip(), "enabled": bool(enabled)},
        headers=_headers(),
        timeout=15,
    )
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    _filters_cache_time = 0.0
    return resp.json()


def ctv_upload_filter(file_bytes: bytes, filename: str, name: str = "") -> dict:
    """
    POST /api/v1/ctv/filters/upload
    Tải lên file màu 3D LUT định dạng .cube (tối đa 20MB).
    """
    global _filters_cache_time
    url = f"{API_BASE_URL}/api/v1/ctv/filters/upload"
    form_data = {"name": name.strip()} if name and name.strip() else {}
    files = {"file": (filename, file_bytes, "application/octet-stream")}
    resp = _client.post(
        url,
        data=form_data,
        files=files,
        headers=_auth_only_headers(),
        timeout=60,
    )
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    _filters_cache_time = 0.0
    return resp.json()
