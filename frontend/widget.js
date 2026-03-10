/* ═══════════════════════════════════════════════════════════════
   WIDGET JS - Correos de Bolivia Chat Bubble
   ═══════════════════════════════════════════════════════════════ */

// ─── CONFIGURACIÓN ─────────────────────────────────
let API_URL = '/api';
let lang    = 'es';

// ─── AUTO-INICIALIZACIÓN EN MODO WIDGET ───────────────────
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

  // Si el widget ya está en el DOM (chatbot.html nativo) no inyectar
  if (document.getElementById('chat-window')) {
    initWidget(s);
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
      initWidget(s);
    })
    .catch(err => console.error('No se pudo cargar widget.html:', err));
})();


// ─── INICIALIZAR ───────────────────────────────────
function initWidget(s) {
  if (s && s.dataset.pos === 'left') {
    const bubble = document.getElementById('chat-bubble');
    const win    = document.getElementById('chat-window');
    if (bubble) { bubble.style.left = '28px';  bubble.style.right = 'auto'; }
    if (win)    { win.style.left    = '22px';  win.style.right    = 'auto'; }
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

  console.log('Chat Bubble Widget - Correos de Bolivia cargado');
}


// ─── ESTADO ────────────────────────────────────────
let chatOpen    = false;
let busy        = false;
let translating = false;
let ctrl        = null;
let mapInst     = null;

// ─── TEXTOS POR IDIOMA ─────────────────────────────
const TX = {
  es: {
    ph: 'Escriba su consulta aquí…',
    lbl: 'Analizando consulta…',
    bye: 'Conversación finalizada',
    translating: 'Traduciendo conversación…',
    welcome: 'Hola  Soy chatbotBO asistente de la Agencia Boliviana de Correos. Puedo ayudarle con envíos, tarifas, rastreo de paquetes, sucursales y más. ¿En qué le puedo ayudar?',
    chips: []
  },
  en: {
    ph: 'Type your question here…',
    lbl: 'Processing request…',
    bye: 'Conversation ended',
    translating: 'Translating conversation…',
    welcome: 'Hello  I am chatboBo the virtual assistant of the Bolivian Postal Agency. I can help you with shipments, rates, package tracking, branches and more. How can I help you?',
    chips: []
  },
  fr: {
    ph: 'Saisissez votre question…',
    lbl: 'Traitement en cours…',
    bye: 'Conversation terminée',
    translating: 'Traduction en cours…',
    welcome: "Bonjour  Je suis l'assistant virtuel de l'Agence Postale Bolivienne. Je peux vous aider avec les envois, tarifs, suivi de colis, succursales et plus. Comment puis-je vous aider ?",
    chips: []
  },
  pt: {
    ph: 'Digite sua consulta aqui…',
    lbl: 'Processando sua consulta…',
    bye: 'Conversa encerrada',
    translating: 'Traduzindo conversa…',
    welcome: 'Olá  Sou o assistente virtual da Agência Boliviana de Correios. Posso ajudá-lo com envios, tarifas, rastreamento de pacotes, agências e mais. Como posso ajudá-lo?',
    chips: []
  },
  zh: {
    ph: '请在此输入您的问题…',
    lbl: '正在处理您的请求…',
    bye: '对话已结束',
    translating: '正在翻译对话…',
    welcome: '您好  我是玻利维亚邮政局的虚拟助手。我可以帮助您处理邮件、费率、包裹追踪、网点等问题。请问有什么可以帮助您？',
    chips: ['追踪包裹', '邮寄费率', '附近网点', '营业时间']
  },
  ru: {
    ph: 'Введите ваш вопрос…',
    lbl: 'Обработка запроса…',
    bye: 'Разговор завершён',
    translating: 'Перевод разговора…',
    welcome: 'Здравствуйте  Я виртуальный помощник Боливийского почтового агентства. Я помогу вам с доставкой, тарифами, отслеживанием посылок, отделениями и многим другим. Чем могу помочь?',
    chips: []
  }
};

// ─── UI HELPERS ────────────────────────────────────
function setStop(v) {
  document.getElementById('stop').classList.toggle('vis', v);
  document.getElementById('send').style.display = v ? 'none' : 'flex';
}

function now() {
  return new Date().toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit' });
}

// ─── TOGGLE CHAT ───────────────────────────────────
function toggleChat() {
  chatOpen = !chatOpen;
  document.getElementById('chat-window').classList.toggle('open', chatOpen);
  if (chatOpen) {
    document.getElementById('badge').style.display = 'none';
    setTimeout(() => document.getElementById('input').focus(), 420);
  }
}

function minimize() {
  document.getElementById('chat-window').classList.remove('open');
  chatOpen = false;
}

// ─── IDIOMA ─────────────────────────────────────────
async function setLang(l) {
  if (translating || busy || l === lang) return;
  lang = l;

  document.querySelectorAll('.lpill').forEach(b => b.classList.toggle('on', b.dataset.lang === l));

  const t = TX[l] || TX.es;
  document.getElementById('input').placeholder = t.ph;

  // Actualizar chips
  const cc = document.getElementById('chips-container');
  if (cc) {
    cc.innerHTML = t.chips.map(c => `<button class="chip" onclick="suggest(this)">${c}</button>`).join('');
  }

  await translateConversation();
}

// ─── TRADUCIR CONVERSACIÓN ─────────────────────────
async function translateConversation() {
  const bubbles = Array.from(document.querySelectorAll('.msg.b .bub:not(.farewell)'));
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

// ─── AVATARES ───────────────────────────────────────
function mkAv(t) {
  const a = document.createElement('div');
  a.className = 'av';
  a.innerHTML = t === 'u'
    ? '<svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>'
    : '<svg viewBox="0 0 24 24"><path d="M20 4H4C2.9 4 2 4.9 2 6v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>';
  return a;
}

// ─── MENSAJE DE BIENVENIDA (burbuja fija, no desaparece) ───
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

// ─── AÑADIR MENSAJE ────────────────────────────────
function addMsg(text, type, bye = false) {
  // Solo eliminar el card de chips, la burbuja de bienvenida (welcomeMsg) se queda
  document.getElementById('welcomeCard')?.remove();

  const chat = document.getElementById('chat');
  const wrap = document.createElement('div');
  wrap.className = `msg ${type}`;

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

  if (!bye && type === 'b') {
    const acts = document.createElement('div');
    acts.className = 'msg-actions';
    const btn = document.createElement('button');
    
    acts.appendChild(btn);
    body.appendChild(acts);
  }

  wrap.appendChild(mkAv(type));
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

// ─── TRADUCIR MENSAJE INDIVIDUAL ───────────────────
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

// ─── TYPING INDICATOR ──────────────────────────────
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

// ─── ENVIAR MENSAJE ────────────────────────────────
async function sendMsg(msg) {
  if (busy || translating || !msg.trim()) return;
  busy = true;
  const inp = document.getElementById('input');
  inp.disabled = true;
  setStop(true);
  addMsg(msg, 'u');
  showTyping();
  ctrl = new AbortController();
  try {
    const res  = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, lang }),
      signal: ctrl.signal
    });
    const data = await res.json();
    removeTyping();
    const bye = data.despedida === true;
    addMsg(data.response || data.error || 'Sin respuesta disponible', 'b', bye);
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
  busy = false;
  setStop(false);
  inp.disabled = false;
  inp.focus();
}

function suggest(btn) { sendMsg(btn.textContent); }
function stopResp()   { if (ctrl) { ctrl.abort(); ctrl = null; } }

// ─── LIMPIAR CONVERSACIÓN ──────────────────────────
function clearConv() { document.getElementById('confirm-bar').classList.add('open'); }
function closeConf() { document.getElementById('confirm-bar').classList.remove('open'); }

async function doClear() {
  closeConf();
  try {
    await fetch(`${API_URL}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (e) {}

  const chat = document.getElementById('chat');
  chat.innerHTML = '';
  const t  = TX[lang] || TX.es;

  // Reconstruir el card de chips
  const wc = document.createElement('div');
  wc.className = 'welcome';
  wc.id = 'welcomeCard';
  wc.innerHTML = `
    <div class="wc-icon"><svg viewBox="0 0 24 24"><path d="M20 4H4C2.9 4 2 4.9 2 6v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg></div>
    <div class="wc-title">Bienvenido</div>
    <div class="chips" id="chips-container">
      ${t.chips.map(c => `<button class="chip" onclick="suggest(this)">${c}</button>`).join('')}
    </div>`;
  chat.appendChild(wc);

  // Volver a mostrar el mensaje de bienvenida como burbuja
  addWelcomeMsg(t.welcome);

  const inp = document.getElementById('input');
  inp.disabled    = false;
  inp.placeholder = t.ph;
  document.getElementById('send').disabled = false;
  busy = false;
  setStop(false);
}

// ─── MAPA ──────────────────────────────────────────
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
      .bindPopup(`<div style="font-family:'DM Sans',sans-serif;font-size:12px;line-height:1.5;color:#1A0E00"><strong>${s.nombre}</strong><br>📍 ${s.direccion || ''}<br>🕐 ${s.horario || ''}</div>`);
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