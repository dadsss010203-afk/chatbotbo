/* ═══════════════════════════════════════════════════════════════════════
   WIDGET JS - Correos de Bolivia Chat Bubble
   ═══════════════════════════════════════════════════════════════════════ */

// ─── CONFIGURACIÓN ────────────────────────────────────────────────────
let API_URL = '/api';
let lang    = 'es';

// ─── ESTADO ────────────────────────────────────────────────────────────
let chatOpen    = false;
let busy        = false;
let translating = false;
let ctrl        = null;
let tarifaMode  = false;
let trackingMode = false;
let qrLibPromise = null;

// ─── TEXTOS POR IDIOMA ────────────────────────────────────────────────
const TX = {
  es: {
    ph: 'Escriba su consulta aquí…',
    lbl: 'Analizando consulta…',
    bye: 'Conversación finalizada',
    translating: 'Traduciendo conversación…',
    welcome: '¡Hola! Soy chatbotBO, el asistente oficial de Correos de Bolivia. Puedo ayudarte con envíos, sucursales, ubicaciones y más.\n\n• Presiona el botón TARIFAS para activar las consultas de tarifas de envío. Presiónalo de nuevo para desactivarlo.\n• Presiona el botón RASTREO para rastrear un paquete. Presiónalo de nuevo para desactivarlo.\n\n¿En qué puedo ayudarte hoy?',
    chips: [],
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
    chips: [],
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
    console.log('chat-window existe (modo página directa), inyectando contenido de widget.html...');
    // Inyectar contenido de widget.html
    fetch(baseUrl + '/widget.html')
      .then(res => {
        if (!res.ok) throw new Error('widget.html HTTP ' + res.status);
        return res.text();
      })
      .then(html => {
        // Extraer solo el contenido del chat-window del HTML
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const newWindow = doc.getElementById('chat-window');
        if (newWindow) {
          existingWindow.innerHTML = newWindow.innerHTML;
          // Configurar API_URL desde el atributo data-api del script
          if (s && s.dataset.api) {
            API_URL = s.dataset.api.replace(/\/+$/, '');
          }
          console.log('Contenido inyectado. API_URL:', API_URL);
          setTimeout(() => initWidget(s), 100);
        }
      })
      .catch(err => console.error('No se pudo cargar widget.html:', err));
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
  if (s && s.dataset.pos === 'left') {
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

  // Cerrar mapa al hacer clic fuera
  const mapaModal = document.getElementById('mapa-modal');
  if (mapaModal) {
    mapaModal.addEventListener('click', e => {
      if (e.target === e.currentTarget) closeMap();
    });
  }

  // Mostrar mensaje de bienvenida como burbuja del bot
  // (aparece debajo de los chips y NO desaparece al escribir)
  setTimeout(() => {
    const t = TX[lang] || TX.es;
    addWelcomeMsg(t.welcome);
  }, 200);

  if (lang !== 'es') setLang(lang);
  setTarifaModeUI();
  setTrackingModeUI();

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

// ─── TOGGLE CHAT ──────────────────────────────────────────────────────
function toggleChat() {
  console.log('toggleChat llamado, chatOpen actual:', chatOpen);
  chatOpen = !chatOpen;
  console.log('Nuevo chatOpen:', chatOpen);
  const chatWindow = document.getElementById('chat-window');
  console.log('chat-window element:', chatWindow);
  if (chatWindow) {
    chatWindow.classList.toggle('open', chatOpen);
    // Forzar opacidad correcta
    chatWindow.style.opacity = chatOpen ? '1' : '0';
    console.log('Clase open toggled. Nueva clase:', chatWindow.className);
    console.log('Contenido HTML del chat-window:', chatWindow.innerHTML.substring(0, 200));
    const style = window.getComputedStyle(chatWindow);
    console.log('Display:', style.display);
    console.log('Opacity:', style.opacity);
  } else {
    console.error('chat-window no encontrado');
  }
  if (chatOpen) {
    document.getElementById('badge').style.display = 'none';
    setTimeout(() => document.getElementById('input').focus(), 420);
  }
}

function minimize() {
  document.getElementById('chat-window').classList.remove('open');
  chatOpen = false;
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

  if (tarifaBtn) {
    tarifaBtn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
  }
  if (trackingBtn) {
    trackingBtn.textContent = trackingMode ? t.trackingCancel : t.tracking;
  }
  if (nearbyBtn) {
    nearbyBtn.textContent = t.nearby;
    console.log('Botón sucursales actualizado:', t.nearby);
  } else {
    console.log('Botón sucursales no encontrado');
  }
  if (fHint) {
    fHint.textContent = t.enterHint;
  }
  if (confirmText) {
    confirmText.innerHTML = t.confirmText;
  }
  if (cancelBtn) {
    cancelBtn.textContent = t.cancelBtn;
  }
  if (confirmBtn) {
    confirmBtn.textContent = t.confirmBtn;
  }

  // No traducir conversación existente, el backend ya responde en el idioma correcto
  // await translateConversation();
  const cc = document.getElementById('chips-container');
  if (cc) {
    cc.innerHTML = t.chips.map(c => `<button class="chip" onclick="suggest(this)">${c}</button>`).join('');
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
  a.innerHTML = t === 'u'
    ? '<svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>'
    : '<svg viewBox="0 0 24 24"><path d="M20 4H4C2.9 4 2 4.9 2 6v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>';
  return a;
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
        <div class="sc-htxt"><strong>${loc.nombre || 'Sucursal AGBC'}</strong><span>Sucursal AGBC</span></div>
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
async function addTrackingQR(trackingUrl, codigo) {
  if (!trackingUrl) return;
  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = 'msg b qr-message';

  const body = document.createElement('div');
  body.className = 'bub';
  body.classList.add('no-translate');
  body.style.background = 'var(--white)';
  body.style.border = '1px solid var(--border)';
  body.style.borderRadius = '12px';
  body.style.padding = '12px';
  body.style.width = '100%';
  body.style.maxWidth = '280px';
  body.style.textAlign = 'center';

  const title = document.createElement('div');
  title.textContent = '📱 Escanea para rastrear en tu celular';
  title.style.fontSize = '0.75rem';
  title.style.fontWeight = '600';
  title.style.color = 'var(--b700)';
  title.style.marginBottom = '10px';
  body.appendChild(title);

  const qrContainer = document.createElement('div');
  const safeCode = (codigo || 'tracking').toString().replace(/[^a-zA-Z0-9_-]/g, '');
  qrContainer.id = 'qr-' + safeCode;
  qrContainer.style.display = 'flex';
  qrContainer.style.justifyContent = 'center';
  qrContainer.style.padding = '8px';
  qrContainer.style.background = 'white';
  qrContainer.style.borderRadius = '8px';
  body.appendChild(qrContainer);

  const link = document.createElement('a');
  link.href = trackingUrl;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = '🔗 Abrir en web de Correos';
  link.style.display = 'inline-block';
  link.style.marginTop = '10px';
  link.style.fontSize = '0.72rem';
  link.style.fontWeight = '600';
  link.style.color = 'var(--b700)';
  link.style.textDecoration = 'none';
  body.appendChild(link);

  wrap.appendChild(mkAv('b'));
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;

  try {
    if (!window.QRCode) {
      await ensureQRCodeLib();
    }
    new QRCode(qrContainer, {
      text: trackingUrl,
      width: 128,
      height: 128,
      colorDark: '#0B1F4E',
      colorLight: '#ffffff',
      correctLevel: QRCode.CorrectLevel.M
    });
  } catch (e) {
    console.error('Error generando QR:', e);
    qrContainer.innerHTML = '<div style="padding:20px;color:#999;font-size:0.7rem">Ver en: ' + trackingUrl + '</div>';
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
    const res  = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, lang, sid, request_id: currentRequestId, tarifa_mode: tarifaMode, tracking_mode: trackingMode }),
      signal: ctrl.signal
    });
    const data = await res.json();
    console.log('Respuesta del backend:', data);
    if (data && data.sid) {
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
    removeTyping();
    const bye = data.despedida === true;
    const isBranchesList = data?.response_type === 'branches_list' && Array.isArray(data?.branches);
    if (isBranchesList) {
      addBranchesList(data.branches, data.message || '');
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
    const trackingUrl = data?.tracking?.tracking_url || data?.tracking_url || data?.tracking?.url || null;
    const trackingCode = data?.tracking?.codigo || data?.tracking_code || data?.codigo || data?.tracking?.code || null;
    if (trackingUrl) {
      await addTrackingQR(trackingUrl, trackingCode);
    }
    addQuickReplies((Array.isArray(data.quick_replies) && data.quick_replies.length > 0) ? data.quick_replies : quickRepliesFromTarifa(data));
    if (bye) {
      inp.disabled = true;
      inp.placeholder = (TX[lang] || TX.es).bye;
      setStop(false);
      document.getElementById('send').disabled = true;
      return;
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
function clearConv() { document.getElementById('confirm-bar').classList.add('open'); }
function closeConf() { document.getElementById('confirm-bar').classList.remove('open'); }

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

  addWelcomeMsg(t.welcome);

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
    addMsg('Tu navegador no soporta geolocalización.', 'b', false, null);
    return;
  }

  isLocating = true;
  addMsg('Solicitando acceso a tu ubicación...', 'b', false, null);

  navigator.geolocation.getCurrentPosition(
    async position => {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;

      try {
        const res = await fetch(`${API_URL}/sucursal/cercana`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lat, lng, lang, sid }),
        });
        const data = await res.json();

        if (data && data.ok && data.sucursal) {
          addMsg(data.response || `La sucursal más cercana es: ${data.sucursal.nombre} - ${data.sucursal.direccion}`, 'b', false, null);
          if (data.mi_ubicacion && data.sucursal && data.sucursal.lat && data.sucursal.lng) {
            addBranchMap(data.mi_ubicacion, data.sucursal);
          }
          if (data.quick_replies) addQuickReplies(data.quick_replies);
        } else {
          addMsg('No se pudo determinar la sucursal más cercana. Asegúrate de tener habilitado el GPS.', 'b', false, null);
        }
      } catch (e) {
        addMsg('Error al buscar la sucursal más cercana.', 'b', false, null);
      } finally {
        isLocating = false;
      }
    },
    error => {
      let msg = 'No se pudo obtener tu ubicación.';
      if (error && error.code === 1) msg = 'Permiso de ubicación denegado.';
      if (error && error.code === 2) msg = 'No se pudo determinar tu ubicación.';
      if (error && error.code === 3) msg = 'La solicitud de ubicación tardó demasiado.';
      addMsg(msg, 'b', false, null);
      isLocating = false;
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
    }
  );
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
