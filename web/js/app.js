/**
 * GLOCK SHOP — Frontend Application
 * Полностью автономная клиентская логика:
 * - Каталог товаров и категорий
 * - Мультивалютность (USD / RUB)
 * - Авторизация через Telegram Login Widget + Демо-вход
 * - Единый баланс и скидочная система лояльности
 * - Оплата через CryptoBot (авто-поллинг) и Tonkeeper (QR, Deep Link, проверка)
 * - Реферальная система на сайт (?ref=ID)
 * - История покупок и выдача цифровых товаров
 */

// Глобальное состояние приложения
const state = {
  currency: localStorage.getItem('glock_currency') || 'USD',
  activeCategory: null,
  activeSubcategory: null,
  searchQuery: '',
  categories: [],
  products: [],
  user: null,
  selectedProduct: null,
  topupAmount: 5.0,
  topupMethod: 'cryptobot',
  activeCryptoInvoiceId: null,
  cryptoPollTimer: null,
  activeTonkeeperId: null,
  config: {
    shop_title: 'GLOCK SHOP',
    bot_username: '',
    exchange_rate: 90.0,
    support_url: 'https://t.me/glock_admin_bot',
    ton_wallet: ''
  }
};

// ==========================================
// УПРАВЛЕНИЕ ТОКЕНАМИ И АВТОРИЗАЦИЕЙ (SESSION)
// ==========================================

function getAuthToken() {
  return localStorage.getItem('glock_session_token') || '';
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem('glock_session_token', token);
  } else {
    localStorage.removeItem('glock_session_token');
  }
}

async function apiFetch(url, options = {}) {
  const opts = { ...options };
  const headers = { ...(opts.headers || {}) };
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  opts.headers = headers;
  opts.credentials = 'include';
  return fetch(url, opts);
}

// ==========================================
// ИНИЦИАЛИЗАЦИЯ
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  // 1. Проверяем реферальный параметр в URL (?ref=123456)
  const urlParams = new URLSearchParams(window.location.search);
  const ref = urlParams.get('ref');
  if (ref) {
    localStorage.setItem('glock_ref_id', ref);
    console.log('[Ref] Зафиксирован реферер ID:', ref);
  }

  // 2. Устанавливаем валюту в UI
  applyCurrencyButtons();

  // 3. Загружаем системные параметры и пользователя (с автовосстановлением сессии)
  await loadInitData();

  // 4. Загружаем каталог товаров
  await loadCatalog();

  // 5. Регистрируем Telegram Auth Callback
  window.onTelegramAuth = handleTelegramAuthCallback;
}

// Загрузка начальных параметров магазина и сессии
async function loadInitData() {
  try {
    const token = getAuthToken();
    const initUrl = token ? `/api/init?session_token=${encodeURIComponent(token)}` : '/api/init';
    const res = await apiFetch(initUrl);
    if (!res.ok) throw new Error('Ошибка связи с сервером');
    const data = await res.json();
    
    state.config.shop_title = data.shop_title || 'GLOCK SHOP';
    state.config.bot_username = data.bot_username || '';
    state.config.exchange_rate = data.exchange_rate || 90.0;
    state.config.support_url = data.support_url || 'https://t.me/glock_admin_bot';
    state.config.ton_wallet = data.ton_wallet || '';

    // Обновляем название магазина в шапке
    const titleEl = document.getElementById('shopTitle');
    if (titleEl) titleEl.innerText = state.config.shop_title;

    // Если пользователь авторизован — обновляем состояние и профиль
    if (data.user) {
      state.user = data.user;
      refreshUserProfile().catch(console.warn);
    } else if (token) {
      // Если токен был сохранен, но сервер его не распознал (сброс сессии)
      setAuthToken(null);
      state.user = null;
    }
    renderAuthContainer();

  } catch (err) {
    console.error('Ошибка инициализации:', err);
    showToast('Ошибка подключения к серверу магазина', 'error');
  }
}

// ==========================================
// КАТАЛОГ И КАТЕГОРИИ
// ==========================================

async function loadCatalog() {
  const grid = document.getElementById('productsGrid');
  try {
    const res = await apiFetch('/api/catalog');
    if (!res.ok) throw new Error('Не удалось загрузить каталог');
    const data = await res.json();

    state.categories = data.categories || [];
    state.products = data.products || [];

    // Обновляем счетчики в Hero баннере
    const catCountEl = document.getElementById('totalCatsCount');
    const prodCountEl = document.getElementById('totalProdsCount');
    if (catCountEl) catCountEl.innerText = state.categories.length;
    if (prodCountEl) prodCountEl.innerText = state.products.length;

    renderCategories();
    renderProducts();

  } catch (err) {
    console.error('Ошибка загрузки каталога:', err);
    if (grid) {
      grid.innerHTML = `
        <div class="empty-state">
          <p>⚠️ Не удалось загрузить каталог товаров. Попробуйте обновить страницу.</p>
        </div>
      `;
    }
  }
}

function renderCategories() {
  const container = document.getElementById('categoriesList');
  if (!container) return;

  const totalProds = state.products.length;
  let html = `
    <button class="cat-pill ${state.activeCategory === null ? 'active' : ''}" onclick="selectCategory(null)">
      <span>🔥 Все паки</span>
      <span class="cat-count">${totalProds}</span>
    </button>
  `;

  // Показываем только основные (корневые) разделы: parent_id == null
  const parentCats = state.categories.filter(c => !c.parent_id);

  parentCats.forEach(cat => {
    // Считаем товары этой категории + всех её вложенных подкатегорий
    const count = state.products.filter(p => p.category_id === cat.id || p.parent_category_id === cat.id).length;
    if (count > 0) {
      const isActive = state.activeCategory === cat.id ? 'active' : '';
      html += `
        <button class="cat-pill ${isActive}" onclick="selectCategory(${cat.id})">
          <span>${escapeHtml(cat.name)}</span>
          <span class="cat-count">${count}</span>
        </button>
      `;
    }
  });

  container.innerHTML = html;
}

function selectCategory(catId) {
  state.activeCategory = catId;
  state.activeSubcategory = null; // Сброс выбранной подкатегории

  // Обновляем заголовок раздела
  const titleEl = document.getElementById('currentCategoryTitle');
  if (titleEl) {
    if (catId === null) {
      titleEl.innerText = 'Все доступные паки моделей';
    } else {
      const cat = state.categories.find(c => c.id === catId);
      titleEl.innerText = cat ? `Раздел: ${cat.name}` : 'Каталог';
    }
  }

  renderCategories();
  renderSubcategories();
  renderProducts();
}

function renderSubcategories() {
  const subContainer = document.getElementById('subcategoriesList');
  if (!subContainer) return;

  if (state.activeCategory === null) {
    subContainer.style.display = 'none';
    subContainer.innerHTML = '';
    return;
  }

  // Ищем подкатегории для текущей выбранной категории (где parent_id == activeCategory)
  const subcats = state.categories.filter(c => c.parent_id === state.activeCategory);

  if (subcats.length === 0) {
    subContainer.style.display = 'none';
    subContainer.innerHTML = '';
    return;
  }

  const parentCat = state.categories.find(c => c.id === state.activeCategory);
  const totalCount = state.products.filter(p => p.category_id === state.activeCategory || p.parent_category_id === state.activeCategory).length;

  let html = `
    <button class="subcat-pill ${state.activeSubcategory === null ? 'active' : ''}" onclick="selectSubcategory(null)">
      <span>💎 Все паки (${totalCount})</span>
    </button>
  `;

  subcats.forEach(sc => {
    const scCount = state.products.filter(p => p.category_id === sc.id).length;
    if (scCount > 0) {
      const isActive = state.activeSubcategory === sc.id ? 'active' : '';
      html += `
        <button class="subcat-pill ${isActive}" onclick="selectSubcategory(${sc.id})">
          <span>📦 ${escapeHtml(sc.name)} (${scCount})</span>
        </button>
      `;
    }
  });

  subContainer.innerHTML = html;
  subContainer.style.display = 'flex';
}

function selectSubcategory(subcatId) {
  state.activeSubcategory = subcatId;
  renderSubcategories();
  renderProducts();
}

function handleSearch() {
  const input = document.getElementById('searchInput');
  state.searchQuery = input ? input.value.trim().toLowerCase() : '';
  renderProducts();
}

function renderProducts() {
  const grid = document.getElementById('productsGrid');
  const countBadge = document.getElementById('visibleProductsCount');
  if (!grid) return;

  let filtered = state.products;

  // Фильтр по категории / подкатегории
  if (state.activeSubcategory !== null) {
    filtered = filtered.filter(p => p.category_id === state.activeSubcategory);
  } else if (state.activeCategory !== null) {
    filtered = filtered.filter(p => p.category_id === state.activeCategory || p.parent_category_id === state.activeCategory);
  }

  // Фильтр по поисковому запросу
  if (state.searchQuery) {
    filtered = filtered.filter(p => {
      const name = (p.name || '').toLowerCase();
      const desc = (p.description || '').toLowerCase();
      const cat = (p.category_name || '').toLowerCase();
      return name.includes(state.searchQuery) || desc.includes(state.searchQuery) || cat.includes(state.searchQuery);
    });
  }

  if (countBadge) {
    countBadge.innerText = `${filtered.length} паков`;
  }

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">🔍</span>
        <h3>Ничего не найдено</h3>
        <p>Попробуйте выбрать другой раздел или сбросить фильтр</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.map(prod => {
    const photo = (prod.photos && prod.photos[0]) ? prod.photos[0] : '/static/img/product_placeholder.png';
    const priceStr = formatPrice(prod.price_cents);
    const oldPriceStr = prod.old_price_cents ? formatPrice(prod.old_price_cents) : '';
    
    // Бейдж скидки
    let badgeHtml = '';
    if (prod.discount_pct > 0) {
      badgeHtml = `<span class="badge badge-discount">-${prod.discount_pct}%</span>`;
    }

    // Бейдж наличия
    const stockBadge = prod.in_stock 
      ? '<span class="badge badge-stock">В наличии</span>' 
      : '<span class="badge badge-out">Закончился</span>';

    // Бейдж типа пака
    const packName = prod.category_name || '';
    const packBadge = packName ? `<span class="badge badge-pack">${escapeHtml(packName)}</span>` : '';

    // Очищаем описание модели от экранированных слэшей и форматируем
    let cleanDesc = (prod.description || '')
      .replace(/\\/g, ' • ')
      .replace(/—/g, ' • ')
      .replace(/\s*•\s*/g, ' • ')
      .replace(/\s+/g, ' ')
      .trim();

    return `
      <div class="product-card" onclick="openProductModal(${prod.id})">
        <div class="card-image-wrap">
          <img src="${photo}" alt="${escapeHtml(prod.name)}" loading="lazy" onerror="this.src='/static/img/product_placeholder.png'">
          <div class="card-badges">
            ${packBadge}
            ${badgeHtml}
            ${stockBadge}
          </div>
          <div class="card-image-overlay"></div>
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(prod.name)}</h3>
          <p class="card-desc" title="${escapeAttr(cleanDesc)}">${escapeHtml(cleanDesc)}</p>
          <div class="card-footer">
            <div class="price-box">
              <span class="price-current">${priceStr}</span>
              ${oldPriceStr ? `<span class="price-old">${oldPriceStr}</span>` : ''}
            </div>
            <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); openProductModal(${prod.id})">
              Купить
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ==========================================
// МОДАЛЬНОЕ ОКНО ТОВАРА
// ==========================================

function openProductModal(prodId) {
  const prod = state.products.find(p => p.id === prodId);
  if (!prod) return;

  state.selectedProduct = prod;

  // Фото
  const imgEl = document.getElementById('modalProductImg');
  const photo = (prod.photos && prod.photos[0]) ? prod.photos[0] : '/static/img/product_placeholder.png';
  if (imgEl) imgEl.src = photo;

  // Название и описание
  const titleEl = document.getElementById('modalTitle');
  const descEl = document.getElementById('modalDesc');
  if (titleEl) titleEl.innerText = prod.name;
  if (descEl) descEl.innerText = prod.description || 'Описание товара отсутствует.';

  // Бейджи
  const badgesEl = document.getElementById('modalBadges');
  if (badgesEl) {
    let bHtml = '';
    if (prod.discount_pct > 0) {
      bHtml += `<span class="badge badge-discount">Скидка -${prod.discount_pct}%</span>`;
    }
    if (prod.in_stock) {
      const cnt = prod.kind === 'oneoff' ? ` (${prod.stock_count} шт.)` : '';
      bHtml += `<span class="badge badge-stock">В наличии${cnt}</span>`;
    } else {
      bHtml += `<span class="badge badge-out">Товар распродан</span>`;
    }
    badgesEl.innerHTML = bHtml;
  }

  // Расчет персональной скидки лояльности пользователя
  let finalCents = prod.price_cents;
  let loyaltyDiscountPercent = 0;
  if (state.user && state.user.loyalty && state.user.loyalty.percent > 0) {
    loyaltyDiscountPercent = state.user.loyalty.percent;
    finalCents = Math.round(prod.price_cents * (100 - loyaltyDiscountPercent) / 100);
  }

  // Цены
  const priceEl = document.getElementById('modalPrice');
  const oldPriceEl = document.getElementById('modalOldPrice');
  if (priceEl) {
    priceEl.innerText = formatPrice(finalCents);
  }
  if (oldPriceEl) {
    if (loyaltyDiscountPercent > 0) {
      oldPriceEl.innerText = `${formatPrice(prod.price_cents)} (-${loyaltyDiscountPercent}% VIP)`;
    } else if (prod.old_price_cents) {
      oldPriceEl.innerText = formatPrice(prod.old_price_cents);
    } else {
      oldPriceEl.innerText = '';
    }
  }

  // Кнопка покупки с баланса
  const buyBtn = document.getElementById('btnBuyBalance');
  if (buyBtn) {
    if (!prod.in_stock) {
      buyBtn.disabled = true;
      buyBtn.innerText = '❌ Товар закончился';
      buyBtn.className = 'btn btn-outline btn-block disabled';
    } else if (!state.user) {
      buyBtn.disabled = false;
      buyBtn.innerText = '✈️ Войти для покупки';
      buyBtn.className = 'btn btn-primary btn-block';
    } else if (state.user.balance_cents < finalCents) {
      const diffCents = finalCents - state.user.balance_cents;
      buyBtn.disabled = false;
      buyBtn.innerText = `➕ Пополнить на ${formatPrice(diffCents)} и купить`;
      buyBtn.className = 'btn btn-primary btn-block';
    } else {
      buyBtn.disabled = false;
      buyBtn.innerText = `💳 Купить с баланса (${formatPrice(finalCents)})`;
      buyBtn.className = 'btn btn-primary btn-block';
    }
  }

  openModal('productModal');
}

// Покупка текущего выбранного товара с баланса
async function buyCurrentProduct() {
  if (!state.selectedProduct) return;

  // Если не авторизован — открываем окно входа
  if (!state.user) {
    openLoginModal();
    return;
  }

  const prod = state.selectedProduct;
  if (!prod.in_stock) {
    showToast('Товара нет в наличии', 'error');
    return;
  }

  // Проверка баланса
  let finalCents = prod.price_cents;
  if (state.user.loyalty && state.user.loyalty.percent > 0) {
    finalCents = Math.round(prod.price_cents * (100 - state.user.loyalty.percent) / 100);
  }

  if (state.user.balance_cents < finalCents) {
    const neededUsd = ((finalCents - state.user.balance_cents) / 100);
    closeModal('productModal');
    openTopupModal(Math.max(1, Math.ceil(neededUsd)));
    showToast(`Недостаточно средств. Пополните баланс на $${neededUsd.toFixed(2)}`, 'warning');
    return;
  }

  const buyBtn = document.getElementById('btnBuyBalance');
  if (buyBtn) {
    buyBtn.disabled = true;
    buyBtn.innerText = '⏳ Обработка заказа...';
  }

  try {
    const res = await apiFetch('/api/buy/balance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: prod.id })
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      if (data.error === 'no_funds') {
        closeModal('productModal');
        openTopupModal();
        showToast(data.message || 'Недостаточно средств', 'warning');
      } else {
        showToast(data.message || data.error || 'Ошибка при покупке', 'error');
      }
      return;
    }

    // Успешная покупка!
    closeModal('productModal');
    
    // Обновляем профиль и баланс
    await refreshUserProfile();
    await loadCatalog();

    // Показываем окно с полученным товаром
    showSuccessPurchase(data.name, data.content_value);

  } catch (err) {
    console.error('Ошибка покупки:', err);
    showToast('Сетевая ошибка при совершении покупки', 'error');
  } finally {
    if (buyBtn) {
      buyBtn.disabled = false;
      buyBtn.innerText = '💳 Купить с баланса';
    }
  }
}

function showSuccessPurchase(productName, contentValue) {
  const nameEl = document.getElementById('successProdTitle');
  const valEl = document.getElementById('successDeliveredValue');

  if (nameEl) nameEl.innerText = productName || 'Товар оплачен';
  if (valEl) valEl.innerText = contentValue || 'Ваш заказ успешно зарегистрирован!';

  openModal('successPurchaseModal');
}

// Прямая оплата через CryptoBot из окна товара
function startDirectCryptoPay() {
  if (!state.selectedProduct) return;
  if (!state.user) {
    openLoginModal();
    return;
  }

  const amountUsd = (state.selectedProduct.price_cents / 100);
  closeModal('productModal');
  openTopupModal(amountUsd);
  switchPayMethod('cryptobot');
  createCryptoInvoice();
}

// Прямая оплата через Tonkeeper из окна товара
function startDirectTonkeeperPay() {
  if (!state.selectedProduct) return;
  if (!state.user) {
    openLoginModal();
    return;
  }

  const amountUsd = (state.selectedProduct.price_cents / 100);
  closeModal('productModal');
  openTopupModal(amountUsd);
  switchPayMethod('tonkeeper');
}

// ==========================================
// ПОПОЛНЕНИЕ БАЛАНСА (CRYPTOBOT & TONKEEPER)
// ==========================================

function openTopupModal(presetAmount = null) {
  if (!state.user) {
    openLoginModal();
    return;
  }

  if (presetAmount) {
    setTopupAmount(presetAmount);
  } else {
    setTopupAmount(5);
  }

  openModal('topupModal');
}

function setTopupAmount(amt) {
  state.topupAmount = parseFloat(amt);
  const input = document.getElementById('topupAmountInput');
  if (input) input.value = state.topupAmount.toFixed(2);

  // Обновляем активный класс пресетов
  document.querySelectorAll('.preset-btn').forEach(btn => {
    const val = parseFloat(btn.innerText.replace('$', ''));
    if (val === state.topupAmount) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  updateConvertedAmounts();

  // Если открыта вкладка Tonkeeper — пересоздаем заявку с новой суммой
  if (state.topupMethod === 'tonkeeper') {
    createTonkeeperInvoice();
  }
}

function updateConvertedAmounts() {
  const input = document.getElementById('topupAmountInput');
  if (input) {
    const val = parseFloat(input.value) || 0;
    state.topupAmount = val;
    const rubVal = Math.round(val * state.config.exchange_rate);
    const rubPreview = document.getElementById('convertedRubPreview');
    if (rubPreview) rubPreview.innerText = `≈ ${rubVal.toLocaleString('ru-RU')} ₽`;
  }
}

function switchPayMethod(method) {
  state.topupMethod = method;

  const tabCrypto = document.getElementById('tabCryptoBot');
  const tabTon = document.getElementById('tabTonkeeper');
  const contentCrypto = document.getElementById('payContentCryptoBot');
  const contentTon = document.getElementById('payContentTonkeeper');

  if (method === 'cryptobot') {
    tabCrypto.classList.add('active');
    tabTon.classList.remove('active');
    contentCrypto.style.display = 'block';
    contentTon.style.display = 'none';
  } else {
    tabTon.classList.add('active');
    tabCrypto.classList.remove('active');
    contentTon.style.display = 'block';
    contentCrypto.style.display = 'none';
    createTonkeeperInvoice();
  }
}

// ------------------------------------------
// CryptoBot интеграция
// ------------------------------------------

async function createCryptoInvoice() {
  const btn = document.getElementById('btnCreateCryptoInvoice');
  const statusBox = document.getElementById('cryptoInvoiceBox');
  const openLink = document.getElementById('btnOpenCryptoBot');
  const statusText = document.getElementById('cryptoStatusText');

  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch('/api/pay/cryptobot/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount_usd: state.topupAmount })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка создания счета в CryptoBot', 'error');
      if (btn) btn.disabled = false;
      return;
    }

    state.activeCryptoInvoiceId = data.invoice_id;

    if (statusBox) statusBox.style.display = 'block';
    if (openLink) {
      openLink.href = data.pay_url;
      // Автоматически открываем ссылку на счет в новой вкладке
      window.open(data.pay_url, '_blank');
    }
    if (statusText) statusText.innerText = `Ожидание оплаты счета #${data.invoice_id}...`;

    // Запускаем опрос статуса
    startCryptoPolling(data.invoice_id);

  } catch (err) {
    console.error('Ошибка вызова CryptoBot:', err);
    showToast('Сетевая ошибка при обращении к CryptoBot', 'error');
    if (btn) btn.disabled = false;
  }
}

function startCryptoPolling(invoiceId) {
  stopCryptoPolling();

  state.cryptoPollTimer = setInterval(async () => {
    try {
      const res = await apiFetch(`/api/pay/cryptobot/status/${invoiceId}`);
      if (!res.ok) return;
      const data = await res.json();

      if (data.status === 'paid') {
        stopCryptoPolling();
        showToast('🎉 Оплата CryptoBot успешно получена! Баланс пополнен.', 'success');
        await refreshUserProfile();
        closeModal('topupModal');
      } else if (data.status === 'expired') {
        stopCryptoPolling();
        showToast('Срок действия счета в CryptoBot истек.', 'warning');
        const statusText = document.getElementById('cryptoStatusText');
        if (statusText) statusText.innerText = 'Срок действия счета истек.';
      }
    } catch (err) {
      console.warn('Ошибка проверки инвойса:', err);
    }
  }, 3000);
}

function stopCryptoPolling() {
  if (state.cryptoPollTimer) {
    clearInterval(state.cryptoPollTimer);
    state.cryptoPollTimer = null;
  }
}

// ------------------------------------------
// Tonkeeper интеграция
// ------------------------------------------

async function createTonkeeperInvoice() {
  const qrContainer = document.getElementById('tonQrCode');
  const amountEl = document.getElementById('tonkeeperAmount');
  const walletEl = document.getElementById('tonkeeperWallet');
  const commentEl = document.getElementById('tonkeeperComment');
  const appBtn = document.getElementById('btnTonkeeperApp');

  if (qrContainer) qrContainer.innerHTML = '<div class="spinner-small"></div>';

  try {
    const res = await apiFetch('/api/pay/tonkeeper/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount_usd: state.topupAmount })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка генерации реквизитов Tonkeeper', 'error');
      if (qrContainer) qrContainer.innerHTML = '<span>Ошибка генерации QR</span>';
      return;
    }

    state.activeTonkeeperId = data.topup_id;

    if (amountEl) amountEl.innerText = `${data.amount_ton} TON`;
    if (walletEl) walletEl.innerText = data.wallet;
    if (commentEl) commentEl.innerText = data.comment;
    if (appBtn) appBtn.href = data.universal_link;

    // Генерация красивого QR-кода
    if (qrContainer && typeof QRCode !== 'undefined') {
      qrContainer.innerHTML = '';
      new QRCode(qrContainer, {
        text: data.universal_link,
        width: 150,
        height: 150,
        colorDark: '#000000',
        colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.M
      });
    }

  } catch (err) {
    console.error('Ошибка Tonkeeper:', err);
    showToast('Сетевая ошибка при связи с сервером', 'error');
  }
}

async function checkTonkeeperPayment() {
  if (!state.activeTonkeeperId) {
    showToast('Сначала создайте заявку на оплату', 'warning');
    return;
  }

  const btn = document.getElementById('btnCheckTonkeeper');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '🔄 Проверяем блокчейн TON...';
  }

  try {
    const res = await apiFetch('/api/pay/tonkeeper/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topup_id: state.activeTonkeeperId })
    });

    const data = await res.json();

    if (data.status === 'paid') {
      showToast('💎 Транзакция найдена! Баланс успешно пополнен.', 'success');
      await refreshUserProfile();
      closeModal('topupModal');
    } else {
      showToast(data.message || 'Платеж еще не дошел. Подождите 1-2 минуты.', 'info');
    }

  } catch (err) {
    console.error('Ошибка проверки Tonkeeper:', err);
    showToast('Ошибка при обращении к узлу TON', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🔄 Проверить оплату';
    }
  }
}

// ==========================================
// ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ, ЛОЯЛЬНОСТЬ И РЕФЕРАЛЫ
// ==========================================

async function openProfileModal() {
  if (!state.user) {
    openLoginModal();
    return;
  }

  await refreshUserProfile();
  openModal('profileModal');
}

async function refreshUserProfile() {
  try {
    const res = await apiFetch('/api/user/me');
    if (!res.ok) {
      if (res.status === 401) {
        setAuthToken(null);
        state.user = null;
        renderAuthContainer();
      }
      return;
    }

    const data = await res.json();
    state.user = data;
    renderAuthContainer();

    // Заполняем данные модального окна профиля
    const nameEl = document.getElementById('profName');
    const idEl = document.getElementById('profId');
    const balanceEl = document.getElementById('profBalance');
    const avatarEl = document.getElementById('profAvatar');

    if (nameEl) nameEl.innerText = data.username ? `@${data.username}` : `Пользователь #${data.id}`;
    if (idEl) idEl.innerText = `Telegram ID: ${data.id}`;
    if (balanceEl) balanceEl.innerText = formatPrice(data.balance_cents);
    if (avatarEl) {
      const char = (data.username ? data.username[0] : '') || '👤';
      avatarEl.innerText = char.toUpperCase();
    }

    // Лояльность
    const loyalty = data.loyalty;
    if (loyalty) {
      const tierEl = document.getElementById('profLoyaltyTier');
      const spentEl = document.getElementById('profTotalSpent');
      const progressEl = document.getElementById('profLoyaltyProgress');
      const hintEl = document.getElementById('profLoyaltyHint');

      const tierName = loyalty.name || loyalty.tier || 'Базовый';
      const badge = loyalty.badge || '';
      if (tierEl) tierEl.innerText = `${badge} ${tierName} (${loyalty.percent || 0}%)`.trim();
      if (spentEl) spentEl.innerText = `Всего покупок: ${data.total_spent_usd}`;
      if (progressEl) progressEl.style.width = `${Math.min(100, Math.max(8, loyalty.progress_pct || 15))}%`;
      if (hintEl) {
        if (loyalty.next_name && loyalty.needed_rub) {
          hintEl.innerText = `До уровня «${loyalty.next_name}» осталось покупок на ${loyalty.needed_rub} ₽`;
        } else {
          hintEl.innerText = loyalty.next_hint || 'Достигайте новых статусов для получения постоянной VIP-скидки!';
        }
      }
    }

    // Реферальная система сайта
    const ref = data.referral;
    if (ref) {
      const linkInput = document.getElementById('profRefLink');
      const invitedEl = document.getElementById('profRefInvited');
      const percentEl = document.getElementById('profRefPercent');
      const earnedEl = document.getElementById('profRefEarned');

      if (linkInput) linkInput.value = ref.link;
      if (invitedEl) invitedEl.innerText = ref.invited_count;
      if (percentEl) percentEl.innerText = `${ref.percent}%`;
      if (earnedEl) earnedEl.innerText = ref.earned_usd;
    }

    // История покупок
    const purchasesList = document.getElementById('profPurchasesList');
    if (purchasesList) {
      const items = data.purchases || [];
      if (items.length === 0) {
        purchasesList.innerHTML = '<p class="empty-hint">У вас пока нет покупок. Перейдите в каталог!</p>';
      } else {
        purchasesList.innerHTML = items.map(p => `
          <div class="purchase-card">
            <div class="purchase-card-top">
              <span class="purchase-card-name">📦 ${escapeHtml(p.product_name)}</span>
              <span class="purchase-card-date">${escapeHtml(p.created_at || '')}</span>
            </div>
            <div class="purchase-card-link-row">
              <span class="purchase-card-link">${escapeHtml(p.content_value || 'Цифровой товар')}</span>
              <button class="btn-copy-card" onclick="copyRawText('${escapeAttr(p.content_value || '')}')">Скопировать</button>
            </div>
          </div>
        `).join('');
      }
    }

  } catch (err) {
    console.error('Ошибка обновления профиля:', err);
  }
}

// Отрисовка кнопки входа / профиля в шапке
function renderAuthContainer() {
  const container = document.getElementById('authContainer');
  if (!container) return;

  if (state.user) {
    const displayName = state.user.username ? `@${state.user.username}` : `ID: ${state.user.id}`;
    const balanceFormatted = formatPrice(state.user.balance_cents);
    container.innerHTML = `
      <div class="user-chip" onclick="openProfileModal()">
        <div class="user-chip-avatar">👤</div>
        <div class="user-chip-meta">
          <span class="user-chip-name">${escapeHtml(displayName)}</span>
          <span class="user-chip-balance">${balanceFormatted}</span>
        </div>
      </div>
    `;
  } else {
    container.innerHTML = `
      <button class="btn btn-primary btn-login" onclick="openLoginModal()">
        <span class="tg-icon">✈️</span> Войти через Telegram
      </button>
    `;
  }
}

async function logout() {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {
    console.warn(e);
  }
  setAuthToken(null);
  state.user = null;
  renderAuthContainer();
  closeModal('profileModal');
  showToast('Вы успешно вышли из аккаунта', 'info');
}

// ==========================================
// АВТОРИЗАЦИЯ TELEGRAM
// ==========================================

let botAuthPollTimer = null;
let currentAuthUserId = null;
let currentAuthUsername = null;
let resendCountdownTimer = null;

function openLoginModal() {
  if (botAuthPollTimer) {
    clearInterval(botAuthPollTimer);
    botAuthPollTimer = null;
  }
  if (resendCountdownTimer) {
    clearInterval(resendCountdownTimer);
    resendCountdownTimer = null;
  }

  // Сброс на шаг 1
  backToIdentifierStep();

  const idInput = document.getElementById('loginIdentifier');
  if (idInput) idInput.value = '';
  const otpInput = document.getElementById('loginOtpCode');
  if (otpInput) otpInput.value = '';

  const waitingEl = document.getElementById('botAuthWaiting');
  if (waitingEl) waitingEl.style.display = 'none';
  const btnAuth = document.getElementById('btnAuthViaBot');
  if (btnAuth) {
    btnAuth.disabled = false;
    btnAuth.innerHTML = '<span class="tg-paper-icon">✈️</span> Войти в 1 клик через бота';
  }

  const btnSend = document.getElementById('btnSendCode');
  if (btnSend) {
    btnSend.disabled = false;
    btnSend.innerHTML = 'Получить код в Telegram 🚀';
  }

  openModal('loginModal');
  setTimeout(() => {
    if (idInput) idInput.focus();
  }, 100);
}

function backToIdentifierStep() {
  const stepId = document.getElementById('loginStepIdentifier');
  const stepCode = document.getElementById('loginStepCode');
  if (stepId) stepId.style.display = 'block';
  if (stepCode) stepCode.style.display = 'none';

  const idInput = document.getElementById('loginIdentifier');
  if (idInput) idInput.focus();
}

// Шаг 1: Запрос одноразового кода в Telegram
async function handleSendCode() {
  const input = document.getElementById('loginIdentifier');
  const btnSend = document.getElementById('btnSendCode');
  const rawVal = input ? input.value.trim() : '';

  if (!rawVal) {
    showToast('Введите ваш никнейм (@username) или Telegram ID', 'warning');
    if (input) input.focus();
    return;
  }

  try {
    if (btnSend) {
      btnSend.disabled = true;
      btnSend.innerHTML = '<div class="spinner-small"></div> Отправка кода в Telegram...';
    }

    const res = await apiFetch('/api/auth/send_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier: rawVal })
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(data.error || 'Не удалось отправить код', 'error');
      if (btnSend) {
        btnSend.disabled = false;
        btnSend.innerHTML = 'Получить код в Telegram 🚀';
      }
      return;
    }

    // Успешно отправлено
    currentAuthUserId = data.user_id;
    currentAuthUsername = data.username;

    const targetUserEl = document.getElementById('otpTargetUsername');
    if (targetUserEl) targetUserEl.innerText = `@${data.username}`;

    const stepId = document.getElementById('loginStepIdentifier');
    const stepCode = document.getElementById('loginStepCode');
    if (stepId) stepId.style.display = 'none';
    if (stepCode) stepCode.style.display = 'block';

    const otpInput = document.getElementById('loginOtpCode');
    if (otpInput) {
      otpInput.value = '';
      otpInput.focus();
    }

    startResendCountdown(60);
    showToast(`Код отправлен пользователю @${data.username} в Telegram! 📲`, 'success');

  } catch (err) {
    console.error('Ошибка запроса кода:', err);
    showToast('Ошибка при запросе кода. Попробуйте еще раз', 'error');
  } finally {
    if (btnSend) {
      btnSend.disabled = false;
      btnSend.innerHTML = 'Получить код в Telegram 🚀';
    }
  }
}

function startResendCountdown(seconds) {
  const btnResend = document.getElementById('btnResendCode');
  if (!btnResend) return;

  if (resendCountdownTimer) clearInterval(resendCountdownTimer);

  let remaining = seconds;
  btnResend.disabled = true;
  btnResend.style.pointerEvents = 'none';
  btnResend.style.opacity = '0.5';
  btnResend.innerText = `Отправить повторно (${remaining}s)`;

  resendCountdownTimer = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(resendCountdownTimer);
      resendCountdownTimer = null;
      btnResend.disabled = false;
      btnResend.style.pointerEvents = 'auto';
      btnResend.style.opacity = '1';
      btnResend.innerText = 'Отправить повторно';
    } else {
      btnResend.innerText = `Отправить повторно (${remaining}s)`;
    }
  }, 1000);
}

function handleResendCode() {
  handleSendCode();
}

// Шаг 2: Проверка 6-значного кода
async function handleVerifyCode() {
  const otpInput = document.getElementById('loginOtpCode');
  const btnVerify = document.getElementById('btnVerifyCode');
  const codeVal = otpInput ? otpInput.value.trim() : '';

  if (!codeVal || codeVal.length < 6) {
    showToast('Введите 6 цифр кода из сообщения', 'warning');
    if (otpInput) otpInput.focus();
    return;
  }

  if (!currentAuthUserId) {
    showToast('Ошибка сессии авторизации. Запросите код заново', 'error');
    backToIdentifierStep();
    return;
  }

  try {
    if (btnVerify) {
      btnVerify.disabled = true;
      btnVerify.innerHTML = '<div class="spinner-small"></div> Проверка кода...';
    }

    const payload = {
      user_id: currentAuthUserId,
      code: codeVal
    };
    const savedRef = localStorage.getItem('glock_ref_id');
    if (savedRef) {
      payload.referrer_id = savedRef;
    }

    const res = await apiFetch('/api/auth/verify_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(data.error || 'Неверный код подтверждения', 'error');
      if (otpInput) {
        otpInput.select();
      }
      return;
    }

    if (data.token) {
      setAuthToken(data.token);
    }
    state.user = data.user;
    renderAuthContainer();
    refreshUserProfile().catch(console.warn);
    closeModal('loginModal');

    const dispName = data.user.username ? `@${data.user.username}` : (data.user.first_name || `ID ${data.user.id}`);
    showToast(`Добро пожаловать, ${dispName}! 🎉`, 'success');

    if (state.selectedProduct) {
      openProductModal(state.selectedProduct.id);
    }

  } catch (err) {
    console.error('Ошибка проверки кода:', err);
    showToast('Ошибка проверки кода. Попробуйте еще раз', 'error');
  } finally {
    if (btnVerify) {
      btnVerify.disabled = false;
      btnVerify.innerHTML = 'Подтвердить и войти 🔑';
    }
  }
}

// Альтернативный способ: Вход в 1 клик через бота
async function startBotAuthFlow() {
  const btnAuth = document.getElementById('btnAuthViaBot');
  const waitingEl = document.getElementById('botAuthWaiting');
  const statusText = document.getElementById('botAuthStatusText');

  try {
    if (btnAuth) btnAuth.disabled = true;
    if (waitingEl) waitingEl.style.display = 'flex';
    if (statusText) statusText.innerText = 'Создание сессии входа...';

    const res = await apiFetch('/api/auth/bot_create', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.token) {
      throw new Error(data.error || 'Не удалось создать токен авторизации');
    }

    const botUrl = data.bot_url;
    const botName = data.bot_username || 'glock_models_bot';
    if (statusText) {
      statusText.innerHTML = `Открываем бота... Нажмите <b>Старт</b> в <a href="${botUrl}" target="_blank" style="color:#fff;text-decoration:underline;">@${botName}</a>`;
    }

    // Открываем Telegram deep-link
    window.open(botUrl, '_blank');

    // Опрашиваем сервер каждые 1.5 секунды
    if (botAuthPollTimer) clearInterval(botAuthPollTimer);
    let elapsed = 0;
    botAuthPollTimer = setInterval(async () => {
      elapsed += 1500;
      if (elapsed > 120000) {
        clearInterval(botAuthPollTimer);
        botAuthPollTimer = null;
        if (waitingEl) waitingEl.style.display = 'none';
        if (btnAuth) btnAuth.disabled = false;
        showToast('Время ожидания входа истекло. Попробуйте снова.', 'warning');
        return;
      }

      try {
        const pollRes = await apiFetch(`/api/auth/bot_poll/${data.token}`);
        const pollData = await pollRes.json();
        if (pollData.status === 'confirmed' && pollData.user) {
          clearInterval(botAuthPollTimer);
          botAuthPollTimer = null;
          if (waitingEl) waitingEl.style.display = 'none';
          if (btnAuth) btnAuth.disabled = false;

          if (pollData.token) {
            setAuthToken(pollData.token);
          }
          state.user = pollData.user;
          renderAuthContainer();
          refreshUserProfile().catch(console.warn);
          closeModal('loginModal');
          const dispName = pollData.user.username ? `@${pollData.user.username}` : (pollData.user.first_name || `ID ${pollData.user.id}`);
          showToast(`Добро пожаловать, ${dispName}!`, 'success');

          if (state.selectedProduct) {
            openProductModal(state.selectedProduct.id);
          }
        }
      } catch (pollErr) {
        console.warn('Ошибка проверки токена:', pollErr);
      }
    }, 1500);

  } catch (err) {
    console.error('Ошибка входа через бота:', err);
    showToast(err.message || 'Ошибка входа через бота', 'error');
    if (btnAuth) btnAuth.disabled = false;
    if (waitingEl) waitingEl.style.display = 'none';
  }
}

// Callback на случай внешнего Telegram Login Widget
async function handleTelegramAuthCallback(user) {
  try {
    const payload = { ...user };
    const savedRef = localStorage.getItem('glock_ref_id');
    if (savedRef) {
      payload.referrer_id = savedRef;
    }

    const res = await apiFetch('/api/auth/telegram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка авторизации Telegram', 'error');
      return;
    }

    if (data.token) {
      setAuthToken(data.token);
    }
    state.user = data.user;
    renderAuthContainer();
    refreshUserProfile().catch(console.warn);
    closeModal('loginModal');
    showToast(`Добро пожаловать, ${data.user.username ? '@' + data.user.username : data.user.first_name}!`, 'success');

    if (state.selectedProduct) {
      openProductModal(state.selectedProduct.id);
    }

  } catch (err) {
    console.error('Ошибка входа через Telegram:', err);
    showToast('Ошибка при входе через Telegram', 'error');
  }
}

// ==========================================
// ВАЛЮТА И ФОРМАТИРОВАНИЕ
// ==========================================

function setCurrency(curr) {
  state.currency = curr;
  localStorage.setItem('glock_currency', curr);
  applyCurrencyButtons();

  renderProducts();
  renderAuthContainer();

  if (state.selectedProduct) {
    openProductModal(state.selectedProduct.id);
  }
}

function applyCurrencyButtons() {
  const btnUSD = document.getElementById('btnUSD');
  const btnRUB = document.getElementById('btnRUB');

  if (state.currency === 'RUB') {
    if (btnRUB) btnRUB.classList.add('active');
    if (btnUSD) btnUSD.classList.remove('active');
  } else {
    if (btnUSD) btnUSD.classList.add('active');
    if (btnRUB) btnRUB.classList.remove('active');
  }
}

function formatPrice(cents) {
  if (state.currency === 'RUB') {
    const rub = Math.round(cents * state.config.exchange_rate / 100);
    return `${rub.toLocaleString('ru-RU')} ₽`;
  } else {
    return `$${(cents / 100).toFixed(2)}`;
  }
}

// ==========================================
// УПРАВЛЕНИЕ МОДАЛЬНЫМИ ОКНАМИ
// ==========================================

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
  if (modalId === 'topupModal') {
    stopCryptoPolling();
  }
  if (modalId === 'loginModal') {
    if (botAuthPollTimer) {
      clearInterval(botAuthPollTimer);
      botAuthPollTimer = null;
    }
    if (resendCountdownTimer) {
      clearInterval(resendCountdownTimer);
      resendCountdownTimer = null;
    }
  }
}

function closeModalOnOverlay(event, modalId) {
  if (event.target && event.target.classList.contains('modal-overlay')) {
    closeModal(modalId);
  }
}

// ==========================================
// УТИЛИТЫ И TOASTS
// ==========================================

function copyText(elementId, isInput = false) {
  const el = document.getElementById(elementId);
  if (!el) return;

  const text = isInput ? el.value : el.innerText;
  copyRawText(text);
}

function copyRawText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast('Скопировано в буфер обмена! 📋', 'success');
  }).catch(() => {
    showToast('Не удалось скопировать', 'error');
  });
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerText = message;

  container.appendChild(toast);

  // Плавное появление
  setTimeout(() => toast.classList.add('visible'), 10);

  // Удаление через 3.5 секунды
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function truncate(str, maxLen = 60) {
  if (!str) return '';
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str;
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeAttr(text) {
  if (!text) return '';
  return String(text).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
