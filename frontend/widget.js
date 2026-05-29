     1|/* ═══════════════════════════════════════════════════════════════════════
     2|   WIDGET JS - Correos de Bolivia Chat Bubble
     3|   ═══════════════════════════════════════════════════════════════════════ */
     4|
     5|// ─── CONFIGURACIÓN ────────────────────────────────────────────────────
     6|let API_URL = '/api';
     7|let lang    = 'es';
     8|let embedMode = false;
     9|let widgetPos = 'right';
    10|
    11|// ─── ESTADO ────────────────────────────────────────────────────────────
    12|let chatOpen    = false;
    13|let busy        = false;
    14|let translating = false;
    15|let ctrl        = null;
    16|let tarifaMode  = false;
    17|let trackingMode = false;
    18|let qrLibPromise = null;
    19|let welcomeLoaded = false;
    20|
    21|// ─── TEXTOS POR IDIOMA ────────────────────────────────────────────────
    22|const TX = {
    23|  es: {
    24|    ph: 'Escriba su consulta aquí…',
    25|    lbl: 'Analizando consulta…',
    26|    bye: 'Conversación finalizada',
    27|    translating: 'Traduciendo conversación…',
    28|    welcome: '¡Hola! Soy ChatbotBO, el asistente oficial de Correos de Bolivia.\n\nPuedo ayudarte con envíos, sucursales, ubicaciones y más.\n\n• Presiona TARIFAS para consultar precios de envío.\n• Presiona RASTREO para rastrear un paquete.\n\n¿En qué puedo ayudarte hoy?',
    29|    chips: ['📦 Rastrear paquete', '💰 Ver tarifas', '📍 Sucursales', '🕐 Horarios', '✉️ ¿Qué es EMS?'],
    30|    tarifa: 'Tarifas',
    31|    tarifaCancel: 'Cancelar tarifa',
    32|    tracking: 'Rastreo',
    33|    trackingCancel: 'Cancelar rastreo',
    34|    nearby: 'Sucursales',
    35|    enterHint: 'Enter para enviar',
    36|    confirmText: '¿Borrar toda la conversación?',
    37|    cancelBtn: 'Cancelar',
    38|    confirmBtn: 'Confirmar',
    39|    tarifaMode: 'Modo tarifas activado. ¿Qué servicio quieres usar?',
    40|    trackingMode: 'Modo rastreo activado. Envíame tu código de rastreo.',
    41|    tarifaCancelled: 'Modo tarifas cancelado. Volviste al chat general.',
    42|    trackingCancelled: 'Modo rastreo cancelado. Volviste al chat general.',
    43|    nacional: 'Nacional',
    44|    internacional: 'Internacional',
    45|    ems: 'Express Mail Service (EMS)',
    46|    prioritario: 'Prioritario',
    47|    encomiendas: 'Encomiendas Postales'
    48|  },
    49|  en: {
    50|    ph: 'Type your question here…',
    51|    lbl: 'Processing request…',
    52|    bye: 'Conversation ended',
    53|    translating: 'Translating conversation…',
    54|    welcome: 'Hello! I am chatbotBO, the virtual assistant of the Bolivian Postal Agency. I can help you with shipments, package tracking, branches and more. How can I help you?',
    55|    chips: ['📦 Track package', '💰 View rates', '📍 Branches', '🕐 Office hours', '✉️ What is EMS?'],
    56|    tarifa: 'Rates',
    57|    tarifaCancel: 'Cancel rates',
    58|    tracking: 'Tracking',
    59|    trackingCancel: 'Cancel tracking',
    60|    nearby: 'Branches',
    61|    enterHint: 'Enter to send',
    62|    confirmText: 'Delete entire conversation?',
    63|    cancelBtn: 'Cancel',
    64|    confirmBtn: 'Confirm',
    65|    tarifaMode: 'Rates mode activated. What service do you want to use?',
    66|    trackingMode: 'Tracking mode activated. Send me your tracking code.',
    67|    tarifaCancelled: 'Rates mode cancelled. Back to general chat.',
    68|    trackingCancelled: 'Tracking mode cancelled. Back to general chat.',
    69|    nacional: 'National',
    70|    internacional: 'International',
    71|    ems: 'Express Mail Service (EMS)',
    72|    prioritario: 'Priority',
    73|    encomiendas: 'Postal Parcels'
    74|  },
    75|};
    76|
    77|// ─── AUTO-INICIALIZACIÓN EN MODO WIDGET ──────────────────────────────
    78|console.log('Widget.js cargando...');
    79|(function(){
    80|  let s = document.currentScript;
    81|  if (!s) {
    82|    const all = document.getElementsByTagName('script');
    83|    for (let i = all.length - 1; i >= 0; --i) {
    84|      if ((all[i].src || '').includes('widget.js')) { s = all[i]; break; }
    85|    }
    86|  }
    87|
    88|  if (s) {
    89|    if (s.dataset.api)  API_URL = s.dataset.api.replace(/\/+$/, '');
    90|    if (s.dataset.lang) lang    = s.dataset.lang;
    91|  }
    92|
    93|  const params = new URLSearchParams(window.location.search || '');
    94|  if (params.get('api')) API_URL = params.get('api').replace(/\/+$/, '');
    95|  if (params.get('lang')) lang = params.get('lang');
    96|  if (params.get('embed') === '1') embedMode = true;
    97|  if (params.get('pos') === 'left') widgetPos = 'left';
    98|  if (s && s.dataset.pos === 'left') widgetPos = 'left';
    99|  if (embedMode) document.body.classList.add('widget-shell');
   100|
   101|  const baseUrl = s
   102|    ? s.src.replace(/\/widget\.js.*$/, '')
   103|    : API_URL.replace(/\/api$/, '');
   104|
   105|  console.log('widget.js | baseUrl:', baseUrl, '| API_URL:', API_URL);
   106|
   107|  // Cargar Leaflet YA (los <script> en HTML inyectado no ejecutan)
   108|  if (!window.L) {
   109|    const lCss = document.createElement('link');
   110|    lCss.rel   = 'stylesheet';
   111|    lCss.href  = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
   112|    document.head.appendChild(lCss);
   113|    const lJs = document.createElement('script');
   114|    lJs.src   = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
   115|    document.head.appendChild(lJs);
   116|  }
   117|  ensureQRCodeLib().catch(err => console.warn('No se pudo precargar QRCode:', err));
   118|
   119|  // Si el widget ya está en el DOM (chatbot.html nativo) inyectar contenido de widget.html
   120|  const existingWindow = document.getElementById('chat-window');
   121|  if (existingWindow) {
   122|    console.log('chat-window existe, inicializando widget ya presente en el DOM...');
   123|    setTimeout(() => initWidget(s), 100);
   124|    return;
   125|  }
   126|
   127|  // Inyectar CSS
   128|  const link  = document.createElement('link');
   129|  link.rel    = 'stylesheet';
   130|  link.href   = baseUrl + '/widget.css';
   131|  document.head.appendChild(link);
   132|
   133|  // Inyectar HTML y luego inicializar
   134|  fetch(baseUrl + '/widget.html')
   135|    .then(res => {
   136|      if (!res.ok) throw new Error('widget.html HTTP ' + res.status);
   137|      return res.text();
   138|    })
   139|    .then(html => {
   140|      // Reemplazar rutas relativas con URL absoluta del servidor
   141|      html = html.replace(/src="\/logogif\.gif"/g, `src="${baseUrl}/logogif.gif"`);
   142|      html = html.replace(/src="\/logo_chatbot\.png"/g, `src="${baseUrl}/logo_chatbot.png"`);
   143|      html = html.replace(/src="\/logocorreos\.jpg"/g, `src="${baseUrl}/logocorreos.jpg"`);
   144|      document.body.insertAdjacentHTML('beforeend', html);
   145|      // Retrasar la inicialización para asegurar que el script se cargue completamente
   146|      setTimeout(() => initWidget(s), 100);
   147|    })
   148|    .catch(err => console.error('No se pudo cargar widget.html:', err));
   149|  console.log('Widget auto-inicialización completada');
   150|})();
   151|
   152|
   153|// ─── INICIALIZAR ──────────────────────────────────────────────────────
   154|function initWidget(s) {
   155|  console.log('initWidget llamado');
   156|  if (window._widgetInitialized) {
   157|    console.log('initWidget ya fue llamado, ignorando.');
   158|    return;
   159|  }
   160|  window._widgetInitialized = true;
   161|  if (widgetPos === 'left') {
   162|    const bubble = document.getElementById('chat-bubble');
   163|    const win    = document.getElementById('chat-window');
   164|    if (bubble) { bubble.style.left = '28px';  bubble.style.right = 'auto'; }
   165|    if (win)    { win.style.left    = '22px';  win.style.right    = 'auto'; }
   166|  }
   167|
   168|  // La burbuja ya usa onclick en widget.html; evitar doble toggle.
   169|  const bubble = document.getElementById('chat-bubble');
   170|  console.log('Chat bubble element:', bubble);
   171|  if (!bubble) {
   172|    console.error('Chat bubble no encontrado');
   173|  }
   174|
   175|  // Adjuntar form listener cuando el DOM ya existe
   176|  const form = document.getElementById('form');
   177|  if (form) {
   178|    form.addEventListener('submit', e => {
   179|      e.preventDefault();
   180|      const inp = document.getElementById('input');
   181|      const t   = inp.value.trim();
   182|      if (!t) return;
   183|      inp.value = '';
   184|      sendMsg(t);
   185|    });
   186|  }
   187|
   188|  // Conectar botones del header (sin onclick inline para evitar errores de scope)
   189|  const btnClose    = document.getElementById('btn-close');
   190|  const btnMinimize = document.getElementById('btn-minimize');
   191|  const btnBubble   = document.getElementById('chat-bubble');
   192|  if (btnClose)    btnClose.addEventListener('click', () => toggleChat());
   193|  if (btnMinimize) btnMinimize.addEventListener('click', () => minimize());
   194|  if (btnBubble)   btnBubble.addEventListener('click', () => toggleChat());
   195|
   196|  // Cerrar mapa al hacer clic fuera
   197|  const mapaModal = document.getElementById('mapa-modal');
   198|  if (mapaModal) {
   199|    mapaModal.addEventListener('click', e => {
   200|      if (e.target === e.currentTarget) closeMap();
   201|    });
   202|  }
   203|
   204|  if (lang !== 'es') setLang(lang);
   205|  setTarifaModeUI();
   206|  setTrackingModeUI();
   207|  notifyEmbedState(false);
   208|
   209|  console.log('Chat Bubble Widget - Correos de Bolivia cargado');
   210|}
   211|
   212|
   213|// ─── ESTADO (otras variables globales ya declaradas arriba) ───────────
   214|let mapInst     = null;
   215|let sid         = localStorage.getItem('chat_sid') || '';
   216|let currentRequestId = '';
   217|
   218|function newRequestId() {
   219|  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
   220|    return window.crypto.randomUUID();
   221|  }
   222|  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
   223|}
   224|
   225|function ensureQRCodeLib() {
   226|  if (window.QRCode) return Promise.resolve();
   227|  if (qrLibPromise) return qrLibPromise;
   228|  qrLibPromise = new Promise((resolve, reject) => {
   229|    const existing = document.querySelector('script[data-widget-qr-lib="1"]');
   230|    if (existing) {
   231|      existing.addEventListener('load', () => resolve(), { once: true });
   232|      existing.addEventListener('error', () => reject(new Error('No se pudo cargar QRCode')), { once: true });
   233|      return;
   234|    }
   235|    const script = document.createElement('script');
   236|    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js';
   237|    script.async = true;
   238|    script.dataset.widgetQrLib = '1';
   239|    script.onload = () => resolve();
   240|    script.onerror = () => reject(new Error('No se pudo cargar QRCode'));
   241|    document.head.appendChild(script);
   242|  });
   243|  return qrLibPromise;
   244|}
   245|
   246|// ─── UI HELPERS ───────────────────────────────────────────────────────
   247|function setStop(v) {
   248|  document.getElementById('stop').classList.toggle('vis', v);
   249|  document.getElementById('send').style.display = v ? 'none' : 'flex';
   250|}
   251|
   252|function setTarifaModeUI() {
   253|  const btn = document.getElementById('tarifa-toggle');
   254|  if (!btn) return;
   255|  const t = TX[lang] || TX.es;
   256|  btn.classList.toggle('active', tarifaMode);
   257|  btn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
   258|}
   259|
   260|function setTrackingModeUI() {
   261|  const btn = document.getElementById('tracking-toggle');
   262|  if (!btn) return;
   263|  const t = TX[lang] || TX.es;
   264|  btn.classList.toggle('active', trackingMode);
   265|  btn.textContent = trackingMode ? t.trackingCancel : t.tracking;
   266|}
   267|
   268|async function cancelTarifaMode(notify = true) {
   269|  tarifaMode = false;
   270|  setTarifaModeUI();
   271|  try {
   272|    const res = await fetch(`${API_URL}/tarifa/cancel`, {
   273|      method: 'POST',
   274|      headers: { 'Content-Type': 'application/json' },
   275|      body: JSON.stringify({ sid }),
   276|    });
   277|    const data = await res.json();
   278|    if (data && data.sid) {
   279|      sid = data.sid;
   280|      localStorage.setItem('chat_sid', sid);
   281|    }
   282|  } catch (e) {
   283|    console.warn('No se pudo cancelar flujo tarifa:', e);
   284|  }
   285|  if (notify) {
   286|    const t = TX[lang] || TX.es;
   287|    addMsg(t.tarifaCancelled, 'b', false, null);
   288|  }
   289|}
   290|
   291|async function cancelTrackingMode(notify = true) {
   292|  trackingMode = false;
   293|  setTrackingModeUI();
   294|  try {
   295|    const res = await fetch(`${API_URL}/tracking/cancel`, {
   296|      method: 'POST',
   297|      headers: { 'Content-Type': 'application/json' },
   298|      body: JSON.stringify({ sid }),
   299|    });
   300|    const data = await res.json();
   301|    if (data && data.sid) {
   302|      sid = data.sid;
   303|      localStorage.setItem('chat_sid', sid);
   304|    }
   305|  } catch (e) {
   306|    console.warn('No se pudo cancelar flujo tracking:', e);
   307|  }
   308|  if (notify) {
   309|    const t = TX[lang] || TX.es;
   310|    addMsg(t.trackingCancelled, 'b', false, null);
   311|  }
   312|}
   313|
   314|async function toggleTarifaMode() {
   315|  if (tarifaMode) {
   316|    await cancelTarifaMode(true);
   317|    return;
   318|  }
   319|  if (trackingMode) {
   320|    await cancelTrackingMode(false);
   321|  }
   322|  tarifaMode = true;
   323|  setTarifaModeUI();
   324|  const t = TX[lang] || TX.es;
   325|  try {
   326|    const res = await fetch(`${API_URL}/tarifa/start`, {
   327|      method: 'POST',
   328|      headers: { 'Content-Type': 'application/json' },
   329|      body: JSON.stringify({ sid, lang }),
   330|    });
   331|    const data = await res.json();
   332|    if (data && data.sid) {
   333|      sid = data.sid;
   334|      localStorage.setItem('chat_sid', sid);
   335|    }
   336|    addMsg(data.response || t.tarifaMode, 'b', false, null, false, data.conversation_log_id || null);
   337|    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
   338|  } catch (e) {
   339|    addMsg(t.tarifaMode, 'b', false, null);
   340|  }
   341|}
   342|
   343|async function toggleTrackingMode() {
   344|  if (trackingMode) {
   345|    await cancelTrackingMode(true);
   346|    return;
   347|  }
   348|  if (tarifaMode) {
   349|    await cancelTarifaMode(false);
   350|  }
   351|  trackingMode = true;
   352|  setTrackingModeUI();
   353|  const t = TX[lang] || TX.es;
   354|  try {
   355|    const res = await fetch(`${API_URL}/tracking/start`, {
   356|      method: 'POST',
   357|      headers: { 'Content-Type': 'application/json' },
   358|      body: JSON.stringify({ sid, lang }),
   359|    });
   360|    const data = await res.json();
   361|    if (data && data.sid) {
   362|      sid = data.sid;
   363|      localStorage.setItem('chat_sid', sid);
   364|    }
   365|    addMsg(data.response || t.trackingMode, 'b', false, null, false, data.conversation_log_id || null);
   366|    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
   367|  } catch (e) {
   368|    addMsg(t.trackingMode, 'b', false, null);
   369|  }
   370|}
   371|
   372|function now() {
   373|  return new Date().toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit' });
   374|}
   375|
   376|function notifyEmbedState(open) {
   377|  if (!embedMode || window.parent === window) return;
   378|  window.parent.postMessage({ type: 'chatbotbo:state', open }, '*');
   379|}
   380|
   381|window.addEventListener('message', (event) => {
   382|  const data = event.data || {};
   383|  if (data.type !== 'chatbotbo:command') return;
   384|  if (data.action === 'open' && !chatOpen) toggleChat();
   385|  if (data.action === 'close' && chatOpen) minimize();
   386|});
   387|
   388|// ─── TOGGLE CHAT ──────────────────────────────────────────────────────
   389|function toggleChat() {
   390|  console.log('toggleChat llamado, chatOpen actual:', chatOpen);
   391|  chatOpen = !chatOpen;
   392|  console.log('Nuevo chatOpen:', chatOpen);
   393|  const chatWindow = document.getElementById('chat-window');
   394|  const bubble = document.getElementById('chat-bubble');
   395|  const isMobile = window.innerWidth <= 480;
   396|  console.log('chat-window element:', chatWindow);
   397|  if (chatWindow) {
   398|    chatWindow.classList.toggle('open', chatOpen);
   399|    chatWindow.style.opacity = chatOpen ? '1' : '0';
   400|  } else {
   401|    console.error('chat-window no encontrado');
   402|  }
   403|  if (chatOpen) {
   404|    document.getElementById('badge').style.display = 'none';
   405|    if (isMobile && bubble) bubble.style.display = 'none';
   406|    if (!welcomeLoaded) {
   407|      welcomeLoaded = true;
   408|      loadWelcome();
   409|    }
   410|    setTimeout(() => document.getElementById('input').focus(), 420);
   411|  } else {
   412|    if (bubble) bubble.style.display = 'flex';
   413|  }
   414|  notifyEmbedState(chatOpen);
   415|}
   416|
   417|function minimize() {
   418|  document.getElementById('chat-window').classList.remove('open');
   419|  const bubble = document.getElementById('chat-bubble');
   420|  if (bubble) bubble.style.display = 'flex';
   421|  chatOpen = false;
   422|  notifyEmbedState(false);
   423|}
   424|
   425|// ─── IDIOMA ───────────────────────────────────────────────────────────
   426|async function setLang(l) {
   427|  if (translating || busy || l === lang) return;
   428|  lang = l;
   429|
   430|  document.querySelectorAll('.lpill').forEach(b => b.classList.toggle('on', b.dataset.lang === l));
   431|
   432|  const t = TX[l] || TX.es;
   433|  document.getElementById('input').placeholder = t.ph;
   434|
   435|  // Actualizar botones y textos
   436|  const tarifaBtn = document.getElementById('tarifa-toggle');
   437|  const trackingBtn = document.getElementById('tracking-toggle');
   438|  const nearbyBtn = document.getElementById('nearby-toggle');
   439|  const fHint = document.querySelector('.f-hint');
   440|  const confirmText = document.querySelector('#confirm-bar p');
   441|  const cancelBtn = document.querySelector('.cno');
   442|  const confirmBtn = document.querySelector('.csi');
   443|
   444|  if (tarifaBtn) tarifaBtn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
   445|  if (trackingBtn) trackingBtn.textContent = trackingMode ? t.trackingCancel : t.tracking;
   446|  if (nearbyBtn) nearbyBtn.textContent = t.nearby;
   447|  if (fHint) fHint.textContent = t.enterHint;
   448|  if (confirmText) confirmText.innerHTML = t.confirmText;
   449|  if (cancelBtn) cancelBtn.textContent = t.cancelBtn;
   450|  if (confirmBtn) confirmBtn.textContent = t.confirmBtn;
   451|
   452|  const cc = document.getElementById('chips-container');
   453|  if (cc) {
   454|    cc.innerHTML = t.chips.map(c => `<button class="chip" onclick="suggest(this)">${c}</button>`).join('');
   455|  }
   456|
   457|  // Mostrar banner animado y traducir conversación
   458|  const banner = document.getElementById('translate-banner');
   459|  const bubbles = Array.from(
   460|    document.querySelectorAll('.msg.b .bub:not(.farewell):not(.no-translate)')
   461|  ).filter(b => !b.closest('.qr-message'));
   462|
   463|  if (bubbles.length > 0) {
   464|    // Mostrar banner con animación de puntos
   465|    let dots = 0;
   466|    banner.innerHTML = `<span id="banner-text">${t.translating}</span>`;
   467|    banner.classList.add('vis');
   468|    const dotsInterval = setInterval(() => {
   469|      dots = (dots + 1) % 4;
   470|      const el = document.getElementById('banner-text');
   471|      if (el) el.textContent = t.translating.replace('…', '.'.repeat(dots) || '.');
   472|    }, 400);
   473|
   474|    await translateConversation();
   475|
   476|    clearInterval(dotsInterval);
   477|    banner.classList.remove('vis');
   478|  }
   479|}
   480|
   481|// ─── TRADUCIR CONVERSACIÓN ────────────────────────────────────────────
   482|async function translateConversation() {
   483|  const bubbles = Array.from(
   484|    document.querySelectorAll('.msg.b .bub:not(.farewell):not(.no-translate)')
   485|  ).filter(b => !b.closest('.qr-message'));
   486|  if (bubbles.length === 0) return;
   487|
   488|  translating = true;
   489|  const t      = TX[lang] || TX.es;
   490|  const inp    = document.getElementById('input');
   491|  const banner = document.getElementById('translate-banner');
   492|  const pills  = document.querySelectorAll('.lpill');
   493|
   494|  inp.disabled = true;
   495|  pills.forEach(p => p.disabled = true);
   496|  banner.textContent = t.translating;
   497|  banner.classList.add('vis');
   498|  bubbles.forEach(b => b.classList.add('translating-anim'));
   499|
   500|  const originals = bubbles.map(b => b.dataset.original || b.textContent || '');
   501|