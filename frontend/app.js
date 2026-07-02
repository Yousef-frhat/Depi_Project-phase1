/**
 * ChargeHub Frontend Application
 * Mobile Recharge & Scratch Cards Platform
 */

const API_BASE = '/api';

let currentUser = null;
let selectedOperator = null;
let selectedAmount = null;

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('token');
    if (token) {
        fetchProfile();
    }
    loadAvailableCards();
});

// ============================================================================
// AUTH FUNCTIONS
// ============================================================================

function showModal(type) {
    document.getElementById('modal-overlay').classList.add('active');
    if (type === 'login') {
        document.getElementById('login-form').style.display = 'block';
        document.getElementById('register-form').style.display = 'none';
    } else {
        document.getElementById('login-form').style.display = 'none';
        document.getElementById('register-form').style.display = 'block';
    }
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
}

async function doLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    if (!email || !password) {
        showToast('يرجى ملء جميع الحقول', 'error');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (data.success) {
            localStorage.setItem('token', data.data.access_token);
            currentUser = data.data.user;
            updateUI();
            closeModal();
            showToast('تم تسجيل الدخول بنجاح', 'success');
            loadTransactions();
        } else {
            showToast(data.error || 'فشل تسجيل الدخول', 'error');
        }
    } catch (e) {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }
}

async function doRegister() {
    const username = document.getElementById('reg-username').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;

    if (!username || !email || !password) {
        showToast('يرجى ملء جميع الحقول', 'error');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password })
        });
        const data = await res.json();

        if (data.success) {
            localStorage.setItem('token', data.data.access_token);
            currentUser = data.data.user;
            updateUI();
            closeModal();
            showToast('تم إنشاء الحساب بنجاح! رصيدك الابتدائي: 0 ج.م', 'success');
        } else {
            showToast(data.error || 'فشل إنشاء الحساب', 'error');
        }
    } catch (e) {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }
}

async function fetchProfile() {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const res = await fetch(`${API_BASE}/auth/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();

        if (data.success) {
            currentUser = data.data;
            updateUI();
            loadTransactions();
        } else {
            localStorage.removeItem('token');
        }
    } catch (e) {
        localStorage.removeItem('token');
    }
}

function logout() {
    localStorage.removeItem('token');
    currentUser = null;
    updateUI();
    showToast('تم تسجيل الخروج', 'success');
}

function updateUI() {
    const authDiv = document.getElementById('nav-auth');
    const userDiv = document.getElementById('nav-user');

    if (currentUser) {
        authDiv.style.display = 'none';
        userDiv.style.display = 'flex';
        document.getElementById('user-name').textContent = currentUser.username;
        document.getElementById('user-balance').textContent = `${currentUser.balance.toFixed(2)} ج.م`;
    } else {
        authDiv.style.display = 'flex';
        userDiv.style.display = 'none';
        document.getElementById('transactions-list').innerHTML = '<p class="empty-state">سجل الدخول لعرض العمليات</p>';
    }
}

// ============================================================================
// RECHARGE FUNCTIONS
// ============================================================================

function selectOperator(el) {
    document.querySelectorAll('.operator-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    selectedOperator = el.dataset.operator;
}

function selectAmount(el) {
    document.querySelectorAll('.amount-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    selectedAmount = parseFloat(el.dataset.amount);
}

async function doRecharge() {
    if (!currentUser) {
        showModal('login');
        return;
    }

    const phone = document.getElementById('phone-number').value.trim();

    if (!selectedOperator) { showToast('اختر الشبكة أولاً', 'error'); return; }
    if (!phone || phone.length !== 11) { showToast('أدخل رقم هاتف صحيح (11 رقم)', 'error'); return; }
    if (!selectedAmount) { showToast('اختر المبلغ', 'error'); return; }

    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/recharge`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                phone_number: phone,
                operator: selectedOperator,
                amount: selectedAmount
            })
        });
        const data = await res.json();

        if (data.success) {
            showToast(data.message, 'success');
            fetchProfile();
            loadTransactions();
            // Reset form
            document.querySelectorAll('.operator-card').forEach(c => c.classList.remove('selected'));
            document.querySelectorAll('.amount-card').forEach(c => c.classList.remove('selected'));
            document.getElementById('phone-number').value = '';
            selectedOperator = null;
            selectedAmount = null;
        } else {
            showToast(data.error || 'فشل الشحن', 'error');
        }
    } catch (e) {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }
}

// ============================================================================
// CARDS FUNCTIONS
// ============================================================================

async function loadAvailableCards() {
    try {
        const res = await fetch(`${API_BASE}/cards/available`);
        const data = await res.json();

        if (data.success) {
            renderCards(data.data);
        }
    } catch (e) {
        console.error('Failed to load cards:', e);
    }
}

function renderCards(cards) {
    const grid = document.getElementById('cards-grid');

    if (!cards || cards.length === 0) {
        grid.innerHTML = '<p class="empty-state">لا توجد كروت متاحة حالياً</p>';
        return;
    }

    const operatorNames = { vodafone: 'فودافون', etisalat: 'اتصالات', orange: 'اورنج', we: 'وي' };

    grid.innerHTML = cards.map(card => `
        <div class="card-item">
            <div class="card-item-header">
                <span class="card-item-operator">${operatorNames[card.operator] || card.operator}</span>
                <span class="card-item-badge">متاح</span>
            </div>
            <div class="card-item-amount">${card.denomination} ج.م</div>
            <div class="card-item-count">${card.available_count} كارت متاح</div>
            <button class="btn btn-primary" onclick="purchaseCard('${card.operator}', ${card.denomination})">شراء كارت</button>
        </div>
    `).join('');
}

async function purchaseCard(operator, denomination) {
    if (!currentUser) {
        showModal('login');
        return;
    }

    if (!confirm(`هل تريد شراء كارت ${operator} بقيمة ${denomination} ج.م؟`)) return;

    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/cards/purchase`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ operator, denomination })
        });
        const data = await res.json();

        if (data.success) {
            const card = data.data.card;
            showToast(`تم الشراء! الرقم التسلسلي: ${card.serial_number}`, 'success');
            alert(`كارت ${operator} - ${denomination} ج.م\n\nالرقم التسلسلي: ${card.serial_number}\nالرقم السري (PIN): ${card.pin}`);
            fetchProfile();
            loadAvailableCards();
            loadTransactions();
        } else {
            showToast(data.error || 'فشل شراء الكارت', 'error');
        }
    } catch (e) {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }
}

// ============================================================================
// TRANSACTIONS
// ============================================================================

async function loadTransactions() {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const res = await fetch(`${API_BASE}/transactions`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();

        if (data.success) {
            renderTransactions(data.data.transactions);
        }
    } catch (e) {
        console.error('Failed to load transactions:', e);
    }
}

function renderTransactions(transactions) {
    const list = document.getElementById('transactions-list');

    if (!transactions || transactions.length === 0) {
        list.innerHTML = '<p class="empty-state">لا توجد عمليات بعد</p>';
        return;
    }

    const typeLabels = { recharge: 'شحن رصيد', card_purchase: 'شراء كارت', deposit: 'إيداع' };
    const typeIcons = { recharge: '📱', card_purchase: '💳', deposit: '💰' };
    const operatorNames = { vodafone: 'فودافون', etisalat: 'اتصالات', orange: 'اورنج', we: 'وي' };

    list.innerHTML = transactions.map(tx => `
        <div class="transaction-item">
            <div class="transaction-info">
                <div class="transaction-icon ${tx.type}">${typeIcons[tx.type] || '📋'}</div>
                <div class="transaction-details">
                    <h4>${typeLabels[tx.type] || tx.type} - ${operatorNames[tx.operator] || tx.operator || ''}</h4>
                    <p>${tx.phone_number || 'كارت فكة'} • ${new Date(tx.created_at).toLocaleDateString('ar-EG')}</p>
                </div>
            </div>
            <div class="transaction-amount">-${tx.amount} ج.م</div>
        </div>
    `).join('');
}

// ============================================================================
// UTILITIES
// ============================================================================

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => { toast.classList.remove('show'); }, 3000);
}

function scrollToSection(id) {
    document.getElementById(id).scrollIntoView({ behavior: 'smooth' });
}
