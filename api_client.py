"""
api_client.py – Gọi API locket.2707226.xyz
Tích hợp bảng tra cứu và phân loại mã lỗi HTTP chuẩn:
  400, 401, 402, 403, 404, 409, 429
"""

import threading
import time
import httpx
from config import API_KEY, API_BASE_URL

_client = httpx.Client(
    timeout=httpx.Timeout(12.0, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    headers={"User-Agent": "AloPremiumBot/2.0"}
)


class ApiError(Exception):
    """Lỗi có cấu trúc khi gọi máy chủ API CTV, giữ tương thích str() với Exception thường."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


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
    400: "Dữ liệu gửi lên không hợp lệ, UID/Username không tồn tại hoặc thiếu trường bắt buộc.",
    401: "Secret Key sai, đã bị đổi mới hoặc thiếu header Authorization: Bearer sk_...",
    402: "Số dư Coin CTV không đủ để thanh toán gói này. Cần nạp thêm Coin trên Dashboard.",
    403: "Tài khoản CTV mới tạo chưa nạp đủ 150.000đ kích hoạt ban đầu.",
    404: "Gói cước hoặc UID không tồn tại trên hệ thống (hoặc gói đã bị ẩn).",
    409: "UID này đã được mua bởi CTV khác và vẫn đang còn hạn dùng.",
    413: "Dung lượng file tải lên vượt quá giới hạn cho phép (tối đa 20MB).",
    429: "Tra cứu quá nhiều – vượt quá tần suất Rate Limit cho phép trong 1 giờ. Vui lòng thử lại sau.",
    500: "Lỗi máy chủ API. Vui lòng liên hệ Admin để được hỗ trợ.",
}


def _extract_error_parts(resp: httpx.Response) -> tuple[str, int, str]:
    status = resp.status_code
    err_code = ""
    msg = ""
    try:
        data = resp.json()
        err_code = str(data.get("error") or "").strip()
        msg = str(data.get("message") or "").strip()
    except Exception:
        msg = (resp.text or "").strip()

    if err_code and err_code in API_ERROR_CODES:
        text = f"[{err_code}] {API_ERROR_CODES[err_code]}"
        if msg and msg.lower() not in text.lower():
            text += f"\n• Chi tiết: {msg}"
        return text, status, err_code

    if status in API_ERROR_CODES:
        detail = f"[HTTP {status}] {API_ERROR_CODES[status]}"
        if msg:
            detail += f"\n• Chi tiết: {msg}"
        return detail, status, err_code

    return f"Lỗi máy chủ API (Mã {status}): {msg or resp.text}", status, err_code


def parse_api_error(resp: httpx.Response) -> str:
    """Chuyển đổi lỗi HTTP trả về từ API thành thông báo chuẩn theo bảng tra cứu."""
    text, _, _ = _extract_error_parts(resp)
    return text


def _raise_api_error(resp: httpx.Response) -> None:
    text, status, err_code = _extract_error_parts(resp)
    raise ApiError(text, status_code=status, error_code=err_code)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _auth_only_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
    }


# ─── CACHE 30S CHỐNG HTTP 429 & PARSE RESPONSE CHUẨN ─────────────────────────

_lookup_cache_lock = threading.Lock()
_lookup_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}
_LOOKUP_CACHE_TTL = 30.0
_ACCOUNT_CACHE_TTL = 30.0
_account_info_cache: tuple[float, dict | None] = (0.0, None)


def _get_cached_lookup(op: str, key: str, service: str = "", ttl: float = _LOOKUP_CACHE_TTL) -> dict | None:
    cache_key = (op, key.strip().lower(), service.strip().lower())
    now = time.time()
    with _lookup_cache_lock:
        entry = _lookup_cache.get(cache_key)
        if entry and (now - entry[0] < ttl):
            return entry[1]
    return None


def _set_cached_lookup(op: str, key: str, value: dict, service: str = "") -> None:
    cache_key = (op, key.strip().lower(), service.strip().lower())
    now = time.time()
    with _lookup_cache_lock:
        if len(_lookup_cache) > 500:
            expired = [k for k, (ts, _) in _lookup_cache.items() if now - ts >= _LOOKUP_CACHE_TTL]
            for k in expired:
                _lookup_cache.pop(k, None)
            if len(_lookup_cache) > 500:
                _lookup_cache.clear()
        _lookup_cache[cache_key] = (now, value)


def invalidate_uid_cache(identifier: str = "", service: str = "") -> None:
    """Xóa cache tra cứu (30s) cho UID/username sau khi kích hoạt gói hoặc reset Spotify."""
    global _account_info_cache, _uids_cache_time
    ident_l = (identifier or "").strip().lower().lstrip("@")
    svc_l = (service or "").strip().lower()
    with _lookup_cache_lock:
        if not ident_l:
            _lookup_cache.clear()
        else:
            to_del = []
            for k in _lookup_cache:
                _, k_id, k_svc = k
                if svc_l and k_svc and k_svc != svc_l:
                    continue
                if ident_l in k_id or k_id in ident_l:
                    to_del.append(k)
            for k in to_del:
                _lookup_cache.pop(k, None)
    _account_info_cache = (0.0, None)
    _uids_cache_time = 0.0


def parse_spotify_check_data(res: dict) -> dict:
    """Chuẩn hóa JSON trả về từ GET /api/spotify/check (đọc đúng object lồng spotify.isBound/deviceSig...)."""
    data = res.get("data") if isinstance(res, dict) and isinstance(res.get("data"), dict) else (res if isinstance(res, dict) else {})
    sp_obj = data.get("spotify") if isinstance(data.get("spotify"), dict) else {}
    is_bound = sp_obj.get("isBound") if "isBound" in sp_obj else data.get("isBound", False)
    active = bool(data.get("active") is True or str(data.get("status") or "").upper() == "ACTIVE")
    return {
        "uid": str(data.get("uid") or data.get("id") or "").strip(),
        "username": str(data.get("displayName") or data.get("username") or data.get("name") or "").strip(),
        "avatar_url": data.get("avatarUrl") or data.get("avatar") or data.get("image") or "",
        "found": bool(data.get("found", True)),
        "active": active,
        "status": str(data.get("status") or ("ACTIVE" if active else "INACTIVE")),
        "expires_at": data.get("expiresAt"),
        "is_mine": data.get("isMine"),
        "is_bound": bool(is_bound),
        "client_ip": str(sp_obj.get("clientIp") or "").strip(),
        "device_sig": str(sp_obj.get("deviceSig") or "").strip(),
        "last_seen_at": sp_obj.get("lastSeenAt"),
        "raw": data,
    }


def parse_uid_check_data(res: dict) -> dict:
    """Chuẩn hóa JSON trả về từ GET /api/uid/check."""
    data = res.get("data") if isinstance(res, dict) and isinstance(res.get("data"), dict) else (res if isinstance(res, dict) else {})
    pkg = data.get("package") if isinstance(data.get("package"), dict) else {}
    active = bool(data.get("active") is True or str(data.get("status") or "").upper() == "ACTIVE")
    return {
        "uid": str(data.get("uid") or data.get("id") or "").strip(),
        "username": str(data.get("username") or "").strip(),
        "service": str(data.get("service") or "").strip(),
        "avatar_url": data.get("avatarUrl") or data.get("avatar") or "",
        "found": bool(data.get("found", False)),
        "active": active,
        "status": str(data.get("status") or ("ACTIVE" if active else "INACTIVE")),
        "expires_at": data.get("expiresAt"),
        "created_at": data.get("createdAt"),
        "is_mine": data.get("isMine"),
        "package": pkg,
        "package_code": str(pkg.get("code") or "").strip(),
        "package_name": str(pkg.get("name") or "").strip(),
        "duration_days": pkg.get("durationDays"),
        "price_coin": pkg.get("priceCoin"),
        "raw": data,
    }


# ─── THÔNG TIN TÀI KHOẢN CTV & SỐ DƯ COIN ────────────────────────────────────

def get_account_info(force_refresh: bool = False) -> dict:
    """
    GET /api/keys/me (300 lần/giờ)
    Tra cứu thông tin tài khoản CTV: username, email, balanceCoin, isActivated, role...
    """
    global _account_info_cache
    now = time.time()
    cached_ts, cached_val = _account_info_cache
    if not force_refresh and cached_val is not None and (now - cached_ts < _ACCOUNT_CACHE_TTL):
        return cached_val

    url = f"{API_BASE_URL}/api/keys/me"
    resp = _client.get(url, headers=_headers(), timeout=15)
    if resp.is_error:
        _raise_api_error(resp)
    res = resp.json()
    _account_info_cache = (time.time(), res)
    return res


def get_packages(service: str = "all") -> dict:
    """
    GET /api/packages?service=all|spotify|locket (Cache 5s ở upstream)
    Lấy danh sách các gói cước và giá coin từ máy chủ.
    """
    url = f"{API_BASE_URL}/api/packages"
    resp = _client.get(url, params={"service": service}, headers=_headers(), timeout=15)
    if resp.is_error:
        _raise_api_error(resp)
    return resp.json()


def check_uid_details(username: str, service: str = "locket", force_refresh: bool = False) -> dict:
    """
    GET /api/uid/check?username=...&service=... (1200 lần/giờ, cache nội bộ 30s)
    Kiểm tra thông tin chi tiết gói, hạn dùng, trạng thái kích hoạt và quyền sở hữu isMine của UID.
    """
    if not force_refresh:
        cached = _get_cached_lookup("uid_check", username, service)
        if cached is not None:
            return cached

    url = f"{API_BASE_URL}/api/uid/check"
    resp = _client.get(url, params={"username": username, "service": service}, headers=_headers(), timeout=15)
    if resp.is_error:
        _raise_api_error(resp)
    res = resp.json()
    _set_cached_lookup("uid_check", username, res, service)
    return res


# ─── SPOTIFY ──────────────────────────────────────────────────────────────────

def spotify_check(uid_or_link: str, force_refresh: bool = False) -> dict:
    """
    GET /api/spotify/check?uid=... (600 lần/giờ, cache nội bộ 30s)
    Kiểm tra tài khoản, Profile Spotify & Phiên IP hoạt động (spotify.isBound/deviceSig/clientIp).
    """
    if not force_refresh:
        cached = _get_cached_lookup("spotify_check", uid_or_link, "spotify")
        if cached is not None:
            return cached

    url = f"{API_BASE_URL}/api/spotify/check"
    resp = _client.get(url, params={"uid": uid_or_link}, headers=_headers(), timeout=15)
    if resp.is_error:
        _raise_api_error(resp)
    res = resp.json()
    _set_cached_lookup("spotify_check", uid_or_link, res, "spotify")
    return res


def spotify_reset(uid: str) -> dict:
    """
    POST /api/spotify/reset (60 lần/giờ)
    Giải phóng phiên IP Spotify ngay lập tức (chuyển máy tức thì thay vì chờ ân hạn 20-25s).
    Body: {"uid": "<uid>"}
    """
    url = f"{API_BASE_URL}/api/spotify/reset"
    resp = _client.post(url, json={"uid": uid}, headers=_headers(), timeout=15)
    if resp.is_error:
        _raise_api_error(resp)
    invalidate_uid_cache(uid, "spotify")
    return resp.json()


# ─── RESOLVE UID (LOCKET & SPOTIFY) ──────────────────────────────────────────

def resolve_uid(identifier: str, service: str = "locket", force_refresh: bool = False) -> dict:
    """
    POST /api/uid/resolve (300 lần/giờ, cache nội bộ 30s)
    Tra cứu Username Locket hoặc Link/UID Spotify ra UID & Avatar mà không tạo đơn/trừ Coin.
    """
    svc = (service or "locket").strip().lower()
    if svc not in ("locket", "spotify"):
        svc = "locket"

    if not force_refresh:
        cached = _get_cached_lookup("uid_resolve", identifier, svc)
        if cached is not None:
            return cached

    url = f"{API_BASE_URL}/api/uid/resolve"
    resp = _client.post(
        url,
        json={"identifier": identifier, "service": svc},
        headers=_headers(),
        timeout=15,
    )
    if resp.is_error:
        _raise_api_error(resp)
    res = resp.json()
    _set_cached_lookup("uid_resolve", identifier, res, svc)
    return res


def locket_resolve(identifier: str, force_refresh: bool = False) -> dict:
    """
    POST /api/uid/resolve (service='locket')
    Tra cứu Username Locket ra UID & Avatar.
    """
    return resolve_uid(identifier=identifier, service="locket", force_refresh=force_refresh)


# ─── MUA GÓI / GIA HẠN (Trừ Coin CTV) ────────────────────────────────────────

def create_subscription(uid: str, package_code: str, service: str, note: str = "Order from Telegram Bot") -> dict:
    """
    POST /api/uid/create (300 lần/giờ)
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
        _raise_api_error(resp)
    res = resp.json()
    invalidate_uid_cache(uid, service)
    return res


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
    frame_id: str = "",
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
    if frame_id and frame_id.strip():
        payload["id"] = frame_id.strip()
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


def ctv_delete_frame(frame_id: str) -> dict:
    """
    DELETE /api/v1/ctv/frames?id=...
    Xóa khung widget trên máy chủ locket.2707226.xyz theo ID.
    """
    global _frames_cache_time
    fid = (frame_id or "").strip()
    if not fid:
        raise ValueError("Thiếu ID khung cần xóa")
    endpoint = f"{API_BASE_URL}/api/v1/ctv/frames"
    resp = _client.request(
        "DELETE",
        endpoint,
        params={"id": fid},
        json={"id": fid},
        headers=_headers(),
        timeout=15,
    )
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
    caption_id: str = "",
    group_name: str = "",
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
    if caption_id and caption_id.strip():
        payload["id"] = caption_id.strip()
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
    if group_name and group_name.strip():
        payload["groupName"] = group_name.strip()[:60]

    resp = _client.post(url, json=payload, headers=_headers(), timeout=15)
    if resp.is_error:
        raise Exception(parse_api_error(resp))
    return resp.json()


def ctv_delete_caption(caption_id: str, uid: str = "") -> dict:
    """
    DELETE /api/v1/ctv/captions?id=...&uid=...
    Xóa Caption của khách hàng (khi truyền uid) hoặc Brand Caption CTV (khi không truyền uid).
    """
    cid = (caption_id or "").strip()
    if not cid:
        raise ValueError("Thiếu ID Caption cần xóa")
    url = f"{API_BASE_URL}/api/v1/ctv/captions"
    req_params = {"id": cid}
    payload = {"id": cid}
    if uid and uid.strip():
        req_params["uid"] = uid.strip()
        payload["uid"] = uid.strip()
    resp = _client.request(
        "DELETE",
        url,
        params=req_params,
        json=payload,
        headers=_headers(),
        timeout=15,
    )
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


def _normalize_external_cube_url(raw_url: str) -> str:
    """Chuẩn hóa link Google Drive, Dropbox, GitHub blob sang link tải trực tiếp."""
    import re
    u = raw_url.strip()
    m_gd = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", u)
    if m_gd:
        return f"https://drive.google.com/uc?export=download&id={m_gd.group(1)}"
    if "dropbox.com/" in u:
        u = re.sub(r"[?&]dl=0\b", "", u)
        sep = "&" if "?" in u else "?"
        if "dl=1" not in u:
            u = f"{u}{sep}dl=1"
    m_gh = re.match(r"^https://github\.com/([^/]+/[^/]+)/blob/(.+)$", u)
    if m_gh:
        return f"https://raw.githubusercontent.com/{m_gh.group(1)}/{m_gh.group(2)}"
    return u


def _validate_public_http_url(url_str: str) -> str:
    """Chặn SSRF: chỉ cho phép HTTP/HTTPS công cộng, chặn IP nội bộ/loopback."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url_str)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("Link tải .cube phải bắt đầu bằng https:// hoặc http:// hợp lệ.")
    host = parsed.hostname
    if host.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise ValueError("Không được phép tải từ địa chỉ nội bộ.")
    infos = socket.getaddrinfo(host, None)
    for info in infos:
        ip_str = info[4][0].split("%")[0]
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
            raise ValueError("Địa chỉ máy chủ nguồn không hợp lệ (chặn IP nội bộ).")
    return url_str


def ctv_upload_filter_from_url(external_url: str, name: str = "") -> dict:
    """Tải file .cube từ URL ngoài (tối đa 20MB) rồi đẩy lên API CTV."""
    import re
    norm_url = _normalize_external_cube_url(external_url)
    _validate_public_http_url(norm_url)

    current_url = norm_url
    max_bytes = 20 * 1024 * 1024
    downloaded = bytearray()
    for _ in range(4):
        _validate_public_http_url(current_url)
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=8.0), follow_redirects=False) as dl_client:
            with dl_client.stream("GET", current_url, headers={"User-Agent": "AloPremiumLUT/1.0"}) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    from urllib.parse import urljoin
                    current_url = urljoin(current_url, r.headers["location"])
                    continue
                if r.is_error:
                    raise Exception(f"Không thể tải file từ URL (HTTP {r.status_code}).")
                for chunk in r.iter_bytes(65536):
                    downloaded.extend(chunk)
                    if len(downloaded) > max_bytes:
                        raise Exception("File tải về vượt quá giới hạn tối đa 20MB.")
                break
    else:
        raise Exception("Quá nhiều lượt chuyển hướng khi tải file .cube.")

    raw_bytes = bytes(downloaded)
    if not raw_bytes or b"<html" in raw_bytes[:512].lower():
        raise Exception("Đường dẫn không trả về file .cube hợp lệ (có thể link bị khóa quyền truy cập hoặc là trang HTML).")
    if b"LUT_3D_SIZE" not in raw_bytes[:4096] and b"DOMAIN_" not in raw_bytes[:4096]:
        if not re.search(rb"^\s*[+-]?\d+(\.\d+)?\s+[+-]?\d+(\.\d+)?\s+[+-]?\d+(\.\d+)?\s*$", raw_bytes[:4096], re.M):
            raise Exception("Nội dung tải về không đúng định dạng file 3D LUT (.cube).")

    fname = (name.strip().replace(" ", "_") or "external_lut") + ".cube"
    return ctv_upload_filter(file_bytes=raw_bytes, filename=fname, name=name)
