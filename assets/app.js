/**
 * app.js - Xử lý toàn bộ logic nghiệp vụ mua hàng, kiểm tra tài khoản, VietQR & Tra cứu
 * Giữ nguyên 100% API, tham số và tương thích hoàn toàn với web_server.py
 */

let systemProducts = {};
let selectedProduct = 'locket';
let selectedPlan = 'ltm';
let verifiedAccountData = null;
let currentOrderData = null;
let pollTimer = null;
let countdownInterval = null;
let appliedCouponData = null;

// ============================================================
// 1. KHỞI TẠO HỆ THỐNG & TẢI DỮ LIỆU ĐỘNG TỪ SERVER
// ============================================================
async function initSystem() {
    try {
        // Tải cấu hình ngân hàng & hệ thống
        try {
            const cfgRes = await fetch('/api/config');
            if (cfgRes.ok) {
                window.sysConfig = await cfgRes.json();
            }
        } catch (e) {
            console.warn('Lỗi nạp config:', e);
        }

        // Tải danh mục gói cước & giá bán mới nhất từ backend
        const res = await fetch('/api/packages?_t=' + Date.now(), { cache: 'no-store' });
        if (res.ok) {
            const data = await res.json();
            systemProducts = data.products || {};

            // Cập nhật Top Banner ưu đãi (nếu có từ admin)
            if (data.banner) {
                const bannerEl = document.getElementById('topPromoBanner');
                const tagEl = document.getElementById('topPromoTag');
                const textEl = document.getElementById('topPromoText');
                if (bannerEl) {
                    if (data.banner.enabled === false) {
                        bannerEl.style.display = 'none';
                    } else {
                        bannerEl.style.display = 'flex';
                        if (tagEl && data.banner.tag) tagEl.textContent = data.banner.tag;
                        if (textEl && data.banner.text) textEl.innerHTML = data.banner.text;
                    }
                }
            }
        }
    } catch (err) {
        console.error('Lỗi khởi tạo hệ thống:', err);
    }

    // Khởi tạo tab Locket mặc định
    selectProduct('locket');

    // Kiểm tra đơn hàng đang chờ thanh toán gần nhất
    const savedOrderId = localStorage.getItem('last_order_id');
    if (savedOrderId) {
        const resumeBtn = document.getElementById('resumePaymentButton');
        if (resumeBtn) {
            resumeBtn.style.display = 'block';
            resumeBtn.textContent = `📋 Xem lại đơn gần nhất (${savedOrderId})`;
        }
    }
}

// ============================================================
// 2. CHUYỂN ĐỔI SẢN PHẨM & RENDER GÓI CƯỚC
// ============================================================
function selectProduct(prodKey) {
    selectedProduct = prodKey;
    verifiedAccountData = null;

    // Cập nhật active tab
    ['locket', 'spotify', 'locket_spotify', 'locket_ai'].forEach(pk => {
        const btn = document.getElementById('quickTab_' + pk);
        if (btn) {
            if (pk === prodKey) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        }
    });

    // Ẩn avatar đã xác thực trước đó
    const preview = document.getElementById('accountProfileCard');
    if (preview) preview.style.display = 'none';

    const errBox = document.getElementById('accountErrorMsg');
    if (errBox) errBox.style.display = 'none';

    // Cấu hình form theo từng dịch vụ
    const badge = document.getElementById('activeProductBadge');
    const label = document.getElementById('accountInputLabel');
    const input = document.getElementById('accountInput');
    const trialBanner = document.getElementById('tiktokTrialBanner');
    const comboContainer = document.getElementById('comboSpotifyInputContainer');
    const studioContainer = document.getElementById('studioAddonContainer');

    if (prodKey === 'locket') {
        if (badge) badge.textContent = '💛 Locket Gold VIP';
        if (label) label.textContent = 'Tên hiển thị / Link Locket của bạn:';
        if (input) {
            input.placeholder = 'Nhập @username hoặc dán link locket.cam/...';
            input.value = '';
        }
        if (trialBanner) trialBanner.style.display = 'flex';
        if (comboContainer) comboContainer.style.display = 'none';
        if (studioContainer) studioContainer.style.display = 'flex';
    } else if (prodKey === 'spotify') {
        if (badge) badge.textContent = '🎵 Spotify Premium';
        if (label) label.textContent = 'Link Profile Spotify của bạn:';
        if (input) {
            input.placeholder = 'Dán link https://open.spotify.com/user/...';
            input.value = '';
        }
        if (trialBanner) trialBanner.style.display = 'none';
        if (comboContainer) comboContainer.style.display = 'none';
        if (studioContainer) studioContainer.style.display = 'none';
    } else if (prodKey === 'locket_spotify') {
        if (badge) badge.textContent = '👑 Combo Duo (Locket + Spotify)';
        if (label) label.textContent = '1. Link / Username Locket:';
        if (input) {
            input.placeholder = 'Nhập @username hoặc link Locket';
            input.value = '';
        }
        if (trialBanner) trialBanner.style.display = 'none';
        if (comboContainer) comboContainer.style.display = 'block';
        if (studioContainer) studioContainer.style.display = 'flex';
    } else if (prodKey === 'locket_ai') {
        if (badge) badge.textContent = '✨ VIP ALL-IN-ONE';
        if (label) label.textContent = 'Tên hiển thị / Username Locket:';
        if (input) {
            input.placeholder = 'Nhập @username hoặc link Locket';
            input.value = '';
        }
        if (trialBanner) trialBanner.style.display = 'none';
        if (comboContainer) comboContainer.style.display = 'none';
        if (studioContainer) studioContainer.style.display = 'flex';
    }

    renderPlanPills();
    updatePayAmount();
}

function renderPlanPills() {
    const container = document.getElementById('planPills');
    if (!container) return;

    const prod = systemProducts[selectedProduct];
    if (!prod || !prod.plans) {
        container.innerHTML = '<div style="color:var(--muted);font-size:14px;">Đang tải danh mục gói cước...</div>';
        return;
    }

    const planKeys = Object.keys(prod.plans);
    if (!planKeys.includes(selectedPlan)) {
        selectedPlan = planKeys[planKeys.length - 1]; // Chọn gói vĩnh viễn hoặc dài nhất mặc định
    }

    container.innerHTML = '';
    planKeys.forEach(pk => {
        const p = prod.plans[pk];
        const pill = document.createElement('div');
        pill.className = `vip-plan-pill ${pk === selectedPlan ? 'active' : ''}`;
        pill.onclick = () => selectPlan(pk);
        pill.innerHTML = `
            <div class="vip-pill-label">${p.label || pk}</div>
            <div class="vip-pill-price">${(p.price || 0).toLocaleString('vi-VN')}đ</div>
        `;
        container.appendChild(pill);
    });
}

function selectPlan(planKey) {
    selectedPlan = planKey;
    const container = document.getElementById('planPills');
    if (container) {
        const pills = container.querySelectorAll('.vip-plan-pill');
        const prod = systemProducts[selectedProduct];
        if (prod && prod.plans) {
            const keys = Object.keys(prod.plans);
            pills.forEach((p, idx) => {
                if (keys[idx] === planKey) {
                    p.classList.add('active');
                } else {
                    p.classList.remove('active');
                }
            });
        }
    }
    updatePayAmount();
}

function quickSelectTrial5k() {
    selectProduct('locket');
    selectPlan('test');
    const input = document.getElementById('accountInput');
    if (input) input.focus();
    showToast('⚡ Đã chọn Gói Test Dùng Thử 24h (5.000đ)!');
}

// ============================================================
// 3. TÍNH TOÁN GIÁ TIỀN & MÃ GIẢM GIÁ (COUPON)
// ============================================================
function updatePayAmount() {
    let basePrice = 0;
    const prod = systemProducts[selectedProduct];
    if (prod && prod.plans && prod.plans[selectedPlan]) {
        basePrice = prod.plans[selectedPlan].price || 0;
    }

    // Addon Studio Caption (+10.000đ)
    const studioCb = document.getElementById('studioCheckbox');
    if (studioCb && studioCb.checked) {
        basePrice += 10000;
    }

    // Trừ mã giảm giá (nếu có)
    let discount = 0;
    if (appliedCouponData) {
        if (appliedCouponData.discount_pct) {
            discount = Math.round(basePrice * (appliedCouponData.discount_pct / 100));
        } else if (appliedCouponData.discount_amount) {
            discount = appliedCouponData.discount_amount;
        }
    }

    const finalAmount = Math.max(0, basePrice - discount);

    const payBtn = document.getElementById('btnPayAmount');
    if (payBtn) {
        payBtn.textContent = finalAmount.toLocaleString('vi-VN') + 'đ';
    }
    return finalAmount;
}

async function applyCouponCode() {
    const input = document.getElementById('couponInput');
    const code = (input ? input.value : '').trim().toUpperCase();
    const statusMsg = document.getElementById('couponStatusMsg');
    const badge = document.getElementById('couponBadge');
    const clearBtn = document.getElementById('btnClearCoupon');

    if (!code) {
        if (statusMsg) {
            statusMsg.textContent = 'Vui lòng nhập mã giảm giá!';
            statusMsg.style.display = 'block';
            statusMsg.style.color = '#dc2626';
        }
        return;
    }

    try {
        const prod = systemProducts[selectedProduct];
        const basePrice = (prod && prod.plans && prod.plans[selectedPlan]) ? prod.plans[selectedPlan].price : 200000;

        const res = await fetch('/api/check_coupon', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code, price: basePrice })
        });
        const data = await res.json();

        if (data.ok && (data.discount_pct || data.discount_amount)) {
            appliedCouponData = data;
            if (badge) {
                badge.textContent = `✓ Giảm ${data.discount_pct ? data.discount_pct + '%' : data.discount_amount.toLocaleString('vi-VN') + 'đ'}`;
                badge.style.display = 'inline-block';
            }
            if (statusMsg) {
                statusMsg.textContent = 'Áp dụng mã giảm giá thành công!';
                statusMsg.style.display = 'block';
                statusMsg.style.color = '#059669';
            }
            if (clearBtn) clearBtn.style.display = 'block';
            updatePayAmount();
            showToast('🎉 Đã áp dụng mã giảm giá!');
        } else {
            appliedCouponData = null;
            if (badge) badge.style.display = 'none';
            if (statusMsg) {
                statusMsg.textContent = data.error || 'Mã giảm giá không hợp lệ!';
                statusMsg.style.display = 'block';
                statusMsg.style.color = '#dc2626';
            }
            updatePayAmount();
        }
    } catch (err) {
        console.error('Lỗi check coupon:', err);
        if (statusMsg) {
            statusMsg.textContent = 'Lỗi kết nối máy chủ khi kiểm tra mã!';
            statusMsg.style.display = 'block';
            statusMsg.style.color = '#dc2626';
        }
    }
}

function clearCoupon() {
    appliedCouponData = null;
    const input = document.getElementById('couponInput');
    const badge = document.getElementById('couponBadge');
    const statusMsg = document.getElementById('couponStatusMsg');
    const clearBtn = document.getElementById('btnClearCoupon');

    if (input) input.value = '';
    if (badge) badge.style.display = 'none';
    if (statusMsg) statusMsg.style.display = 'none';
    if (clearBtn) clearBtn.style.display = 'none';
    updatePayAmount();
    showToast('Đã xóa mã giảm giá');
}

// ============================================================
// 4. KIỂM TRA TÀI KHOẢN (CHECK UID & AVATAR)
// ============================================================
async function checkAccount() {
    const input = document.getElementById('accountInput');
    const identifier = (input ? input.value : '').trim();
    const errBox = document.getElementById('accountErrorMsg');
    const btnText = document.getElementById('btnCheckAccountText');
    const preview = document.getElementById('accountProfileCard');

    if (!identifier) {
        if (errBox) {
            errBox.textContent = 'Vui lòng nhập Username hoặc dán Link tài khoản!';
            errBox.style.display = 'block';
        }
        return;
    }

    if (errBox) errBox.style.display = 'none';
    if (btnText) btnText.textContent = 'Đang kiểm tra...';

    try {
        const res = await fetch('/api/check_account', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service: selectedProduct, identifier: identifier })
        });
        const data = await res.json();

        if (data.ok) {
            verifiedAccountData = data;
            if (preview) {
                const ava = document.getElementById('profileAvatar');
                const name = document.getElementById('profileDisplayName');
                const uid = document.getElementById('profileDetailText');

                if (ava) ava.src = data.avatar || '/assets/logos/flat_yellow.webp';
                if (name) name.textContent = data.display_name || identifier;
                if (uid) uid.textContent = `UID: ${data.uid || 'Hợp lệ'}`;
                preview.style.display = 'flex';
            }
            showToast('✓ Tài khoản hợp lệ!');
        } else {
            verifiedAccountData = null;
            if (preview) preview.style.display = 'none';
            if (errBox) {
                errBox.textContent = data.error || 'Không tìm thấy tài khoản. Vui lòng kiểm tra lại!';
                errBox.style.display = 'block';
            }
        }
    } catch (err) {
        console.error('Lỗi check account:', err);
        if (errBox) {
            errBox.textContent = 'Lỗi kết nối máy chủ xác thực!';
            errBox.style.display = 'block';
        }
    } finally {
        if (btnText) btnText.textContent = 'Kiểm tra';
    }
}

// Hỗ trợ nút dán nhanh (Paste Clipboard)
async function pasteAccountInput() {
    try {
        const text = await navigator.clipboard.readText();
        const input = document.getElementById('accountInput');
        if (input && text) {
            input.value = text.trim();
            checkAccount();
        }
    } catch (e) {
        showToast('Vui lòng cấp quyền dán hoặc dán thủ công!');
    }
}

// ============================================================
// 5. TẠO ĐƠN HÀNG & MỞ MODAL VIETQR THANH TOÁN
// ============================================================
async function openPaymentModal() {
    const input = document.getElementById('accountInput');
    const identifier = (input ? input.value : '').trim();
    const errBox = document.getElementById('accountErrorMsg');

    if (!identifier) {
        if (errBox) {
            errBox.textContent = 'Vui lòng nhập tài khoản trước khi thanh toán!';
            errBox.style.display = 'block';
            input.focus();
        }
        return;
    }

    let spotifyIdentifier = '';
    if (selectedProduct === 'locket_spotify') {
        const spInput = document.getElementById('spotifyAccountInput');
        spotifyIdentifier = (spInput ? spInput.value : '').trim();
        if (!spotifyIdentifier) {
            if (errBox) {
                errBox.textContent = 'Vui lòng nhập Link Profile Spotify cho gói Combo Duo!';
                errBox.style.display = 'block';
            }
            return;
        }
    }

    const studioCb = document.getElementById('studioCheckbox');
    const hasStudio = studioCb ? studioCb.checked : false;
    const couponCode = appliedCouponData ? (document.getElementById('couponInput')?.value || '').trim() : '';

    const submitBtn = document.querySelector('.vip-btn-submit');
    if (submitBtn) submitBtn.disabled = true;

    try {
        const payload = {
            product: selectedProduct,
            plan: selectedPlan,
            identifier: identifier,
            spotify_identifier: spotifyIdentifier,
            has_studio: hasStudio,
            coupon_code: couponCode
        };

        const res = await fetch('/api/create_order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const order = await res.json();

        if (order.ok) {
            currentOrderData = order;
            localStorage.setItem('last_order_id', order.order_id);

            // Cập nhật giao diện modal thanh toán
            const modal = document.getElementById('paymentModal');
            const waitBox = document.getElementById('modalWaitingPayment');
            const successBox = document.getElementById('modalSuccessPayment');

            if (waitBox) waitBox.style.display = 'block';
            if (successBox) successBox.style.display = 'none';

            // Thông tin ngân hàng & QR
            const prodName = document.getElementById('modalProductName');
            const amtEl = document.getElementById('modalAmount');
            const accEl = document.getElementById('modalAccountNo');
            const holderEl = document.getElementById('modalAccountHolder');
            const bankEl = document.getElementById('modalBankName');
            const memoEl = document.getElementById('modalMemo');
            const qrImg = document.getElementById('modalQrImg');

            if (prodName) prodName.textContent = order.product_name || 'Locket Gold VIP';
            if (amtEl) amtEl.textContent = (order.price || 0).toLocaleString('vi-VN') + 'đ';
            if (accEl) accEl.textContent = order.bank_account || (window.sysConfig && window.sysConfig.bank_account) || '34528022007';
            if (holderEl) holderEl.textContent = order.account_holder || (window.sysConfig && window.sysConfig.account_holder) || 'NGUYEN NHU QUYNH';
            if (bankEl) bankEl.textContent = order.bank_name || (window.sysConfig && window.sysConfig.bank_name) || 'TPBank';
            if (memoEl) memoEl.textContent = `ORDER_${order.order_id}`;

            // Sinh mã QR VietQR chuẩn
            const qrUrl = order.qr_url || `/api/qr?data=${encodeURIComponent(`ORDER_${order.order_id}`)}&bank=${encodeURIComponent(order.bank_id || 'TPB')}&account=${encodeURIComponent(order.bank_account || '34528022007')}&amount=${order.price}&memo=${encodeURIComponent(`ORDER_${order.order_id}`)}`;
            if (qrImg) qrImg.src = qrUrl;

            // Mở modal
            if (modal) modal.classList.add('open');

            // Bắt đầu đếm ngược 10 phút & polling trạng thái
            startCountdown(10 * 60);
            startPollingOrderStatus(order.order_id);
        } else {
            alert('Lỗi tạo đơn hàng: ' + (order.error || 'Vui lòng thử lại!'));
        }
    } catch (err) {
        console.error('Lỗi thanh toán:', err);
        alert('Lỗi kết nối máy chủ tạo đơn!');
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }
}

function resumeLastOrder() {
    const savedId = localStorage.getItem('last_order_id');
    if (!savedId) return;

    fetch(`/api/order_status?order_id=${savedId}`)
        .then(r => r.json())
        .then(order => {
            if (order.ok) {
                currentOrderData = order;
                const modal = document.getElementById('paymentModal');
                const waitBox = document.getElementById('modalWaitingPayment');
                const successBox = document.getElementById('modalSuccessPayment');

                if (order.is_paid || order.status === 'done') {
                    handlePaymentSuccess(order);
                } else {
                    if (waitBox) waitBox.style.display = 'block';
                    if (successBox) successBox.style.display = 'none';

                    const prodName = document.getElementById('modalProductName');
                    const amtEl = document.getElementById('modalAmount');
                    const memoEl = document.getElementById('modalMemo');
                    const qrImg = document.getElementById('modalQrImg');

                    if (prodName) prodName.textContent = order.product || 'Gói VIP';
                    if (amtEl) amtEl.textContent = (order.price || 0).toLocaleString('vi-VN') + 'đ';
                    if (memoEl) memoEl.textContent = `ORDER_${order.order_id}`;
                    if (qrImg) qrImg.src = `/api/qr?memo=ORDER_${order.order_id}&amount=${order.price}`;

                    startCountdown(10 * 60);
                    startPollingOrderStatus(order.order_id);
                }
                if (modal) modal.classList.add('open');
            } else {
                showToast('Không tìm thấy thông tin đơn gần nhất!');
            }
        })
        .catch(() => showToast('Lỗi nạp lại đơn hàng!'));
}

// ============================================================
// 6. ĐẾM NGƯỢC & POLLING KIỂM TRA CHUYỂN KHOẢN (SEPAY)
// ============================================================
function startCountdown(durationSeconds) {
    clearInterval(countdownInterval);
    let remaining = durationSeconds;
    const timerEl = document.getElementById('paymentCountdownTimer');

    function tick() {
        const m = Math.floor(remaining / 60);
        const s = remaining % 60;
        if (timerEl) {
            timerEl.textContent = `⏱️ Đơn hàng hết hạn sau: ${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
        }
        if (remaining <= 0) {
            clearInterval(countdownInterval);
            if (timerEl) timerEl.textContent = '⚠️ Đơn hàng đã hết hạn thanh toán!';
        }
        remaining--;
    }
    tick();
    countdownInterval = setInterval(tick, 1000);
}

function startPollingOrderStatus(orderId) {
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/api/order_status?order_id=${encodeURIComponent(orderId)}`);
            if (res.ok) {
                const data = await res.json();
                if (data.ok && (data.is_paid || data.status === 'done')) {
                    clearInterval(pollTimer);
                    clearInterval(countdownInterval);
                    handlePaymentSuccess(data);
                }
            }
        } catch (e) {
            console.warn('Polling error:', e);
        }
    }, 2000);
}

function handlePaymentSuccess(data) {
    const waitBox = document.getElementById('modalWaitingPayment');
    const successBox = document.getElementById('modalSuccessPayment');

    if (waitBox) waitBox.style.display = 'none';
    if (successBox) successBox.style.display = 'block';

    // Bắn pháo hoa confetti chúc mừng
    if (typeof confetti === 'function') {
        confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });
    }

    // Thiết lập đường link tải cấu hình & cài đặt Safari
    const safariBtn = document.getElementById('modalSafariBtn');
    const downloadBtn = document.getElementById('modalDownloadBtn');

    const exactDns = data.direct_safari_url || data.dns_link || (window.sysConfig && window.sysConfig.dns_url) || 'https://doh.2707226.xyz/alopremiumshop';
    const downloadUrl = data.download_url || `/api/download_profile?order_id=${data.order_id}`;

    if (safariBtn) safariBtn.href = exactDns;
    if (downloadBtn) downloadBtn.href = downloadUrl;

    showToast('🎉 Thanh toán thành công! Gói VIP đã được kích hoạt.');
}

function closePaymentModal() {
    clearInterval(pollTimer);
    clearInterval(countdownInterval);
    const modal = document.getElementById('paymentModal');
    if (modal) modal.classList.remove('open');
}

// ============================================================
// 7. TIỆN ÍCH SAO CHÉP & TOAST NOTIFICATION
// ============================================================
function copyText(text, label) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
        showToast(`✓ Đã sao chép ${label || ''}: ${text}`);
    }).catch(() => {
        showToast('Vui lòng sao chép thủ công!');
    });
}

function showToast(msg) {
    let toast = document.getElementById('globalToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'globalToast';
        toast.className = 'vip-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 2600);
}

// ============================================================
// 8. MODAL TRA CỨU ĐƠN HÀNG & RESET THIẾT BỊ
// ============================================================
function openLookupModal() {
    const modal = document.getElementById('lookupModal');
    if (modal) modal.classList.add('open');
}

function closeLookupModal() {
    const modal = document.getElementById('lookupModal');
    if (modal) modal.classList.remove('open');
}

async function performLookup() {
    const input = document.getElementById('lookupInput');
    const query = (input ? input.value : '').trim();
    const resultBox = document.getElementById('lookupResultContainer');

    if (!query) {
        showToast('Vui lòng nhập mã đơn hoặc username!');
        return;
    }

    if (resultBox) resultBox.innerHTML = '<div style="text-align:center;color:var(--muted);padding:10px;">Đang tra cứu...</div>';

    try {
        const res = await fetch(`/api/order_status?order_id=${encodeURIComponent(query)}`);
        const data = await res.json();

        if (data.ok) {
            const isDone = data.is_paid || data.status === 'done';
            resultBox.innerHTML = `
                <div style="background:var(--cream);border-radius:18px;padding:16px;border:1px solid var(--line);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span style="font-weight:800;font-size:15px;">Mã đơn: ORDER_${data.order_id}</span>
                        <span style="font-size:12px;font-weight:800;padding:3px 8px;border-radius:999px;background:${isDone ? '#ecfdf5' : '#fff7ed'};color:${isDone ? '#059669' : '#ea580c'};">
                            ${isDone ? 'ĐÃ KÍCH HOẠT' : 'CHỜ THANH TOÁN'}
                        </span>
                    </div>
                    <div style="font-size:13px;color:var(--muted);margin-bottom:10px;">
                        Dịch vụ: <b>${data.product || 'Gói VIP'}</b> • ${(data.price || 0).toLocaleString('vi-VN')}đ
                    </div>
                    ${isDone ? `
                        <a href="${data.direct_safari_url || data.dns_link || '#'}" target="_blank" class="vip-btn-safari" style="margin-top:6px;padding:10px;">🌐 Cài Đặt Qua Safari</a>
                        <a href="${data.download_url || `/api/download_profile?order_id=${data.order_id}`}" class="vip-btn-download" style="margin-top:6px;padding:10px;">📥 Tải File .mobileconfig</a>
                    ` : `
                        <button onclick="closeLookupModal(); openPaymentModal();" class="vip-btn-submit" style="margin-top:6px;padding:10px;font-size:14px;">Thanh Toán Ngay</button>
                    `}
                </div>
            `;
        } else {
            resultBox.innerHTML = '<div style="text-align:center;color:#dc2626;padding:10px;">Không tìm thấy đơn hàng tương ứng!</div>';
        }
    } catch (e) {
        if (resultBox) resultBox.innerHTML = '<div style="text-align:center;color:#dc2626;padding:10px;">Lỗi kết nối máy chủ!</div>';
    }
}

function openResetModal() {
    const modal = document.getElementById('resetModal');
    if (modal) modal.classList.add('open');
}

function closeResetModal() {
    const modal = document.getElementById('resetModal');
    if (modal) modal.classList.remove('open');
}

async function executeDeviceReset() {
    const input = document.getElementById('resetIdentifierInput');
    const identifier = (input ? input.value : '').trim();
    const service = document.querySelector('input[name="resetServiceType"]:checked')?.value || 'spotify';
    const statusBox = document.getElementById('resetStatusBox');

    if (!identifier) {
        showToast('Vui lòng nhập tài khoản cần đổi máy!');
        return;
    }

    if (statusBox) statusBox.innerHTML = '<div style="color:var(--muted);">Đang xử lý reset thiết bị...</div>';

    try {
        const endpoint = service === 'spotify' ? '/api/reset_spotify' : '/api/reset_locket';
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: identifier })
        });
        const data = await res.json();

        if (data.ok) {
            statusBox.innerHTML = `<div style="color:#059669;font-weight:700;">✓ ${data.message || 'Reset thiết bị thành công! Bạn có thể cài lại trên máy mới.'}</div>`;
            showToast('✓ Reset thiết bị thành công!');
        } else {
            statusBox.innerHTML = `<div style="color:#dc2626;font-weight:700;">❌ ${data.error || 'Không thể reset thiết bị. Vui lòng kiểm tra lại tài khoản!'}</div>`;
        }
    } catch (e) {
        statusBox.innerHTML = '<div style="color:#dc2626;">Lỗi kết nối máy chủ khi reset!</div>';
    }
}

// Tự động khởi chạy khi tải xong DOM
document.addEventListener('DOMContentLoaded', initSystem);
