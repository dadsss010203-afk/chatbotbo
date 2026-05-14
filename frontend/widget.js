/* ═══════════════════════════════════════════════════════════════════════
   WIDGET JS - Correos de Bolivia Chat Bubble
   ═══════════════════════════════════════════════════════════════════════ */

// ─── CONFIGURACIÓN ────────────────────────────────────────────────────
let API_URL = '/api';
let lang    = 'es';
let embedMode = false;
let widgetPos = 'right';

// ─── ESTADO ────────────────────────────────────────────────────────────
let chatOpen    = false;
let busy        = false;
let translating = false;
let ctrl        = null;
let tarifaMode  = false;
let trackingMode = false;
let qrLibPromise = null;
let welcomeLoaded = false;

// ─── TEXTOS POR IDIOMA ────────────────────────────────────────────────
const TX = {
  es: {
    ph: 'Escriba su consulta aquí…',
    lbl: 'Analizando consulta…',
    bye: 'Conversación finalizada',
    translating: 'Traduciendo conversación…',
    welcome: '¡Hola! Soy ChatbotBO, el asistente oficial de Correos de Bolivia.\n\nPuedo ayudarte con envíos, sucursales, ubicaciones y más.\n\n• Presiona TARIFAS para consultar precios de envío.\n• Presiona RASTREO para rastrear un paquete.\n\n¿En qué puedo ayudarte hoy?',
    chips: ['📦 Rastrear paquete', '💰 Ver tarifas', '📍 Sucursales', '🕐 Horarios', '✉️ ¿Qué es EMS?'],
    tarifa: 'Tarifas',
    tarifaCancel: 'Cancelar tarifa',
    tracking: 'Rastreo',
    trackingCancel: 'Cancelar rastreo',
    nearby: 'Sucursales',
    enterHint: 'Enter para enviar',
    confirmText: '¿Borrar toda la conversación?',
    cancelBtn: 'Cancelar',
    confirmBtn: 'Confirmar',
    tarifaMode: 'Modo tarifas activado. ¿Qué servicio quieres usar?',
    trackingMode: 'Modo rastreo activado. Envíame tu código de rastreo.',
    tarifaCancelled: 'Modo tarifas cancelado. Volviste al chat general.',
    trackingCancelled: 'Modo rastreo cancelado. Volviste al chat general.',
    nacional: 'Nacional',
    internacional: 'Internacional',
    ems: 'Express Mail Service (EMS)',
    prioritario: 'Prioritario',
    encomiendas: 'Encomiendas Postales'
  },
  en: {
    ph: 'Type your question here…',
    lbl: 'Processing request…',
    bye: 'Conversation ended',
    translating: 'Translating conversation…',
    welcome: 'Hello! I am chatbotBO, the virtual assistant of the Bolivian Postal Agency. I can help you with shipments, package tracking, branches and more. How can I help you?',
    chips: ['📦 Track package', '💰 View rates', '📍 Branches', '🕐 Office hours', '✉️ What is EMS?'],
    tarifa: 'Rates',
    tarifaCancel: 'Cancel rates',
    tracking: 'Tracking',
    trackingCancel: 'Cancel tracking',
    nearby: 'Branches',
    enterHint: 'Enter to send',
    confirmText: 'Delete entire conversation?',
    cancelBtn: 'Cancel',
    confirmBtn: 'Confirm',
    tarifaMode: 'Rates mode activated. What service do you want to use?',
    trackingMode: 'Tracking mode activated. Send me your tracking code.',
    tarifaCancelled: 'Rates mode cancelled. Back to general chat.',
    trackingCancelled: 'Tracking mode cancelled. Back to general chat.',
    nacional: 'National',
    internacional: 'International',
    ems: 'Express Mail Service (EMS)',
    prioritario: 'Priority',
    encomiendas: 'Postal Parcels'
  },
};

// ─── AUTO-INICIALIZACIÓN EN MODO WIDGET ──────────────────────────────
console.log('Widget.js cargando...');
(function(){
  let s = document.currentScript;
  if (!s) {
    const all = document.getElementsByTagName('script');
    for (let i = all.length - 1; i >= 0; --i) {
      if ((all[i].src || '').includes('widget.js')) { s = all[i]; break; }
    }
  }

  if (s) {
    if (s.dataset.api)  API_URL = s.dataset.api.replace(/\/+$/, '');
    if (s.dataset.lang) lang    = s.dataset.lang;
  }

  const params = new URLSearchParams(window.location.search || '');
  if (params.get('api')) API_URL = params.get('api').replace(/\/+$/, '');
  if (params.get('lang')) lang = params.get('lang');
  if (params.get('embed') === '1') embedMode = true;
  if (params.get('pos') === 'left') widgetPos = 'left';
  if (s && s.dataset.pos === 'left') widgetPos = 'left';
  if (embedMode) document.body.classList.add('widget-shell');

  const baseUrl = s
    ? s.src.replace(/\/widget\.js.*$/, '')
    : API_URL.replace(/\/api$/, '');

  console.log('widget.js | baseUrl:', baseUrl, '| API_URL:', API_URL);

  // Cargar Leaflet YA (los <script> en HTML inyectado no ejecutan)
  if (!window.L) {
    const lCss = document.createElement('link');
    lCss.rel   = 'stylesheet';
    lCss.href  = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
    document.head.appendChild(lCss);
    const lJs = document.createElement('script');
    lJs.src   = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
    document.head.appendChild(lJs);
  }
  ensureQRCodeLib().catch(err => console.warn('No se pudo precargar QRCode:', err));

  // Si el widget ya está en el DOM (chatbot.html nativo) inyectar contenido de widget.html
  const existingWindow = document.getElementById('chat-window');
  if (existingWindow) {
    console.log('chat-window existe, inicializando widget ya presente en el DOM...');
    setTimeout(() => initWidget(s), 100);
    return;
  }

  // Inyectar CSS
  const link  = document.createElement('link');
  link.rel    = 'stylesheet';
  link.href   = baseUrl + '/widget.css';
  document.head.appendChild(link);

  // Inyectar HTML y luego inicializar
  fetch(baseUrl + '/widget.html')
    .then(res => {
      if (!res.ok) throw new Error('widget.html HTTP ' + res.status);
      return res.text();
    })
    .then(html => {
      // Reemplazar rutas relativas con URL absoluta del servidor
      html = html.replace(/src="\/logogif\.gif"/g, `src="${baseUrl}/logogif.gif"`);
      html = html.replace(/src="\/logo_chatbot\.png"/g, `src="${baseUrl}/logo_chatbot.png"`);
      html = html.replace(/src="\/logocorreos\.jpg"/g, `src="${baseUrl}/logocorreos.jpg"`);
      document.body.insertAdjacentHTML('beforeend', html);
      // Retrasar la inicialización para asegurar que el script se cargue completamente
      setTimeout(() => initWidget(s), 100);
    })
    .catch(err => console.error('No se pudo cargar widget.html:', err));
  console.log('Widget auto-inicialización completada');
})();


// ─── INICIALIZAR ──────────────────────────────────────────────────────
function initWidget(s) {
  console.log('initWidget llamado');
  if (window._widgetInitialized) {
    console.log('initWidget ya fue llamado, ignorando.');
    return;
  }
  window._widgetInitialized = true;
  if (widgetPos === 'left') {
    const bubble = document.getElementById('chat-bubble');
    const win    = document.getElementById('chat-window');
    if (bubble) { bubble.style.left = '28px';  bubble.style.right = 'auto'; }
    if (win)    { win.style.left    = '22px';  win.style.right    = 'auto'; }
  }

  // La burbuja ya usa onclick en widget.html; evitar doble toggle.
  const bubble = document.getElementById('chat-bubble');
  console.log('Chat bubble element:', bubble);
  if (!bubble) {
    console.error('Chat bubble no encontrado');
  }

  // Adjuntar form listener cuando el DOM ya existe
  const form = document.getElementById('form');
  if (form) {
    form.addEventListener('submit', e => {
      e.preventDefault();
      const inp = document.getElementById('input');
      const t   = inp.value.trim();
      if (!t) return;
      inp.value = '';
      sendMsg(t);
    });
  }

  // Conectar botones del header (sin onclick inline para evitar errores de scope)
  const btnClose    = document.getElementById('btn-close');
  const btnMinimize = document.getElementById('btn-minimize');
  const btnBubble   = document.getElementById('chat-bubble');
  if (btnClose)    btnClose.addEventListener('click', () => toggleChat());
  if (btnMinimize) btnMinimize.addEventListener('click', () => minimize());
  if (btnBubble)   btnBubble.addEventListener('click', () => toggleChat());

  // Cerrar mapa al hacer clic fuera
  const mapaModal = document.getElementById('mapa-modal');
  if (mapaModal) {
    mapaModal.addEventListener('click', e => {
      if (e.target === e.currentTarget) closeMap();
    });
  }

  if (lang !== 'es') setLang(lang);
  setTarifaModeUI();
  setTrackingModeUI();
  notifyEmbedState(false);

  console.log('Chat Bubble Widget - Correos de Bolivia cargado');
}


// ─── ESTADO (otras variables globales ya declaradas arriba) ───────────
let mapInst     = null;
let sid         = localStorage.getItem('chat_sid') || '';
let currentRequestId = '';

function newRequestId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function ensureQRCodeLib() {
  if (window.QRCode) return Promise.resolve();
  if (qrLibPromise) return qrLibPromise;
  qrLibPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-widget-qr-lib="1"]');
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error('No se pudo cargar QRCode')), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js';
    script.async = true;
    script.dataset.widgetQrLib = '1';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('No se pudo cargar QRCode'));
    document.head.appendChild(script);
  });
  return qrLibPromise;
}

// ─── UI HELPERS ───────────────────────────────────────────────────────
function setStop(v) {
  document.getElementById('stop').classList.toggle('vis', v);
  document.getElementById('send').style.display = v ? 'none' : 'flex';
}

function setTarifaModeUI() {
  const btn = document.getElementById('tarifa-toggle');
  if (!btn) return;
  const t = TX[lang] || TX.es;
  btn.classList.toggle('active', tarifaMode);
  btn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
}

function setTrackingModeUI() {
  const btn = document.getElementById('tracking-toggle');
  if (!btn) return;
  const t = TX[lang] || TX.es;
  btn.classList.toggle('active', trackingMode);
  btn.textContent = trackingMode ? t.trackingCancel : t.tracking;
}

async function cancelTarifaMode(notify = true) {
  tarifaMode = false;
  setTarifaModeUI();
  try {
    const res = await fetch(`${API_URL}/tarifa/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid }),
    });
    const data = await res.json();
    if (data && data.sid) {
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
  } catch (e) {
    console.warn('No se pudo cancelar flujo tarifa:', e);
  }
  if (notify) {
    const t = TX[lang] || TX.es;
    addMsg(t.tarifaCancelled, 'b', false, null);
  }
}

async function cancelTrackingMode(notify = true) {
  trackingMode = false;
  setTrackingModeUI();
  try {
    const res = await fetch(`${API_URL}/tracking/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid }),
    });
    const data = await res.json();
    if (data && data.sid) {
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
  } catch (e) {
    console.warn('No se pudo cancelar flujo tracking:', e);
  }
  if (notify) {
    const t = TX[lang] || TX.es;
    addMsg(t.trackingCancelled, 'b', false, null);
  }
}

async function toggleTarifaMode() {
  if (tarifaMode) {
    await cancelTarifaMode(true);
    return;
  }
  if (trackingMode) {
    await cancelTrackingMode(false);
  }
  tarifaMode = true;
  setTarifaModeUI();
  const t = TX[lang] || TX.es;
  try {
    const res = await fetch(`${API_URL}/tarifa/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid, lang }),
    });
    const data = await res.json();
    if (data && data.sid) {
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
    addMsg(data.response || t.tarifaMode, 'b', false, null, false, data.conversation_log_id || null);
    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
  } catch (e) {
    addMsg(t.tarifaMode, 'b', false, null);
  }
}

async function toggleTrackingMode() {
  if (trackingMode) {
    await cancelTrackingMode(true);
    return;
  }
  if (tarifaMode) {
    await cancelTarifaMode(false);
  }
  trackingMode = true;
  setTrackingModeUI();
  const t = TX[lang] || TX.es;
  try {
    const res = await fetch(`${API_URL}/tracking/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid, lang }),
    });
    const data = await res.json();
    if (data && data.sid) {
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
    addMsg(data.response || t.trackingMode, 'b', false, null, false, data.conversation_log_id || null);
    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
  } catch (e) {
    addMsg(t.trackingMode, 'b', false, null);
  }
}

function now() {
  return new Date().toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit' });
}

function notifyEmbedState(open) {
  if (!embedMode || window.parent === window) return;
  window.parent.postMessage({ type: 'chatbotbo:state', open }, '*');
}

window.addEventListener('message', (event) => {
  const data = event.data || {};
  if (data.type !== 'chatbotbo:command') return;
  if (data.action === 'open' && !chatOpen) toggleChat();
  if (data.action === 'close' && chatOpen) minimize();
});

// ─── TOGGLE CHAT ──────────────────────────────────────────────────────
function toggleChat() {
  console.log('toggleChat llamado, chatOpen actual:', chatOpen);
  chatOpen = !chatOpen;
  console.log('Nuevo chatOpen:', chatOpen);
  const chatWindow = document.getElementById('chat-window');
  const bubble = document.getElementById('chat-bubble');
  const isMobile = window.innerWidth <= 480;
  console.log('chat-window element:', chatWindow);
  if (chatWindow) {
    chatWindow.classList.toggle('open', chatOpen);
    chatWindow.style.opacity = chatOpen ? '1' : '0';
  } else {
    console.error('chat-window no encontrado');
  }
  if (chatOpen) {
    document.getElementById('badge').style.display = 'none';
    if (isMobile && bubble) bubble.style.display = 'none';
    if (!welcomeLoaded) {
      welcomeLoaded = true;
      loadWelcome();
    }
    setTimeout(() => document.getElementById('input').focus(), 420);
  } else {
    if (bubble) bubble.style.display = 'flex';
  }
  notifyEmbedState(chatOpen);
}

function minimize() {
  document.getElementById('chat-window').classList.remove('open');
  const bubble = document.getElementById('chat-bubble');
  if (bubble) bubble.style.display = 'flex';
  chatOpen = false;
  notifyEmbedState(false);
}

// ─── IDIOMA ───────────────────────────────────────────────────────────
async function setLang(l) {
  if (translating || busy || l === lang) return;
  lang = l;

  document.querySelectorAll('.lpill').forEach(b => b.classList.toggle('on', b.dataset.lang === l));

  const t = TX[l] || TX.es;
  document.getElementById('input').placeholder = t.ph;

  // Actualizar botones y textos
  const tarifaBtn = document.getElementById('tarifa-toggle');
  const trackingBtn = document.getElementById('tracking-toggle');
  const nearbyBtn = document.getElementById('nearby-toggle');
  const fHint = document.querySelector('.f-hint');
  const confirmText = document.querySelector('#confirm-bar p');
  const cancelBtn = document.querySelector('.cno');
  const confirmBtn = document.querySelector('.csi');

  if (tarifaBtn) tarifaBtn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
  if (trackingBtn) trackingBtn.textContent = trackingMode ? t.trackingCancel : t.tracking;
  if (nearbyBtn) nearbyBtn.textContent = t.nearby;
  if (fHint) fHint.textContent = t.enterHint;
  if (confirmText) confirmText.innerHTML = t.confirmText;
  if (cancelBtn) cancelBtn.textContent = t.cancelBtn;
  if (confirmBtn) confirmBtn.textContent = t.confirmBtn;

  const cc = document.getElementById('chips-container');
  if (cc) {
    cc.innerHTML = t.chips.map(c => `<button class="chip" onclick="suggest(this)">${c}</button>`).join('');
  }

  // Mostrar banner animado y traducir conversación
  const banner = document.getElementById('translate-banner');
  const bubbles = Array.from(
    document.querySelectorAll('.msg.b .bub:not(.farewell):not(.no-translate)')
  ).filter(b => !b.closest('.qr-message'));

  if (bubbles.length > 0) {
    // Mostrar banner con animación de puntos
    let dots = 0;
    banner.innerHTML = `<span id="banner-text">${t.translating}</span>`;
    banner.classList.add('vis');
    const dotsInterval = setInterval(() => {
      dots = (dots + 1) % 4;
      const el = document.getElementById('banner-text');
      if (el) el.textContent = t.translating.replace('…', '.'.repeat(dots) || '.');
    }, 400);

    await translateConversation();

    clearInterval(dotsInterval);
    banner.classList.remove('vis');
  }
}

// ─── TRADUCIR CONVERSACIÓN ────────────────────────────────────────────
async function translateConversation() {
  const bubbles = Array.from(
    document.querySelectorAll('.msg.b .bub:not(.farewell):not(.no-translate)')
  ).filter(b => !b.closest('.qr-message'));
  if (bubbles.length === 0) return;

  translating = true;
  const t      = TX[lang] || TX.es;
  const inp    = document.getElementById('input');
  const banner = document.getElementById('translate-banner');
  const pills  = document.querySelectorAll('.lpill');

  inp.disabled = true;
  pills.forEach(p => p.disabled = true);
  banner.textContent = t.translating;
  banner.classList.add('vis');
  bubbles.forEach(b => b.classList.add('translating-anim'));

  const originals = bubbles.map(b => b.dataset.original || b.textContent || '');
  originals.forEach((orig, i) => { if (!bubbles[i].dataset.original) bubbles[i].dataset.original = orig; });

  try {
    const res  = await fetch(`${API_URL}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: originals, lang })
    });
    const data = await res.json();
    if (Array.isArray(data.translations)) {
      data.translations.forEach((tr, i) => {
        if (bubbles[i]) bubbles[i].textContent = (typeof tr === 'string' && tr.trim()) ? tr : originals[i];
      });
    }
  } catch (e) {
    console.warn('Error traduciendo:', e);
  }

  setTimeout(() => {
    bubbles.forEach(b => b.classList.remove('translating-anim'));
    banner.classList.remove('vis');
    inp.disabled = false;
    pills.forEach(p => p.disabled = false);
    translating = false;
    if (!busy) inp.focus();
  }, 300);
}

// ─── AVATARES ─────────────────────────────────────────────────────────
function mkAv(t) {
  const a = document.createElement('div');
  a.className = 'av';
  if (t === 'u') {
    a.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 12c2.7 0 4-1.3 4-4s-1.3-4-4-4-4 1.3-4 4 1.3 4 4 4zm0 2c-2.7 0-8 1.35-8 4v2h16v-2c0-2.65-5.3-4-8-4z"/></svg>';
  } else {
    a.style.cssText = 'background:linear-gradient(145deg,#FFC145,#C8860E);border-radius:50%;display:flex;align-items:center;justify-content:center;width:44px;height:44px;flex-shrink:0;box-shadow:0 0 0 3px rgba(200,134,14,0.4),0 4px 12px rgba(122,79,0,0.5);';
    // IDs únicos para cada avatar
    const uid = Math.random().toString(36).slice(2,7);
    a.innerHTML = `<svg viewBox="0 0 44 44" width="44" height="44" xmlns="http://www.w3.org/2000/svg">
      <circle cx="22" cy="22" r="18" fill="white"/>
      <g id="el_${uid}">
        <ellipse cx="14" cy="20" rx="6.5" ry="5" fill="#1A0E00"/>
        <ellipse cx="16" cy="17.5" rx="1.8" ry="1.3" fill="white"/>
      </g>
      <g id="er_${uid}">
        <ellipse cx="30" cy="20" rx="6.5" ry="5" fill="#1A0E00"/>
        <ellipse cx="32" cy="17.5" rx="1.8" ry="1.3" fill="white"/>
      </g>
    </svg>`;
    // Animar pupilas con JS
    let dir = 1, pos = 0;
    setInterval(() => {
      pos += dir * 0.12;
      if (pos > 3) dir = -1;
      if (pos < -3) dir = 1;
      const el = a.querySelector(`#el_${uid}`);
      const er = a.querySelector(`#er_${uid}`);
      if (el) el.setAttribute('transform', `translate(${pos},0)`);
      if (er) er.setAttribute('transform', `translate(${pos},0)`);
    }, 30);
  }
  return a;
}

// ─── TARJETA VISUAL DE TARIFA ─────────────────────────────────────────
function addTarifaCard(card) {
  if (!card || !card.precio) return;
  document.getElementById('welcomeCard')?.remove();
  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = 'msg b';

  const scopeLabel = {
    'nacional': 'EMS Nacional',
    'internacional': 'EMS Internacional',
    'encomienda_nacional': 'Encomienda Nacional',
    'encomienda_internacional': 'Encomienda Internacional',
    'super_express_nacional': 'Super Express Nacional',
    'ems_contratos_nacional': 'EMS Contratos Nacional',
  }[card.scope] || (card.scope || 'Servicio Postal');

  const cardEl = document.createElement('div');
  cardEl.className = 'scard no-translate';
  cardEl.innerHTML = `
    <div class="sc-head" style="background:linear-gradient(135deg,#163A80,#2255B8)">
      <div class="sc-ico">
        <svg viewBox="0 0 24 24"><path d="M12 2v20M6 7c0-1.7 2.7-3 6-3s6 1.3 6 3-2.7 3-6 3-6 1.3-6 3 2.7 3 6 3 6 1.3 6 3"/></svg>
      </div>
      <div class="sc-htxt">
        <strong>Tarifa calculada</strong>
        <span>${scopeLabel}</span>
      </div>
    </div>
    <div class="sc-body">
      <div class="sc-row">
        <svg viewBox="0 0 24 24"><path d="M12 2v20M6 7c0-1.7 2.7-3 6-3s6 1.3 6 3-2.7 3-6 3-6 1.3-6 3 2.7 3 6 3 6 1.3 6 3"/></svg>
        <span><strong style="font-size:1.1rem;color:var(--y700)">${card.precio} Bs</strong></span>
      </div>
      ${card.servicio ? `<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M20 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg><span>Servicio: ${card.servicio}</span></div>` : ''}
      ${card.peso_g ? `<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M12 2a5 5 0 0 1 5 5H7a5 5 0 0 1 5-5zM3 9h18l-2 13H5L3 9z"/></svg><span>Peso: ${card.peso_g} g</span></div>` : ''}
      ${card.rango_min && card.rango_max ? `<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M3 3h18v18H3z" fill="none"/><path d="M8 12h8M12 8v8"/></svg><span>Rango: ${card.rango_min}–${card.rango_max} g</span></div>` : ''}
    </div>
    <a class="sc-cta" href="https://correos.gob.bo" target="_blank" rel="noopener noreferrer">
      <svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      Ver más en correos.gob.bo
    </a>
  `;

  wrap.appendChild(mkAv('b'));
  wrap.appendChild(cardEl);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

async function rateConversation(logId, rating, likeBtn, dislikeBtn) {
  if (!logId) return;
  try {
    await fetch(`${API_URL}/conversations/${encodeURIComponent(String(logId))}/rating`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    });
    if (likeBtn) likeBtn.classList.toggle('active-like', rating === 'like');
    if (dislikeBtn) dislikeBtn.classList.toggle('active-dislike', rating === 'dislike');
  } catch (e) {
    console.warn('No se pudo guardar rating:', e);
  }
}

function buildWelcomeCard() {
  const t = TX[lang] || TX.es;
  const wc = document.createElement('div');
  wc.className = 'welcome';
  wc.id = 'welcomeCard';
  wc.innerHTML = `
    <div class="wc-icon"><svg viewBox="0 0 24 24"><path d="M20 4H4C2.9 4 2 4.9 2 6v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg></div>
    <div class="wc-title"> </div>
    <div class="wc-sub">Consulte sobre envíos, rastreo de paquetes, sucursales y servicios postales de Correos de Bolivia.</div>
    <div class="wc-sep"><div class="wc-sep-l"></div><div class="wc-sep-d"></div><div class="wc-sep-l"></div></div>
    <div class="chips" id="chips-container">
      ${t.chips.map(c => `<button class="chip" onclick="suggest(this)">${c}</button>`).join('')}
    </div>`;
  return wc;
}

async function loadWelcome() {
  await new Promise(resolve => setTimeout(resolve, 300));
  showTyping();
  await new Promise(resolve => setTimeout(resolve, 900));
  removeTyping();
  try {
    const data = await (await fetch(`${API_URL}/welcome?lang=${lang}`)).json();
    addMsg(data.response, 'b', false, null, false);
  } catch (e) {
    addMsg('Bienvenido al asistente oficial de Correos de Bolivia. ¿En qué puedo ayudarte?', 'b', false, null, false);
  }
}

// ─── MENSAJE DE BIENVENIDA (burbuja fija, no desaparece) ─────────────
function addWelcomeMsg(text) {
  const chat = document.getElementById('chat');
  if (!chat) return;

  const wrap = document.createElement('div');
  wrap.className = 'msg b';
  wrap.id = 'welcomeMsg'; // ID único para poder actualizarlo al cambiar idioma

  const b = document.createElement('div');
  b.className = 'bub';
  b.textContent = text;
  b.dataset.original = text;

  const tm = document.createElement('span');
  tm.className = 'msg-time';
  tm.textContent = now();

  const body = document.createElement('div');
  body.style.cssText = 'display:flex;flex-direction:column;align-items:flex-start';
  body.appendChild(b);
  body.appendChild(tm);

  wrap.appendChild(mkAv('b'));
  wrap.appendChild(body);

  // Insertar ANTES del welcomeCard (chips) para que quede arriba
  const card = document.getElementById('welcomeCard');
  if (card) {
    chat.insertBefore(wrap, card);
  } else {
    chat.appendChild(wrap);
  }
}

// ─── AÑADIR MENSAJE ───────────────────────────────────────────────────
function addMsg(text, type, bye = false, loc = null, noTranslate = false, conversationLogId = null) {
  // Solo eliminar el card de chips, la burbuja de bienvenida (welcomeMsg) se queda
  document.getElementById('welcomeCard')?.remove();

  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = `msg ${type}`;

  if (loc && loc.lat) {
    const card = document.createElement('div');
    card.className = 'scard';
    card.classList.add('no-translate');
    card.innerHTML = `
      <div class="sc-head">
        <div class="sc-ico"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg></div>
        <div class="sc-htxt"><strong>${loc.nombre || 'Sucursal'}</strong><span>Correos de Bolivia</span></div>
      </div>
      <div class="sc-body">
        <div class="sc-row"><svg viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg><span>${loc.direccion || 'No disponible'}</span></div>
        <div class="sc-row"><svg viewBox="0 0 24 24"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg><span>${loc.telefono || 'No disponible'}</span></div>
        ${loc.email ? `<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg><span>${loc.email}</span></div>` : ''}
        <div class="sc-sep"></div>
        <div class="sc-row"><svg viewBox="0 0 24 24"><path d="M12 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 12 2zm.5 5v6l5.25 3.15-.75 1.23L11 14V7h1.5z"/></svg><span>${loc.horario || 'No disponible'}</span></div>
      </div>
      ${loc.maps_url ? `<a class="sc-cta" href="${loc.maps_url}" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>Ver en Google Maps</a>` : ''}
    `;
    wrap.appendChild(mkAv(type));
    wrap.appendChild(card);
  } else {
    const b = document.createElement('div');
    b.className = 'bub' + (bye ? ' farewell' : '');
    b.textContent = text;
    b.dataset.original = text;

    const tm = document.createElement('span');
    tm.className = 'msg-time';
    tm.textContent = now();

    const body = document.createElement('div');
    body.style.cssText = `display:flex;flex-direction:column;align-items:${type === 'u' ? 'flex-end' : 'flex-start'}`;
    body.appendChild(b);
    body.appendChild(tm);

    if (!bye && !noTranslate && type === 'b') {
      const acts = document.createElement('div');
      acts.className = 'msg-actions';
      if (conversationLogId) {
        const likeBtn = document.createElement('button');
        likeBtn.className = 'btn-rate';
        likeBtn.type = 'button';
        likeBtn.title = 'Me gustó esta respuesta';
        likeBtn.textContent = '👍';
        likeBtn.onclick = () => rateConversation(conversationLogId, 'like', likeBtn, dislikeBtn);

        const dislikeBtn = document.createElement('button');
        dislikeBtn.className = 'btn-rate';
        dislikeBtn.type = 'button';
        dislikeBtn.title = 'No me gustó esta respuesta';
        dislikeBtn.textContent = '👎';
        dislikeBtn.onclick = () => rateConversation(conversationLogId, 'dislike', likeBtn, dislikeBtn);

        acts.appendChild(likeBtn);
        acts.appendChild(dislikeBtn);
      }
      body.appendChild(acts);
    }

    wrap.appendChild(mkAv(type));
    wrap.appendChild(body);
  }

  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  if (!bye && !noTranslate && type === 'b' && !loc) {
    const bubble = wrap.querySelector('.bub');
    if (bubble) autoTranslateBubble(bubble, text);
  }
}

// ─── TRADUCIR MENSAJE INDIVIDUAL ──────────────────────────────────────
async function autoTranslateBubble(bubble, originalText) {
  if (lang === 'es' || !bubble || !originalText) return;
  if (bubble.classList.contains('no-translate') || bubble.closest('.qr-message')) return;
  try {
    const res  = await fetch(`${API_URL}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: [originalText], lang })
    });
    const data = await res.json();
    if (Array.isArray(data.translations)) {
      const tr = data.translations[0];
      if (typeof tr === 'string' && tr.trim()) {
        bubble.textContent = tr;
      }
    }
  } catch (e) {
    console.warn('No se pudo traducir automáticamente la respuesta:', e);
  }
}

async function translateMsg(bubble, btn, originalText) {
  btn.classList.add('loading');
  btn.textContent = ' ';
  try {
    const res  = await fetch(`${API_URL}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: [originalText], lang })
    });
    const data = await res.json();
    if (Array.isArray(data.translations)) {
      const tr = data.translations[0];
      bubble.textContent = (typeof tr === 'string' && tr.trim()) ? tr : originalText;
      btn.textContent = '↩ Original';
      btn.style.color = 'var(--y700)';
      btn.onclick = () => {
        bubble.textContent = originalText;
        btn.textContent    = '🌐 Traducir';
        btn.style.color    = '';
        btn.onclick        = () => translateMsg(bubble, btn, originalText);
      };
    }
  } catch (e) {
    btn.textContent = '🌐 Traducir';
  }
  btn.classList.remove('loading');
}

// ─── TYPING INDICATOR ─────────────────────────────────────────────────
function showTyping() {
  document.getElementById('welcomeCard')?.remove();
  const chat = document.getElementById('chat');
  const t    = TX[lang] || TX.es;
  const wrap = document.createElement('div');
  wrap.className = 'msg b typing';
  wrap.id = 'tyEl';
  const b = document.createElement('div');
  b.className = 'bub';
  b.innerHTML = `<span class="t-lbl">${t.lbl}</span><div class="dots"><div class="td"></div><div class="td"></div><div class="td"></div></div>`;
  wrap.appendChild(mkAv('b'));
  wrap.appendChild(b);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

function removeTyping() { document.getElementById('tyEl')?.remove(); }


function clearQuickReplies() {
  document.querySelectorAll('.quick-replies').forEach(el => el.remove());
}


function addQuickReplies(options) {
  if (!Array.isArray(options) || options.length === 0) return;
  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = 'msg b quick-replies';

  const body = document.createElement('div');
  body.className = 'chips';
  body.style.marginLeft = '35px';
  body.style.marginTop = '2px';

  options.forEach((opt) => {
    if (!opt || !opt.value) return;
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    btn.textContent = opt.label || opt.value;
    btn.onclick = () => sendMsg(opt.value);
    body.appendChild(btn);
  });

  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}


function quickRepliesFromTarifa(data) {
  const t = TX[lang] || TX.es;
  const missing = data && data.tarifa && Array.isArray(data.tarifa.missing) ? data.tarifa.missing : [];
  if (missing.includes('alcance')) {
    return [
      { label: t.nacional, value: 'nacional' },
      { label: t.internacional, value: 'internacional' },
    ];
  }
  if (missing.includes('tipo_nacional')) {
    return [
      { label: t.ems, value: 'ems' },
      { label: t.prioritario, value: 'encomienda' },
    ];
  }
  if (missing.includes('tipo_internacional')) {
    return [
      { label: t.ems, value: 'ems' },
      { label: t.encomiendas, value: 'encomienda' },
    ];
  }
  return [];
}


// ─── ENVIAR MENSAJE ───────────────────────────────────────────────────
function createStreamingBotMessage() {
  document.getElementById('welcomeCard')?.remove();
  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = 'msg b';

  const bubble = document.createElement('div');
  bubble.className = 'bub';
  bubble.textContent = '';
  bubble.dataset.original = '';

  const tm = document.createElement('span');
  tm.className = 'msg-time';
  tm.textContent = now();

  const body = document.createElement('div');
  body.style.cssText = 'display:flex;flex-direction:column;align-items:flex-start';
  body.appendChild(bubble);
  body.appendChild(tm);

  wrap.appendChild(mkAv('b'));
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return { wrap, body, bubble };
}


async function addTrackingCard(trackingData) {
  if (!trackingData || !trackingData.found) return;
  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = 'msg b';

  const ev = trackingData.ultimo_evento || {};
  const estado = ev.nombre_evento || 'Sin descripción';
  const fecha = (ev.created_at || '—').replace('T', ' ').substring(0, 16);
  const servicio = ev.servicio || '—';
  const oficina = ev.office || ev.ciudad_origen || '—';
  const total = trackingData.total_eventos || 0;
  const codigo = trackingData.codigo || '';
  const trackingUrl = trackingData.tracking_url || `https://trackingbo.correos.gob.bo:8100/?codigo=${codigo}`;
  const safeId = 'qr-' + (codigo || 'tracking').replace(/[^a-zA-Z0-9_-]/g, '');

  const estadoLower = estado.toLowerCase();
  let estadoIcon = '📦';
  if (estadoLower.includes('transit') || estadoLower.includes('proceso')) estadoIcon = '🚚';
  if (estadoLower.includes('entregad')) estadoIcon = '✅';
  if (estadoLower.includes('retenid') || estadoLower.includes('aduana')) estadoIcon = '⚠️';
  if (estadoLower.includes('devuelt')) estadoIcon = '↩️';

  const cardEl = document.createElement('div');
  cardEl.className = 'scard no-translate';
  cardEl.innerHTML = `
    <div class="sc-head" style="background:linear-gradient(135deg,#163A80,#2255B8)">
      <div class="sc-ico"><svg viewBox="0 0 24 24"><path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg></div>
      <div class="sc-htxt"><strong>Estado del envío</strong><span style="font-family:monospace;letter-spacing:0.04em;font-size:0.7rem">${codigo}</span></div>
    </div>
    <div class="sc-body" style="gap:0;padding:12px 14px">
      <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;background:#FFF8E7;border-radius:10px;margin-bottom:10px;border-left:3px solid #E6A817">
        <span style="font-size:1.3rem;line-height:1">${estadoIcon}</span>
        <div>
          <div style="font-size:0.62rem;color:#888;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:1px">Último estado</div>
          <div style="font-size:0.82rem;font-weight:700;color:#1a1a1a;line-height:1.3">${estado}</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#f8f9fa;border-radius:8px;padding:7px 9px">
          <div style="font-size:0.60rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:2px">📍 Origen</div>
          <div style="font-size:0.75rem;font-weight:600;color:#1a1a1a">${oficina}</div>
        </div>
        <div style="background:#f8f9fa;border-radius:8px;padding:7px 9px">
          <div style="font-size:0.60rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:2px">📦 Servicio</div>
          <div style="font-size:0.75rem;font-weight:600;color:#1a1a1a">${servicio}</div>
        </div>
        <div style="background:#f8f9fa;border-radius:8px;padding:7px 9px">
          <div style="font-size:0.60rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:2px">🕐 Fecha</div>
          <div style="font-size:0.72rem;font-weight:600;color:#1a1a1a">${fecha}</div>
        </div>
        <div style="background:#f8f9fa;border-radius:8px;padding:7px 9px">
          <div style="font-size:0.60rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:2px">📋 Eventos</div>
          <div style="font-size:0.75rem;font-weight:600;color:#1a1a1a">${total} registrado${total !== 1 ? 's' : ''}</div>
        </div>
      </div>
      <!-- QR pequeño -->
      <div style="display:flex;align-items:center;justify-content:center;gap:10px;margin-top:10px;padding:8px 10px;background:#f8f9fa;border-radius:10px">
        <div id="qr-${codigo.replace(/[^a-zA-Z0-9]/g,'')}" style="flex-shrink:0"></div>
        <div style="font-size:0.65rem;color:#666;line-height:1.4">📱 <strong>Escanea</strong> para ver el rastreo completo en tu celular</div>
      </div>
    </div>
    <a class="sc-cta" href="${trackingUrl}" target="_blank" rel="noopener noreferrer">
      <svg viewBox="0 0 24 24"><path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg>
      Ver rastreo completo
    </a>
  `;
  wrap.appendChild(mkAv('b'));
  wrap.appendChild(cardEl);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;

  // Generar QR pequeño
  const qrEl = cardEl.querySelector('#qr-' + codigo.replace(/[^a-zA-Z0-9]/g, ''));
  if (qrEl) {
    try {
      if (!window.QRCode) await ensureQRCodeLib();
      new QRCode(qrEl, { text: trackingUrl, width: 72, height: 72, colorDark: '#163A80', colorLight: '#f8f9fa', correctLevel: QRCode.CorrectLevel.M });
    } catch(e) {
      qrEl.style.display = 'none';
    }
  }
  chat.scrollTop = chat.scrollHeight;
}


async function sendMsg(msg) {
  if (busy || translating || !msg.trim()) return;
  busy = true;
  clearQuickReplies();
  const inp = document.getElementById('input');
  inp.disabled = true;
  setStop(true);
  addMsg(msg, 'u');
  showTyping();
  ctrl = new AbortController();
  currentRequestId = newRequestId();
  try {
    const res  = await fetch(`${API_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, lang, sid, request_id: currentRequestId, tarifa_mode: tarifaMode, tracking_mode: trackingMode }),
      signal: ctrl.signal
    });
    if (!res.ok || !res.body) throw new Error('stream_failed');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let streamMsg = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        const data = JSON.parse(line);

        if (data.type === 'start') {
          if (data.sid) {
            sid = data.sid;
            localStorage.setItem('chat_sid', sid);
          }
          continue;
        }

        if (data.type === 'token') {
          if (!streamMsg) {
            removeTyping();
            streamMsg = createStreamingBotMessage();
            streamMsg._fullText = '';
            // Inicializar con cursor parpadeante
            streamMsg.bubble.innerHTML = '<span class="typing-cursor">|</span>';
          }
          
          // Acumular el texto completo
          streamMsg._fullText += data.content || '';
          
          // Mostrar el texto con efecto de escritura y cursor parpadeante
          const textToShow = streamMsg._fullText;
          streamMsg.bubble.innerHTML = textToShow + '<span class="typing-cursor">|</span>';
          streamMsg.bubble.dataset.original = textToShow;
          
          // Auto-scroll suave
          const chat = document.getElementById('chat');
          chat.scrollTop = chat.scrollHeight;
          continue;
        }

        if (data.type === 'end') {
          if (data.sid) {
            sid = data.sid;
            localStorage.setItem('chat_sid', sid);
          }
          removeTyping();

          const bye = data.despedida === true;
          const isBranchesList = data?.response_type === 'branches_list' && Array.isArray(data?.branches);
          if (isBranchesList) {
            if (streamMsg) streamMsg.wrap.remove();
            streamMsg = null;
            addBranchesList(data.branches, data.message || '');
          } else if (streamMsg) {
            const finalText = data.response || streamMsg._fullText || 'Sin respuesta disponible';
            // Remover cursor y mostrar texto final
            streamMsg.bubble.innerHTML = finalText;
            streamMsg.bubble.dataset.original = finalText;
            if (!bye && data.no_translate !== true) {
              autoTranslateBubble(streamMsg.bubble, finalText);
            }
            // Agregar botones 👍👎 al finalizar el streaming
            const logId = data.conversation_log_id || null;
            if (!bye && logId) {
              const acts = document.createElement('div');
              acts.className = 'msg-actions';
              const likeBtn = document.createElement('button');
              likeBtn.className = 'btn-rate';
              likeBtn.type = 'button';
              likeBtn.title = 'Me gustó esta respuesta';
              likeBtn.textContent = '👍';
              const dislikeBtn = document.createElement('button');
              dislikeBtn.className = 'btn-rate';
              dislikeBtn.type = 'button';
              dislikeBtn.title = 'No me gustó esta respuesta';
              dislikeBtn.textContent = '👎';
              likeBtn.onclick = () => rateConversation(logId, 'like', likeBtn, dislikeBtn);
              dislikeBtn.onclick = () => rateConversation(logId, 'dislike', likeBtn, dislikeBtn);
              acts.appendChild(likeBtn);
              acts.appendChild(dislikeBtn);
              streamMsg.body.appendChild(acts);
            }
          } else {
            addMsg(
              data.response || data.error || 'Sin respuesta disponible',
              'b',
              bye,
              data.ubicacion || null,
              data.no_translate === true,
              data.conversation_log_id || null
            );
          }

          if (data?.tarifa?.requires_mode) {
            tarifaMode = false;
            setTarifaModeUI();
          }
          // Mostrar tarjeta visual de tarifa si el backend la devuelve
          if (data?.tarifa_card && data.tarifa_card.precio) {
            addTarifaCard(data.tarifa_card);
          }
          const trackingCode = data?.tracking?.codigo || data?.tracking_code || data?.codigo || data?.tracking?.code || null;
          if (data?.tracking?.found) {
            addTrackingCard(data.tracking);
          }
          // QR eliminado — el botón de la tarjeta lleva directo al link
          addQuickReplies((Array.isArray(data.quick_replies) && data.quick_replies.length > 0) ? data.quick_replies : quickRepliesFromTarifa(data));
          if (bye) {
            inp.disabled = true;
            inp.placeholder = (TX[lang] || TX.es).bye;
            setStop(false);
            document.getElementById('send').disabled = true;
            return;
          }
        }
      }
    }
  } catch (e) {
    removeTyping();
    addMsg(e.name === 'AbortError' ? 'Consulta cancelada.' : 'Error de conexión. Verifique que el servidor esté activo.', 'b');
  }
  ctrl = null;
  currentRequestId = '';
  busy = false;
  setStop(false);
  inp.disabled = false;
  inp.focus();
}

function addBranchesList(branches, intro = '') {
  let texto = (typeof intro === 'string' && intro.trim()) ? `${intro.trim()}\n\n` : '';
  branches.forEach((s) => {
    const nombre = (s?.nombre || '').trim();
    if (nombre) texto += `• ${nombre}\n`;
  });
  addMsg(texto || 'No hay oficinas disponibles en este momento.', 'b', false, null, true, null);
}

function suggest(btn) { sendMsg(btn.textContent); }
function stopResp() {
  if (!ctrl) return;
  fetch(`${API_URL}/chat/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sid, request_id: currentRequestId }),
  }).catch(() => {});
  ctrl.abort();
  ctrl = null;
  currentRequestId = '';
}

// ─── LIMPIAR CONVERSACIÓN ─────────────────────────────────────────────
function clearConv() {
  const bar = document.getElementById('confirm-bar');
  const win = document.getElementById('chat-window');
  if (!bar || !win) return;

  // Posicionar el confirm-bar exactamente en la parte inferior del widget
  const rect = win.getBoundingClientRect();
  bar.style.position = 'fixed';
  bar.style.left = rect.left + 'px';
  bar.style.width = rect.width + 'px';
  bar.style.bottom = (window.innerHeight - rect.bottom) + 'px';
  bar.style.zIndex = '10000';
  bar.style.borderRadius = '0 0 12px 12px';
  bar.style.boxShadow = '0 -2px 12px rgba(0,0,0,0.12)';

  bar.classList.add('open');
}
function closeConf() {
  const bar = document.getElementById('confirm-bar');
  if (bar) {
    bar.classList.remove('open');
    bar.style.position = '';
    bar.style.left = '';
    bar.style.width = '';
    bar.style.bottom = '';
    bar.style.zIndex = '';
  }
}

async function doClear() {
  closeConf();
  try {
    const res = await fetch(`${API_URL}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid }),
    });
    const data = await res.json();
    if (data && data.sid) {
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
  } catch (e) {}

  const chat = document.getElementById('chat');
  chat.innerHTML = '';
  const t  = TX[lang] || TX.es;

  chat.appendChild(buildWelcomeCard());

  const inp = document.getElementById('input');
  inp.disabled    = false;
  inp.placeholder = t.ph;
  document.getElementById('send').disabled = false;
  tarifaMode = false;
  setTarifaModeUI();
  trackingMode = false;
  setTrackingModeUI();
  busy = false;
  setStop(false);
  welcomeLoaded = true;
  loadWelcome();
}

// ─── SUCURSAL MENU ────────────────────────────────────────────────────
function toggleSucursalMenu() {
  const menu = document.getElementById('sucursal-menu');
  const isOpen = menu.style.display === 'block';
  menu.style.display = isOpen ? 'none' : 'block';
}

function closeSucursalMenu() {
  document.getElementById('sucursal-menu').style.display = 'none';
}

// Cerrar si el usuario hace clic fuera del menú
document.addEventListener('click', function(e) {
  const menu = document.getElementById('sucursal-menu');
  const btn = document.getElementById('nearby-toggle');
  if (menu.style.display === 'block' && !menu.contains(e.target) && e.target !== btn) {
    menu.style.display = 'none';
  }
});

async function findNearestBranch() {
  closeSucursalMenu();
  if (isLocating) return;
  if (!navigator.geolocation) {
    addMsg('❌ Tu navegador no soporta geolocalización.', 'b', false, null);
    return;
  }

  // Geolocalización requiere HTTPS — verificar antes de intentar
  if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    addMsg('📍 La función de sucursal cercana requiere conexión segura (HTTPS). Escribe el nombre de tu ciudad para buscar sucursales, por ejemplo: "sucursales La Paz"', 'b', false, null);
    return;
  }

  isLocating = true;
  addMsg('📍 Solicitando acceso a tu ubicación...', 'b', false, null);

  let position;
  try {
    position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,
        timeout: 15000,
        maximumAge: 30000
      });
    });
  } catch (err) {
    isLocating = false;
    let msg = '❌ No se pudo obtener tu ubicación.';
    const s = ' Escribe "sucursales" para ver la lista completa.';
    if (err.code === 1) msg = '❌ Permiso de ubicación denegado. Actívalo en la configuración del navegador.' + s;
    if (err.code === 2) msg = '❌ Ubicación no disponible en este momento.' + s;
    if (err.code === 3) msg = '❌ Tiempo de espera agotado. Intenta de nuevo.' + s;
    addMsg(msg, 'b', false, null);
    return;
  }

  try {
    const lat = position.coords.latitude;
    const lng = position.coords.longitude;
    const res = await fetch(`${API_URL}/sucursal/cercana`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lng, lang, sid }),
    });
    const data = await res.json();
    if (data && data.ok && data.sucursal) {
      addMsg(data.response || `La sucursal más cercana es: ${data.sucursal.nombre}`, 'b', false, null);
      if (data.mi_ubicacion && data.sucursal.lat && data.sucursal.lng) {
        addBranchMap(data.mi_ubicacion, data.sucursal);
      }
      if (data.quick_replies) addQuickReplies(data.quick_replies);
    } else {
      addMsg('❌ No se pudo determinar la sucursal más cercana. Escribe "sucursales" para ver la lista.', 'b', false, null);
    }
  } catch (e) {
    addMsg('❌ Error al buscar la sucursal más cercana.', 'b', false, null);
  } finally {
    isLocating = false;
  }
}

let isLocating = false;

function addBranchMap(userLoc, sucursal) {
  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = 'msg b map-message';

  const body = document.createElement('div');
  body.className = 'bub';
  body.classList.add('no-translate');
  body.style.background = 'var(--white)';
  body.style.border = '1px solid var(--border)';
  body.style.borderRadius = '12px';
  body.style.padding = '8px';
  body.style.width = '100%';
  body.style.maxWidth = '320px';

  const title = document.createElement('div');
  title.textContent = '🗺️ Sucursal más cercana';
  title.style.fontSize = '0.75rem';
  title.style.fontWeight = '600';
  title.style.color = 'var(--b700)';
  title.style.marginBottom = '8px';
  title.style.textAlign = 'center';
  body.appendChild(title);

  const mapDiv = document.createElement('div');
  mapDiv.id = 'map-near-' + Date.now();
  mapDiv.style.height = '200px';
  mapDiv.style.borderRadius = '8px';
  mapDiv.style.overflow = 'hidden';
  body.appendChild(mapDiv);

  const info = document.createElement('div');
  info.style.marginTop = '8px';
  info.style.fontSize = '0.7rem';
  info.style.color = 'var(--ink2)';
  info.innerHTML = `<strong>${sucursal.nombre || 'Sucursal'}</strong><br>${sucursal.direccion || 'Dirección no disponible'}<br>📏 Distancia: ${sucursal.distancia_km || '?'} km<br>🕑 Horario: ${sucursal.horario || 'Consultar'}`;
  body.appendChild(info);

  wrap.appendChild(mkAv('b'));
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;

  setTimeout(() => {
    try {
      if (!window.L) throw new Error('Leaflet no disponible');
      const map = L.map(mapDiv.id).setView([sucursal.lat, sucursal.lng], 13);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
      }).addTo(map);

      const userIcon = L.divIcon({
        className: 'user-marker',
        html: '<div style="background:#2255B8;width:12px;height:12px;border-radius:50%;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)"></div>',
        iconSize: [16, 16],
      });
      L.marker([userLoc.lat, userLoc.lng], { icon: userIcon }).addTo(map).bindPopup('Tú');

      const branchIcon = L.divIcon({
        className: 'branch-marker',
        html: '<div style="background:#F5A623;width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)"></div>',
        iconSize: [20, 20],
      });
      L.marker([sucursal.lat, sucursal.lng], { icon: branchIcon }).addTo(map).bindPopup(sucursal.nombre || 'Sucursal');

      const bounds = L.latLngBounds([
        [userLoc.lat, userLoc.lng],
        [sucursal.lat, sucursal.lng],
      ]);
      map.fitBounds(bounds, { padding: [20, 20] });
    } catch (e) {
      console.error('Error mapa sucursal cercana:', e);
      mapDiv.innerHTML = '<div style="padding:20px;color:#999">Mapa no disponible</div>';
    }
  }, 100);
}

// ─── MAPA ─────────────────────────────────────────────────────────────
async function openMap() {
  document.getElementById('mapa-modal').classList.add('open');

  const mapaDiv = document.getElementById('mapa');
  if (mapaDiv) {
    mapaDiv.style.height = '275px';
    mapaDiv.style.width  = '100%';
  }

  if (mapInst) { setTimeout(() => mapInst.invalidateSize(), 150); return; }

  // Esperar a que Leaflet esté listo
  await new Promise(resolve => {
    if (window.L) return resolve();
    const check = setInterval(() => {
      if (window.L) { clearInterval(check); resolve(); }
    }, 50);
    setTimeout(() => { clearInterval(check); resolve(); }, 5000);
  });

  if (!window.L) { console.error('Leaflet no se pudo cargar'); return; }

  let branches = [];
  try {
    const res = await fetch(`${API_URL}/sucursales`);
    branches = (await res.json()).sucursales || [];
  } catch (e) { console.warn('Error cargando sucursales:', e); }

  const center = branches.find(s => s.lat) || { lat: -16.5, lng: -68.15 };
  mapInst = L.map('mapa').setView([center.lat, center.lng], 6);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
  }).addTo(mapInst);

  const ico = L.divIcon({
    className: '',
    html: `<div style="width:32px;height:32px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:#F5A623;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(122,79,0,0.5);border:2px solid rgba(255,255,255,0.5)"><span style="transform:rotate(45deg);font-size:13px;line-height:1;color:#0B1F4E">✉</span></div>`,
    iconSize: [32, 32], iconAnchor: [16, 32], popupAnchor: [0, -36]
  });

  const list = document.getElementById('suc-list');
  list.innerHTML = '';
  branches.forEach(s => {
    if (!s.lat || !s.lng) return;
    const m = L.marker([s.lat, s.lng], { icon: ico }).addTo(mapInst)
      .bindPopup(`<div style="font-family:'DM Sans',sans-serif;font-size:12px;line-height:1.5;color:#1A0E00"><strong>${s.nombre}</strong><br>${s.direccion || ''}<br>🕑 ${s.horario || ''}</div>`);
    const item = document.createElement('div');
    item.className = 'suc-item';
    item.innerHTML = `<div class="suc-ico"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg></div><div class="suc-nfo"><h4>${s.nombre}</h4><p>${s.direccion || 'No disponible'}<br>${s.horario || 'No disponible'}</p></div>`;
    item.onclick = () => { mapInst.setView([s.lat, s.lng], 16); m.openPopup(); };
    list.appendChild(item);
  });
  setTimeout(() => mapInst.invalidateSize(), 200);
}

function closeMap() { document.getElementById('mapa-modal').classList.remove('open'); }

// Cerrar con Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeMap(); if (chatOpen) minimize(); }
});
