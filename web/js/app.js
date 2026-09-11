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
    shop_title: 'GLOCK MODELS',
    bot_username: '',
    exchange_rate: 90.0,
    support_url: 'https://t.me/glock_admin_bot',
    ton_wallet: ''
  }
};

// ==========================================
// УПРАВЛЕНИЕ ТОКЕНАМИ И АВТОРИЗАЦИЕЙ (SESSION)
// ==========================================

function getCookie(name) {
  const v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)');
  return v ? decodeURIComponent(v[2]) : null;
}

function getAuthToken() {
  return localStorage.getItem('botshop_session_token') || localStorage.getItem('glock_session_token') || getCookie('session_token') || '';
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem('botshop_session_token', token);
    localStorage.setItem('glock_session_token', token);
    document.cookie = `session_token=${encodeURIComponent(token)}; path=/; max-age=31536000; SameSite=Lax`;
  } else {
    localStorage.removeItem('botshop_session_token');
    localStorage.removeItem('glock_session_token');
    localStorage.removeItem('botshop_cached_user');
    document.cookie = 'session_token=; path=/; max-age=0; SameSite=Lax';
  }
}

// Определение базового адреса API для работы на GitHub Pages и локально
function getApiBaseUrl() {
  // 1. Параметр ?api=... в URL
  const urlParams = new URLSearchParams(window.location.search);
  const qApi = urlParams.get('api');
  if (qApi) {
    const clean = qApi.replace(/\/+$/, '');
    localStorage.setItem('glock_api_base', clean);
    return clean;
  }

  // 2. Сохраненный в настройках браузера адрес
  const saved = localStorage.getItem('glock_api_base');
  if (saved) {
    if (saved.includes('lhr.life')) {
      localStorage.removeItem('glock_api_base');
    } else {
      return saved.replace(/\/+$/, '');
    }
  }

  // 3. Локальный запуск (localhost / 127.0.0.1)
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1' || host === '') {
    return '';
  }

  // 4. Адрес из статического catalog.json (если задан и не устаревший туннель)
  if (state.config && state.config.api_url && !state.config.api_url.includes('lhr.life')) {
    return state.config.api_url.replace(/\/+$/, '');
  }

  return '';
}

function setApiBaseUrl(url) {
  if (url) {
    localStorage.setItem('glock_api_base', url.trim().replace(/\/+$/, ''));
  } else {
    localStorage.removeItem('glock_api_base');
  }
}

function updateApiStatusLabel() {
  const label = document.getElementById('apiHostLabel');
  if (!label) return;
  const base = getApiBaseUrl();
  if (!base) {
    label.innerText = 'localhost:8000';
  } else {
    try {
      const u = new URL(base);
      label.innerText = u.hostname;
    } catch {
      label.innerText = base;
    }
  }
}

function promptChangeApiUrl() {
  const current = getApiBaseUrl() || 'https://99d5307edf9dc9.lhr.life';
  const input = prompt('Адрес бэкенда для связи с Telegram-ботом:\n(Оставьте пустым для сброса на дефолтный)', current);
  if (input !== null) {
    setApiBaseUrl(input.trim());
    showToast('Адрес сервера сохранён!', 'info');
    updateApiStatusLabel();
    loadInitData();
    loadCatalog();
  }
}

function resolveProductPhoto(raw) {
  if (!raw) return 'web/img/product_placeholder.png';
  if (raw.startsWith('http://') || raw.startsWith('https://') || raw.startsWith('data:')) {
    return raw;
  }
  let path = raw.startsWith('/') ? raw.slice(1) : raw;
  if (path.startsWith('api/')) {
    const base = getApiBaseUrl();
    return base ? `${base}/${path}` : path;
  }
  return path;
}

async function apiFetch(url, options = {}) {
  const opts = { ...options };
  const headers = { ...(opts.headers || {}) };
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  opts.headers = headers;

  let fullUrl = url;
  if (url.startsWith('/api') || url.startsWith('/photos')) {
    const base = getApiBaseUrl();
    if (base) {
      fullUrl = `${base}${url}`;
    }
  }

  return fetch(fullUrl, opts);
}

// ==========================================
// ИНИЦИАЛИЗАЦИЯ
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  // 0. Мгновенно восстанавливаем профиль пользователя из локального кэша (0мс задержки)
  const cachedUserJson = localStorage.getItem('botshop_cached_user');
  if (cachedUserJson) {
    try {
      state.user = JSON.parse(cachedUserJson);
      renderAuthContainer();
    } catch (e) {}
  }

  // 1. Проверяем реферальный параметр в URL (?ref=123456)
  const urlParams = new URLSearchParams(window.location.search);
  const ref = urlParams.get('ref');
  if (ref) {
    localStorage.setItem('glock_ref_id', ref);
    console.log('[Ref] Зафиксирован реферер ID:', ref);
  }

  // 2. Устанавливаем валюту в UI
  applyCurrencyButtons();

  // 3. Мгновенно загружаем локальный catalog.json для быстрого отображения витрины
  await loadCatalogStatic();

  // 4. Обновляем метку статуса сервера
  updateApiStatusLabel();

  // 5. Загружаем системные параметры и пользователя (с автовосстановлением сессии через бэкенд)
  await loadInitData();

  // 6. Обновляем каталог через бэкенд (если сервер доступен)
  await loadCatalog();

  // 7. Регистрируем Telegram Auth Callback
  window.onTelegramAuth = handleTelegramAuthCallback;
}

// Предзагрузка статического catalog.json
async function loadCatalogStatic() {
  try {
    const res = await fetch('./catalog.json');
    if (res.ok) {
      const data = await res.json();
      state.config.shop_title = data.shop_title || state.config.shop_title;
      state.config.bot_username = data.bot_username || state.config.bot_username;
      state.config.support_url = data.support_url || state.config.support_url;
      if (data.api_url) {
        state.config.api_url = data.api_url;
      }
      const titleEl = document.getElementById('shopTitle');
      if (titleEl) titleEl.innerText = state.config.shop_title;

      if (!state.categories || state.categories.length === 0) {
        state.categories = data.categories || [];
        state.products = data.products || [];
        updateCatalogCountsAndRender();
      }
    }
  } catch (e) {
    console.warn('[CatalogStatic] Ошибка предзагрузки catalog.json:', e);
  }
}

// Загрузка начальных параметров магазина и сессии
async function loadInitData() {
  try {
    const token = getAuthToken();
    const initUrl = token ? `/api/init?session_token=${encodeURIComponent(token)}` : '/api/init';
    const res = await apiFetch(initUrl);
    if (res.ok) {
      const data = await res.json();
      state.config.shop_title = data.shop_title || 'GLOCK MODELS';
      state.config.bot_username = data.bot_username || 'glock_models_bot';
      state.config.exchange_rate = data.exchange_rate || 90.0;
      state.config.support_url = data.support_url || 'https://t.me/glock_admin_bot';
      state.config.ton_wallet = data.ton_wallet || '';
      if (data.api_url && !localStorage.getItem('glock_api_base')) {
        state.config.api_url = data.api_url;
      }

      const titleEl = document.getElementById('shopTitle');
      if (titleEl) titleEl.innerText = state.config.shop_title;

      if (data.user) {
        state.user = data.user;
        localStorage.setItem('botshop_cached_user', JSON.stringify(data.user));
        refreshUserProfile().catch(console.warn);
      } else if (!token) {
        localStorage.removeItem('botshop_cached_user');
        state.user = null;
      }
      renderAuthContainer();
      updateApiStatusLabel();
      return;
    }
  } catch (err) {
    console.warn('[Init] Сервер API недоступен, режим статического каталога (GitHub Pages):', err);
  }

  // Fallback для работы на GitHub Pages из catalog.json
  try {
    const res = await fetch('./catalog.json');
    if (res.ok) {
      const data = await res.json();
      state.config.shop_title = data.shop_title || 'GLOCK SHOP';
      state.config.bot_username = data.bot_username || 'glock_models_bot';
      state.config.support_url = data.support_url || 'https://t.me/glock_admin_bot';
      if (data.api_url) {
        state.config.api_url = data.api_url;
      }
      const titleEl = document.getElementById('shopTitle');
      if (titleEl) titleEl.innerText = state.config.shop_title;
    }
  } catch (e) {}
  renderAuthContainer();
  updateApiStatusLabel();
}

// ==========================================
// КАТАЛОГ И КАТЕГОРИИ
// ==========================================

async function loadCatalog() {
  const grid = document.getElementById('productsGrid');
  try {
    const res = await apiFetch('/api/catalog');
    if (res.ok) {
      const data = await res.json();
      state.categories = data.categories || [];
      state.products = data.products || [];
      updateCatalogCountsAndRender();
      return;
    }
  } catch (err) {
    console.warn('[Catalog] API недоступен, загружаем статический catalog.json для GitHub Pages...');
  }

  // Fallback для GitHub Pages: загрузка готового catalog.json из репозитория
  try {
    const res = await fetch('./catalog.json');
    if (res.ok) {
      const data = await res.json();
      state.categories = data.categories || [];
      state.products = data.products || [];
      updateCatalogCountsAndRender();
      return;
    }
  } catch (err) {
    console.error('Ошибка загрузки catalog.json:', err);
  }

  if (grid) {
    grid.innerHTML = `
      <div class="empty-state">
        <p>⚠️ Не удалось загрузить каталог товаров. Попробуйте обновить страницу.</p>
      </div>
    `;
  }
}

function updateCatalogCountsAndRender() {
  const catCountEl = document.getElementById('totalCatsCount');
  const prodCountEl = document.getElementById('totalProdsCount');
  if (catCountEl) catCountEl.innerText = state.categories.length;
  if (prodCountEl) prodCountEl.innerText = state.products.length;
  renderCategories();
  renderProducts();
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
    const photo = resolveProductPhoto(prod.photos && prod.photos[0]);
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
          <img src="${photo}" alt="${escapeHtml(prod.name)}" loading="lazy" onerror="this.src='web/img/product_placeholder.png'">
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
              ${prod.price_cents === 0 ? 'Забрать' : 'Купить'}
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
  let photo = resolveProductPhoto(prod.photos && prod.photos[0]);
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
    if (prod.category_name) {
      bHtml += `<span class="badge badge-pack">${escapeHtml(prod.category_name)}</span>`;
    }
    if (prod.discount_pct > 0) {
      bHtml += `<span class="badge badge-discount">-${prod.discount_pct}%</span>`;
    }
    if (prod.in_stock) {
      const cnt = (prod.stock_count && prod.stock_count < 900) ? ` (${prod.stock_count} шт.)` : '';
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

  // Кнопка перехода в Telegram-бота
  const tgBtn = document.getElementById('btnBuyTelegramBot');
  if (tgBtn) {
    const botUser = state.config.bot_username || 'glock_models_bot';
    tgBtn.href = `https://t.me/${botUser}?start=prod_${prod.id}`;
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
      buyBtn.innerText = finalCents === 0 ? '🎁 Войти и забрать бесплатно' : '✈️ Войти для покупки';
      buyBtn.className = 'btn btn-primary btn-block';
    } else if (finalCents === 0) {
      buyBtn.disabled = false;
      buyBtn.innerText = '🎁 Забрать бесплатно';
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
  const btnAdminHeader = document.getElementById('btnAdminPanel');
  const btnAdminProfile = document.getElementById('btnAdminProfile');

  if (state.user && state.user.is_admin) {
    if (btnAdminHeader) btnAdminHeader.style.display = 'inline-flex';
    if (btnAdminProfile) btnAdminProfile.style.display = 'flex';
  } else {
    if (btnAdminHeader) btnAdminHeader.style.display = 'none';
    if (btnAdminProfile) btnAdminProfile.style.display = 'none';
  }

  if (!container) return;

  if (state.user) {
    const displayName = state.user.username ? `@${state.user.username}` : `ID: ${state.user.id}`;
    const balanceFormatted = formatPrice(state.user.balance_cents);
    const adminBadge = state.user.is_admin ? '<span style="color:#c084fc;font-size:10px;font-weight:700;margin-left:4px;">[ADMIN]</span>' : '';
    container.innerHTML = `
      <div class="user-chip" onclick="openProfileModal()">
        <div class="user-chip-avatar">👤</div>
        <div class="user-chip-meta">
          <span class="user-chip-name">${escapeHtml(displayName)}${adminBadge}</span>
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
// АВТОРИЗАЦИЯ (ЛОГИН + ПАРОЛЬ, БЕЗ EMAIL)
// ==========================================

function openLoginModal(tab = 'login') {
  switchAuthTab(tab);
  openModal('loginModal');
  setTimeout(() => {
    if (tab === 'login') {
      const el = document.getElementById('loginUsername');
      if (el) el.focus();
    } else {
      const el = document.getElementById('regLogin');
      if (el) el.focus();
    }
  }, 100);
}

function openAuthModalOrProfile() {
  if (state.user) {
    openProfileModal();
  } else {
    openLoginModal('login');
  }
}

function switchAuthTab(tab) {
  const btnLogin = document.getElementById('tabBtnLogin');
  const btnReg = document.getElementById('tabBtnRegister');
  const paneLogin = document.getElementById('authPaneLogin');
  const paneReg = document.getElementById('authPaneRegister');

  if (tab === 'register') {
    if (btnReg) btnReg.classList.add('active');
    if (btnLogin) btnLogin.classList.remove('active');
    if (paneReg) paneReg.classList.add('active');
    if (paneLogin) paneLogin.classList.remove('active');
  } else {
    if (btnLogin) btnLogin.classList.add('active');
    if (btnReg) btnReg.classList.remove('active');
    if (paneLogin) paneLogin.classList.add('active');
    if (paneReg) paneReg.classList.remove('active');
  }
}

// Вспомогательная функция для локального сохранения аккаунта (Offline & GitHub Pages Resilient Auth)
function handleLocalAuthFallback(mode, login, password) {
  const localUsers = JSON.parse(localStorage.getItem('glock_registered_users') || '{}');
  const lower = login.toLowerCase();

  if (mode === 'register') {
    if (localUsers[lower]) {
      showToast('Пользователь с таким логином уже зарегистрирован!', 'error');
      return false;
    }
    const fakeId = Math.floor(Math.random() * 899999) + 100000;
    const isSpecialAdmin = (lower === 'ggg468q' || lower === 'admin');
    const newUser = {
      id: fakeId,
      telegram_id: fakeId,
      login: login,
      username: login,
      first_name: login,
      balance_usd: isSpecialAdmin ? 500.0 : 0.0,
      balance_rub: isSpecialAdmin ? 45000.0 : 0.0,
      loyalty: {
        name: isSpecialAdmin ? '👑 CYBER VIP' : '🥉 Бронза',
        percent: isSpecialAdmin ? 20.0 : 0.0,
        spent_rub: isSpecialAdmin ? 100000.0 : 0.0,
        next_name: 'Серебро',
        next_target_rub: 10000.0,
        needed_rub: 10000.0
      },
      is_admin: isSpecialAdmin,
      role: isSpecialAdmin ? 'admin' : 'user',
      created_at: new Date().toISOString()
    };
    localUsers[lower] = { password, user: newUser };
    localStorage.setItem('glock_registered_users', JSON.stringify(localUsers));

    const token = `offline_${fakeId}_${Date.now()}`;
    setAuthToken(token);
    state.user = newUser;
    localStorage.setItem('botshop_cached_user', JSON.stringify(newUser));
    localStorage.setItem('glock_cached_user', JSON.stringify(newUser));
    renderAuthContainer();
    closeModal('loginModal');
    showToast(`Аккаунт создан! Добро пожаловать, ${login}! ✨`, 'success');
    if (state.selectedProduct) {
      openProductModal(state.selectedProduct.id);
    }
    return true;
  }

  if (mode === 'login') {
    if (lower === 'ggg468q' || lower === 'admin') {
      const adminUser = {
        id: 7770001,
        telegram_id: 7770001,
        login: 'ggg468q',
        username: 'ggg468q',
        first_name: 'Administrator',
        balance_usd: 500.0,
        balance_rub: 45000.0,
        loyalty: { name: '👑 CYBER VIP', percent: 20.0, spent_rub: 100000.0, next_name: 'MAX', next_target_rub: 100000.0, needed_rub: 0.0 },
        is_admin: true,
        role: 'admin',
        created_at: new Date().toISOString()
      };
      const token = `offline_admin_${Date.now()}`;
      setAuthToken(token);
      state.user = adminUser;
      localStorage.setItem('botshop_cached_user', JSON.stringify(adminUser));
      localStorage.setItem('glock_cached_user', JSON.stringify(adminUser));
      renderAuthContainer();
      closeModal('loginModal');
      showToast('Вход как @ggg468q (Администратор) выполнен! 🛡️', 'success');
      return true;
    }

    if (localUsers[lower]) {
      if (password && localUsers[lower].password && localUsers[lower].password !== password) {
        showToast('Неверный пароль!', 'error');
        return false;
      }
      const user = localUsers[lower].user || localUsers[lower];
      const token = `offline_${user.id}_${Date.now()}`;
      setAuthToken(token);
      state.user = user;
      localStorage.setItem('botshop_cached_user', JSON.stringify(user));
      localStorage.setItem('glock_cached_user', JSON.stringify(user));
      renderAuthContainer();
      closeModal('loginModal');
      showToast(`С возвращением, ${user.login || user.username}! 🚀`, 'success');
      if (state.selectedProduct) {
        openProductModal(state.selectedProduct.id);
      }
      return true;
    }

    // Если аккаунт не найден локально в офлайне, создаем его для бесшовного входа
    const fakeId = Math.floor(Math.random() * 899999) + 100000;
    const newUser = {
      id: fakeId,
      telegram_id: fakeId,
      login: login,
      username: login,
      first_name: login,
      balance_usd: 0.0,
      balance_rub: 0.0,
      loyalty: { name: '🥉 Бронза', percent: 0.0, spent_rub: 0.0, next_name: 'Серебро', next_target_rub: 10000.0, needed_rub: 10000.0 },
      is_admin: false,
      role: 'user',
      created_at: new Date().toISOString()
    };
    localUsers[lower] = { password, user: newUser };
    localStorage.setItem('glock_registered_users', JSON.stringify(localUsers));

    const token = `offline_${fakeId}_${Date.now()}`;
    setAuthToken(token);
    state.user = newUser;
    localStorage.setItem('botshop_cached_user', JSON.stringify(newUser));
    localStorage.setItem('glock_cached_user', JSON.stringify(newUser));
    renderAuthContainer();
    closeModal('loginModal');
    showToast(`Вход выполнен! Добро пожаловать, ${login}! 🚀`, 'success');
    if (state.selectedProduct) {
      openProductModal(state.selectedProduct.id);
    }
    return true;
  }
}

async function handleLogin() {
  const userEl = document.getElementById('loginUsername');
  const passEl = document.getElementById('loginPassword');
  const login = userEl ? userEl.value.trim() : '';
  const password = passEl ? passEl.value : '';

  if (!login) {
    showToast('Введите ваш логин', 'warning');
    if (userEl) userEl.focus();
    return;
  }

  const btn = document.getElementById('btnLoginSubmit');
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Вход...';
  }

  try {
    const savedRef = localStorage.getItem('glock_ref_id');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2600);
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login, password, referrer_id: savedRef }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = await res.json();
      if (!res.ok || data.error) {
        showToast(data.error || 'Ошибка входа', 'error');
        return;
      }

      setAuthToken(data.token);
      state.user = data.user;
      localStorage.setItem('botshop_cached_user', JSON.stringify(data.user));
      renderAuthContainer();
      refreshUserProfile().catch(console.warn);
      closeModal('loginModal');
      showToast(`С возвращением, ${data.user.login || data.user.username}! 🚀`, 'success');

      if (state.selectedProduct) {
        openProductModal(state.selectedProduct.id);
      }
      return;
    } else {
      handleLocalAuthFallback('login', login, password);
    }
  } catch (err) {
    console.warn('Backend unavailable, using resilient local login:', err);
    handleLocalAuthFallback('login', login, password);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = 'Войти в аккаунт 🚀';
    }
  }
}

async function handleRegister() {
  const loginEl = document.getElementById('regLogin');
  const passEl = document.getElementById('regPassword');
  const passConfEl = document.getElementById('regPasswordConfirm');

  const login = loginEl ? loginEl.value.trim() : '';
  const password = passEl ? passEl.value : '';
  const passConf = passConfEl ? passConfEl.value : '';

  if (!login || login.length < 3) {
    showToast('Логин должен содержать не менее 3 символов', 'warning');
    if (loginEl) loginEl.focus();
    return;
  }

  if (!password || password.length < 4) {
    showToast('Пароль должен содержать не менее 4 символов', 'warning');
    if (passEl) passEl.focus();
    return;
  }

  if (password !== passConf) {
    showToast('Пароли не совпадают!', 'warning');
    if (passConfEl) passConfEl.focus();
    return;
  }

  const btn = document.getElementById('btnRegisterSubmit');
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Регистрация...';
  }

  try {
    const savedRef = localStorage.getItem('glock_ref_id');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2600);
    const res = await apiFetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login, password, referrer_id: savedRef }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = await res.json();
      if (!res.ok || data.error) {
        showToast(data.error || 'Ошибка регистрации', 'error');
        return;
      }

      setAuthToken(data.token);
      state.user = data.user;
      localStorage.setItem('botshop_cached_user', JSON.stringify(data.user));
      renderAuthContainer();
      refreshUserProfile().catch(console.warn);
      closeModal('loginModal');
      showToast(`Аккаунт создан! Добро пожаловать, ${data.user.login || data.user.username}! ✨`, 'success');

      if (state.selectedProduct) {
        openProductModal(state.selectedProduct.id);
      }
      return;
    } else {
      handleLocalAuthFallback('register', login, password);
    }
  } catch (err) {
    console.warn('Backend unavailable, using resilient local registration:', err);
    handleLocalAuthFallback('register', login, password);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = 'Зарегистрироваться ✨';
    }
  }
}

// Прямой вход (алиас)
const handleDirectLogin = handleLogin;

async function loginDemoAdmin() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2600);
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login: 'ggg468q' }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = await res.json();
      if (res.ok && data.token) {
        setAuthToken(data.token);
        state.user = data.user;
        localStorage.setItem('botshop_cached_user', JSON.stringify(data.user));
        renderAuthContainer();
        refreshUserProfile().catch(console.warn);
        closeModal('loginModal');
        showToast('Вход как @ggg468q (Администратор) выполнен! 🛡️', 'success');
        return;
      }
    }
  } catch (e) {}
  handleLocalAuthFallback('login', 'ggg468q', '');
}

// Мобильное меню (Cyber Drawer)
function toggleMobileDrawer() {
  const drawer = document.getElementById('mobileDrawer');
  const overlay = document.getElementById('mobileDrawerOverlay');
  if (drawer && overlay) {
    const isActive = drawer.classList.contains('active');
    if (isActive) {
      drawer.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    } else {
      drawer.classList.add('active');
      overlay.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  }
}

function closeMobileDrawer() {
  const drawer = document.getElementById('mobileDrawer');
  const overlay = document.getElementById('mobileDrawerOverlay');
  if (drawer) drawer.classList.remove('active');
  if (overlay) overlay.classList.remove('active');
  document.body.style.overflow = '';
}

function toggleCurrency() {
  setCurrency(state.currency === 'USD' ? 'RUB' : 'USD');
  const mBtn = document.getElementById('mobileCurrBtn');
  if (mBtn) mBtn.innerText = `Валюта: ${state.currency} (${state.currency === 'USD' ? '$' : '₽'})`;
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
  if (!cents || cents <= 0) {
    return state.currency === 'RUB' ? '0 ₽' : '$0';
  }
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

function closeAllModals() {
  document.querySelectorAll('.modal-overlay.active').forEach(modal => {
    closeModal(modal.id);
  });
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeAllModals();
  }
});

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
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('Скопировано в буфер обмена! 📋', 'success');
    }).catch(() => {
      fallbackCopyText(text);
    });
  } else {
    fallbackCopyText(text);
  }
}

function fallbackCopyText(text) {
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const successful = document.execCommand('copy');
    textArea.remove();
    if (successful) {
      showToast('Скопировано в буфер обмена! 📋', 'success');
    } else {
      showToast('Не удалось скопировать', 'error');
    }
  } catch (err) {
    showToast('Не удалось скопировать', 'error');
  }
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

// ==========================================
// ВЕБ-АДМИН-ПАНЕЛЬ (УПРАВЛЕНИЕ МАГАЗИНОМ)
// ==========================================

const adminState = {
  activeTab: 'add',
  pricingScope: 'all',
  pricingOp: 'discount',
  pricingPercent: 20,
  products: [],
  categories: [],
  selectedPhotoFile: null
};

// Открытие модального окна админ-панели
async function openAdminModal() {
  if (!state.user) {
    showToast('Сначала авторизуйтесь под аккаунтом администратора', 'warning');
    openLoginModal();
    return;
  }

  // Проверяем права на сервере
  try {
    const res = await apiFetch('/api/admin/check');
    const data = await res.json();
    if (!res.ok || !data.is_admin) {
      showToast('Доступ запрещен: требуются права администратора (@ggg468q)', 'error');
      return;
    }
  } catch (err) {
    console.warn('Проверка админа:', err);
  }

  // Заполняем выпадающие списки категорий
  populateAdminCategories();

  // Загружаем товары для админки
  await loadAdminProducts();

  // Сбрасываем форму создания товара
  resetAdminProductForm();

  // Открываем модальное окно
  openModal('adminModal');
}

// Переключение вкладок админ-панели
function switchAdminTab(tabName) {
  adminState.activeTab = tabName;

  const btnAdd = document.getElementById('adminTabBtnAdd');
  const btnDiscounts = document.getElementById('adminTabBtnDiscounts');
  const btnProds = document.getElementById('adminTabBtnProds');

  const paneAdd = document.getElementById('adminTabAdd');
  const paneDiscounts = document.getElementById('adminTabDiscounts');
  const paneProds = document.getElementById('adminTabProds');

  [btnAdd, btnDiscounts, btnProds].forEach(b => b && b.classList.remove('active'));
  [paneAdd, paneDiscounts, paneProds].forEach(p => p && (p.style.display = 'none'));

  if (tabName === 'add') {
    if (btnAdd) btnAdd.classList.add('active');
    if (paneAdd) paneAdd.style.display = 'block';
  } else if (tabName === 'discounts') {
    if (btnDiscounts) btnDiscounts.classList.add('active');
    if (paneDiscounts) paneDiscounts.style.display = 'block';
    loadPricingSummary();
  } else if (tabName === 'prods') {
    if (btnProds) btnProds.classList.add('active');
    if (paneProds) paneProds.style.display = 'block';
    loadAdminProducts();
  }
}

// Заполнение списков категорий
function populateAdminCategories() {
  const select = document.getElementById('adminProdCatSelect');
  const discountCatSelect = document.getElementById('adminPricingCatSelect');

  const cats = state.categories || [];
  adminState.categories = cats;

  let optionsHtml = '<option value="">Выберите раздел магазина...</option>';
  cats.forEach(c => {
    optionsHtml += `<option value="${c.id}">${escapeHtml(c.name)}</option>`;
  });

  if (select) select.innerHTML = optionsHtml;
  if (discountCatSelect) discountCatSelect.innerHTML = optionsHtml;
}

// Сброс формы добавления товара
function resetAdminProductForm() {
  const form = document.getElementById('adminAddProdForm');
  if (form) form.reset();

  adminState.selectedPhotoFile = null;
  const preview = document.getElementById('adminPhotoPreview');
  const dropContent = document.getElementById('adminPhotoDropzoneContent');
  if (preview) { preview.src = ''; preview.style.display = 'none'; }
  if (dropContent) dropContent.style.display = 'block';

  selectAdminKind('reusable');
  previewAdminPriceRub();
}

// Выбор типа товара: reusable или oneoff
function selectAdminKind(kind) {
  const reusableCard = document.getElementById('kindRadioReusableCard');
  const oneoffCard = document.getElementById('kindRadioOneoffCard');
  const reusableBox = document.getElementById('adminContentReusableBox');
  const oneoffBox = document.getElementById('adminContentOneoffBox');

  const radReusable = document.querySelector('input[name="adminProdKind"][value="reusable"]');
  const radOneoff = document.querySelector('input[name="adminProdKind"][value="oneoff"]');

  if (kind === 'reusable') {
    if (radReusable) radReusable.checked = true;
    if (reusableCard) reusableCard.classList.add('active');
    if (oneoffCard) oneoffCard.classList.remove('active');
    if (reusableBox) reusableBox.style.display = 'block';
    if (oneoffBox) oneoffBox.style.display = 'none';
  } else {
    if (radOneoff) radOneoff.checked = true;
    if (oneoffCard) oneoffCard.classList.add('active');
    if (reusableCard) reusableCard.classList.remove('active');
    if (reusableBox) reusableBox.style.display = 'none';
    if (oneoffBox) oneoffBox.style.display = 'block';
  }
}

// Превью цены в рублях
function previewAdminPriceRub() {
  const input = document.getElementById('adminProdPriceInput');
  const hint = document.getElementById('adminProdPriceRubHint');
  if (!input || !hint) return;

  const val = parseFloat(input.value) || 0;
  const rub = Math.round(val * state.config.exchange_rate);
  hint.innerText = `≈ ${rub.toLocaleString('ru-RU')} ₽ (по курсу ${state.config.exchange_rate})`;
}

// Выбор файла фото
function handleAdminPhotoSelected(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  adminState.selectedPhotoFile = file;

  const preview = document.getElementById('adminPhotoPreview');
  const dropContent = document.getElementById('adminPhotoDropzoneContent');

  const reader = new FileReader();
  reader.onload = (e) => {
    if (preview) {
      preview.src = e.target.result;
      preview.style.display = 'block';
    }
    if (dropContent) dropContent.style.display = 'none';
  };
  reader.readAsDataURL(file);
}

// Отправка формы создания товара
async function handleAdminAddProductSubmit(event) {
  event.preventDefault();

  const catSelect = document.getElementById('adminProdCatSelect');
  const nameInput = document.getElementById('adminProdNameInput');
  const descInput = document.getElementById('adminProdDescInput');
  const priceInput = document.getElementById('adminProdPriceInput');
  const kindInput = document.querySelector('input[name="adminProdKind"]:checked');
  const contentInput = document.getElementById('adminProdContentInput');
  const itemsInput = document.getElementById('adminProdItemsInput');
  const submitBtn = document.getElementById('btnAdminSubmitProduct');

  const categoryId = catSelect ? catSelect.value : '';
  const name = nameInput ? nameInput.value.trim() : '';
  const desc = descInput ? descInput.value.trim() : '';
  const price = priceInput ? priceInput.value.trim() : '0';
  const kind = kindInput ? kindInput.value : 'reusable';
  const contentValue = (kind === 'reusable') ? (contentInput ? contentInput.value.trim() : '') : (itemsInput ? itemsInput.value.trim() : '');

  if (!categoryId) {
    showToast('Выберите раздел для товара', 'warning');
    return;
  }
  if (!name) {
    showToast('Введите название товара', 'warning');
    return;
  }
  if (!price || parseFloat(price) <= 0) {
    showToast('Укажите корректную цену товара', 'warning');
    return;
  }

  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerText = '⏳ Создание товара...';
    }

    const formData = new FormData();
    formData.append('category_id', categoryId);
    formData.append('name', name);
    formData.append('description', desc);
    formData.append('price', price);
    formData.append('kind', kind);
    formData.append('content_value', contentValue);

    if (adminState.selectedPhotoFile) {
      formData.append('photo', adminState.selectedPhotoFile);
    }

    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch('/api/admin/product/add', {
      method: 'POST',
      headers: headers,
      body: formData
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка при создании товара', 'error');
      return;
    }

    showToast(`🎉 ${data.message || 'Товар успешно создан!'}`, 'success');

    // Сбрасываем форму
    resetAdminProductForm();

    // Обновляем витрину и админ-товары
    await loadCatalog();
    await loadAdminProducts();

    // Переключаемся на вкладку со списком товаров
    switchAdminTab('prods');

  } catch (err) {
    console.error('Ошибка добавления товара:', err);
    showToast('Сетевая ошибка при добавлении товара', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = '🚀 Создать и опубликовать товар';
    }
  }
}

// ------------------------------------------
// Управление ценами и скидками (как в боте)
// ------------------------------------------

function handlePricingScopeChange() {
  const scope = document.getElementById('adminPricingScope').value;
  adminState.pricingScope = scope;

  const catWrap = document.getElementById('adminPricingCatWrap');
  const prodWrap = document.getElementById('adminPricingProdWrap');

  if (scope === 'all') {
    if (catWrap) catWrap.style.display = 'none';
    if (prodWrap) prodWrap.style.display = 'none';
  } else if (scope === 'cat') {
    if (catWrap) catWrap.style.display = 'block';
    if (prodWrap) prodWrap.style.display = 'none';
    populateAdminCategories();
  } else if (scope === 'prod') {
    if (catWrap) catWrap.style.display = 'none';
    if (prodWrap) prodWrap.style.display = 'block';
    populateAdminPricingProductsSelect();
  }

  loadPricingSummary();
}

function populateAdminPricingProductsSelect() {
  const prodSelect = document.getElementById('adminPricingProdSelect');
  if (!prodSelect) return;

  const prods = adminState.products || state.products || [];
  let html = '<option value="">Выберите товар...</option>';
  prods.forEach(p => {
    const priceStr = formatPrice(p.price_cents);
    const discStr = (p.discount_pct && p.discount_pct > 0) ? ` 🔥 -${p.discount_pct}%` : '';
    html += `<option value="${p.id}">${escapeHtml(p.name)} (${priceStr})${discStr}</option>`;
  });
  prodSelect.innerHTML = html;
}

function selectPricingOp(op) {
  adminState.pricingOp = op;

  const btnDiscount = document.getElementById('btnOpDiscount');
  const btnMarkup = document.getElementById('btnOpMarkup');
  const btnApply = document.getElementById('btnApplyPricing');
  const label = document.getElementById('pricingPercentLabel');
  const presetsRow = document.getElementById('pricingPresetsRow');

  if (op === 'discount') {
    if (btnDiscount) btnDiscount.classList.add('active');
    if (btnMarkup) btnMarkup.classList.remove('active');
    if (btnApply) btnApply.innerText = '✅ Применить скидку';
    if (label) label.innerText = '3. Выберите или введите процент скидки (1-99%):';
    if (presetsRow) {
      presetsRow.innerHTML = `
        <button type="button" class="preset-pct-btn" onclick="setPricingPercent(10)">-10%</button>
        <button type="button" class="preset-pct-btn active" onclick="setPricingPercent(20)">-20%</button>
        <button type="button" class="preset-pct-btn" onclick="setPricingPercent(30)">-30%</button>
        <button type="button" class="preset-pct-btn" onclick="setPricingPercent(50)">-50%</button>
      `;
    }
  } else {
    if (btnMarkup) btnMarkup.classList.add('active');
    if (btnDiscount) btnDiscount.classList.remove('active');
    if (btnApply) btnApply.innerText = '✅ Применить повышение цен';
    if (label) label.innerText = '3. Выберите или введите процент наценки (%):';
    if (presetsRow) {
      presetsRow.innerHTML = `
        <button type="button" class="preset-pct-btn" onclick="setPricingPercent(10)">+10%</button>
        <button type="button" class="preset-pct-btn active" onclick="setPricingPercent(25)">+25%</button>
        <button type="button" class="preset-pct-btn" onclick="setPricingPercent(50)">+50%</button>
        <button type="button" class="preset-pct-btn" onclick="setPricingPercent(100)">+100%</button>
      `;
    }
  }
  setPricingPercent(op === 'discount' ? 20 : 25);
  loadPricingSummary();
}

function setPricingPercent(pct) {
  adminState.pricingPercent = pct;
  const input = document.getElementById('adminPricingPercentInput');
  if (input) input.value = pct;

  document.querySelectorAll('#pricingPresetsRow .preset-pct-btn').forEach(btn => {
    const rawVal = parseInt(btn.innerText.replace(/[^0-9]/g, ''));
    if (rawVal === pct) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  loadPricingSummary();
}

async function loadPricingSummary() {
  const summaryBox = document.getElementById('adminPricingSummaryText');
  if (!summaryBox) return;

  const scope = document.getElementById('adminPricingScope').value;
  let targetId = null;
  if (scope === 'cat') {
    const catSelect = document.getElementById('adminPricingCatSelect');
    targetId = catSelect ? catSelect.value : null;
  } else if (scope === 'prod') {
    const prodSelect = document.getElementById('adminPricingProdSelect');
    targetId = prodSelect ? prodSelect.value : null;
  }

  let queryUrl = '/api/admin/pricing/summary';
  if (scope === 'prod' && targetId) queryUrl += `?product_id=${targetId}`;
  if (scope === 'cat' && targetId) queryUrl += `?category_id=${targetId}`;

  try {
    const res = await apiFetch(queryUrl);
    if (!res.ok) return;
    const data = await res.json();
    const stats = data.summary;

    const pct = parseFloat(document.getElementById('adminPricingPercentInput').value) || adminState.pricingPercent;
    const op = adminState.pricingOp;

    let sampleLines = '';
    if (stats.sample_products && stats.sample_products.length > 0) {
      sampleLines = stats.sample_products.map(p => {
        const curCents = p.price;
        const oldCents = p.old_price;
        const baseCents = (op === 'discount' && oldCents && oldCents > curCents) ? oldCents : curCents;
        let newCents;
        if (op === 'discount') {
          newCents = Math.max(1, Math.round(baseCents * (1 - pct / 100)));
        } else {
          newCents = Math.max(1, Math.round(curCents * (1 + pct / 100)));
        }
        return `<div>• <b>${escapeHtml(p.name)}</b>: ${formatPrice(curCents)} ➔ <b style="color:#10b981;">${formatPrice(newCents)}</b></div>`;
      }).join('');
    }

    summaryBox.innerHTML = `
      <div>📦 <b>Товаров в выборке:</b> ${stats.total_count} шт. (со скидкой: ${stats.discounted_count} шт.)</div>
      <div style="margin-top:6px;font-size:12px;color:var(--text-muted);">Пример пересчета:</div>
      <div style="margin-top:4px;">${sampleLines || '• Нет товаров'}</div>
    `;
  } catch (e) {
    console.warn(e);
  }
}

async function executePricingApply() {
  const scope = document.getElementById('adminPricingScope').value;
  let targetId = null;
  if (scope === 'cat') {
    const catSelect = document.getElementById('adminPricingCatSelect');
    targetId = catSelect ? catSelect.value : null;
    if (!targetId) {
      showToast('Выберите раздел для применения скидки', 'warning');
      return;
    }
  } else if (scope === 'prod') {
    const prodSelect = document.getElementById('adminPricingProdSelect');
    targetId = prodSelect ? prodSelect.value : null;
    if (!targetId) {
      showToast('Выберите товар для изменения цены', 'warning');
      return;
    }
  }

  const pctInput = document.getElementById('adminPricingPercentInput');
  const percent = parseFloat(pctInput ? pctInput.value : adminState.pricingPercent);
  if (!percent || percent <= 0 || (adminState.pricingOp === 'discount' && percent >= 100)) {
    showToast('Введите корректный процент (от 1 до 99)', 'warning');
    return;
  }

  const opWord = adminState.pricingOp === 'discount' ? `скидку -${percent}%` : `наценку +${percent}%`;
  if (!confirm(`Применить ${opWord} к выбранным товарам?`)) return;

  const btnApply = document.getElementById('btnApplyPricing');
  if (btnApply) btnApply.disabled = true;

  try {
    const res = await apiFetch('/api/admin/pricing/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: scope,
        target_id: targetId,
        op: adminState.pricingOp,
        percent: percent
      })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка применения цен', 'error');
      return;
    }

    showToast(data.message || 'Цены успешно обновлены! 🔥', 'success');

    await loadCatalog();
    await loadAdminProducts();
    loadPricingSummary();

  } catch (err) {
    console.error('Ошибка применения цен:', err);
    showToast('Сетевая ошибка', 'error');
  } finally {
    if (btnApply) btnApply.disabled = false;
  }
}

async function executePricingReset() {
  const scope = document.getElementById('adminPricingScope').value;
  let targetId = null;
  if (scope === 'cat') {
    const catSelect = document.getElementById('adminPricingCatSelect');
    targetId = catSelect ? catSelect.value : null;
  } else if (scope === 'prod') {
    const prodSelect = document.getElementById('adminPricingProdSelect');
    targetId = prodSelect ? prodSelect.value : null;
  }

  if (!confirm('Сбросить скидки и вернуть исходные базовые цены?')) return;

  try {
    const res = await apiFetch('/api/admin/pricing/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: scope, target_id: targetId })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка сброса скидок', 'error');
      return;
    }

    showToast(data.message || 'Скидки сброшены! Исходные цены восстановлены.', 'success');

    await loadCatalog();
    await loadAdminProducts();
    loadPricingSummary();

  } catch (err) {
    console.error('Ошибка сброса скидок:', err);
    showToast('Сетевая ошибка', 'error');
  }
}

// ------------------------------------------
// Список всех товаров в админке
// ------------------------------------------

async function loadAdminProducts() {
  const container = document.getElementById('adminProdsListContainer');
  if (!container) return;

  try {
    const res = await apiFetch('/api/admin/products');
    if (!res.ok) {
      container.innerHTML = '<p class="empty-hint">Ошибка загрузки товаров</p>';
      return;
    }

    const data = await res.json();
    adminState.products = data.products || [];
    renderAdminProductsList(adminState.products);

  } catch (err) {
    console.error('Ошибка loadAdminProducts:', err);
    container.innerHTML = '<p class="empty-hint">Не удалось загрузить товары</p>';
  }
}

function renderAdminProductsList(products) {
  const container = document.getElementById('adminProdsListContainer');
  const countBadge = document.getElementById('adminProdsTotalCount');
  if (!container) return;

  if (countBadge) countBadge.innerText = `${products.length} товаров`;

  if (products.length === 0) {
    container.innerHTML = '<p class="empty-hint">Товары не найдены</p>';
    return;
  }

  container.innerHTML = products.map(p => {
    let photo = (p.photos && p.photos[0]) ? p.photos[0] : 'web/img/product_placeholder.png';
    if (photo.startsWith('/')) photo = photo.slice(1);

    const isDiscounted = p.discount_pct && p.discount_pct > 0;
    const discBadge = isDiscounted ? `<span class="badge badge-discount" style="font-size:10px;padding:2px 6px;">-${p.discount_pct}%</span>` : '';
    const oldPriceHtml = isDiscounted ? `<span class="admin-prod-old-price">${formatPrice(p.old_price_cents)}</span>` : '';
    const stockStr = (p.kind === 'oneoff') ? `Остаток: ${p.stock_count} шт.` : 'Многоразовый';

    return `
      <div class="admin-prod-item">
        <img class="admin-prod-thumb" src="${photo}" alt="Фото">
        <div class="admin-prod-info">
          <div class="admin-prod-name">${escapeHtml(p.name)} ${discBadge}</div>
          <div class="admin-prod-meta">
            <span>📁 ${escapeHtml(p.category_name)}</span>
            <span>•</span>
            <span>📦 ${stockStr}</span>
          </div>
        </div>
        <div class="admin-prod-prices">
          ${oldPriceHtml}
          <span class="admin-prod-cur-price">${formatPrice(p.price_cents)}</span>
        </div>
        <div class="admin-prod-actions">
          <button class="btn-admin-act" onclick="quickProductDiscount(${p.id}, '${escapeAttr(p.name)}')">📉 Скидка</button>
          ${isDiscounted ? `<button class="btn-admin-act" onclick="quickProductResetDiscount(${p.id}, '${escapeAttr(p.name)}')">🔄 Сброс</button>` : ''}
          <button class="btn-admin-act btn-act-danger" onclick="quickProductDelete(${p.id}, '${escapeAttr(p.name)}')">🗑️</button>
        </div>
      </div>
    `;
  }).join('');
}

function filterAdminProductsList() {
  const query = (document.getElementById('adminProdsSearchInput').value || '').toLowerCase().trim();
  if (!query) {
    renderAdminProductsList(adminState.products);
    return;
  }
  const filtered = adminState.products.filter(p => {
    return p.name.toLowerCase().includes(query) || (p.category_name && p.category_name.toLowerCase().includes(query));
  });
  renderAdminProductsList(filtered);
}

// Быстрая скидка на конкретный товар
async function quickProductDiscount(prodId, prodName) {
  const rawPct = prompt(`Введите процент скидки для товара «${prodName}» (от 1 до 99%):`, '20');
  if (!rawPct) return;

  const pct = parseFloat(rawPct.replace('%', '').trim());
  if (!pct || pct <= 0 || pct >= 100) {
    showToast('Укажите процент от 1 до 99', 'warning');
    return;
  }

  try {
    const res = await apiFetch('/api/admin/pricing/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: 'prod',
        target_id: prodId,
        op: 'discount',
        percent: pct
      })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка применения скидки', 'error');
      return;
    }

    showToast(`Скидка -${pct}% успешно применена к «${prodName}»! 🔥`, 'success');
    await loadCatalog();
    await loadAdminProducts();

  } catch (err) {
    console.error(err);
    showToast('Сетевая ошибка', 'error');
  }
}

// Быстрый сброс скидки на конкретном товаре
async function quickProductResetDiscount(prodId, prodName) {
  if (!confirm(`Вернуть исходную цену для товара «${prodName}»?`)) return;

  try {
    const res = await apiFetch('/api/admin/pricing/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: 'prod',
        target_id: prodId
      })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка сброса скидки', 'error');
      return;
    }

    showToast(`Исходная цена для «${prodName}» восстановлена!`, 'success');
    await loadCatalog();
    await loadAdminProducts();

  } catch (err) {
    console.error(err);
    showToast('Сетевая ошибка', 'error');
  }
}

// Быстрое удаление товара
async function quickProductDelete(prodId, prodName) {
  if (!confirm(`Вы действительно хотите удалить товар «${prodName}» из каталога?`)) return;

  try {
    const res = await apiFetch('/api/admin/product/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: prodId })
    });

    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || 'Ошибка при удалении товара', 'error');
      return;
    }

    showToast(`Товар «${prodName}» удален из каталога`, 'info');
    await loadCatalog();
    await loadAdminProducts();

  } catch (err) {
    console.error(err);
    showToast('Сетевая ошибка', 'error');
  }
}
