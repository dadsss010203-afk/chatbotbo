// ─── ESTADO ───────────────────────────────────
let chatOpen=false, welcomeLoaded=false, busy=false, ctrl=null, lang='es';
let translating=false; // flag para evitar traducciones simultáneas
let tarifaMode=false;
let trackingMode=false;
let sid = localStorage.getItem('chat_sid') || '';
let currentRequestId='';

// ─── SID con expiracion (30 min) ───────────────
const SID_EXPIRE_MIN = 30;
function _newSid(){ return 'sess_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,8); }
(function(){
  const ts = localStorage.getItem('chat_sid_ts');
  if(!sid || !ts || (Date.now()-parseInt(ts))/60000 > SID_EXPIRE_MIN){
    sid = _newSid();
    localStorage.setItem('chat_sid', sid);
  }
  localStorage.setItem('chat_sid_ts', Date.now().toString());
})();
function resetSid(){
  sid = _newSid();
  localStorage.setItem('chat_sid', sid);
  localStorage.setItem('chat_sid_ts', Date.now().toString());
  const chat = document.getElementById('chat');
  if(chat) chat.innerHTML = '';
  welcomeLoaded = false;
  loadWelcome();
}

function newRequestId(){
  if(window.crypto && typeof window.crypto.randomUUID==='function'){
    return window.crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

// ─── TEXTOS POR IDIOMA ────────────────────────
const TX={
  es:{
    ph:'Escriba su consulta aquí…', lbl:'Analizando consulta…',
    bye:'Conversación finalizada', translating:'Traduciendo conversación…',
    welcome:'Hola, soy ChatbotBO, el asistente oficial de Correos de Bolivia. Puedo ayudarte con envíos, rastreo de paquetes, sucursales y más. ¿En qué puedo ayudarte?',
    chips:['📦 Rastrear paquete','💰 Ver tarifas','📍 Sucursales','📋 Hacer reclamo','📮 Servicios','🕐 Horarios'],
    tarifa:'Tarifas', tarifaCancel:'Cancelar tarifa',
    tracking:'Rastreo', trackingCancel:'Cancelar rastreo',
    nearby:'Sucursales',
    enterHint:'Enter para enviar',
    confirmText:'¿Borrar toda la conversación?',
    cancelBtn:'Cancelar', confirmBtn:'Confirmar',
    tarifaMode:'Modo tarifas activado. ¿Qué servicio quieres usar?',
    trackingMode:'Modo rastreo activado. Envíame tu código de rastreo.',
    tarifaCancelled:'Modo tarifas cancelado. Volviste al chat general.',
    trackingCancelled:'Modo rastreo cancelado. Volviste al chat general.',
    nacional:'Nacional', internacional:'Internacional',
    ems:'Express Mail Service (EMS)', prioritario:'Prioritario',
    encomiendas:'Encomiendas Postales'
  },
  en:{
    ph:'Type your question here…', lbl:'Processing request…',
    bye:'Conversation ended', translating:'Translating conversation…',
    welcome:'Hello  I am chatboBo the virtual assistant of the Bolivian Postal Agency. I can help you with shipments, package tracking, branches and more. How can I help you?',
    chips:['📦 Track package','💰 View rates','📍 Branches','📋 File complaint','📮 Services','🕐 Hours'],
    tarifa:'Rates', tarifaCancel:'Cancel rates',
    tracking:'Tracking', trackingCancel:'Cancel tracking',
    nearby:'Branches',
    enterHint:'Enter to send',
    confirmText:'Delete entire conversation?',
    cancelBtn:'Cancel', confirmBtn:'Confirm',
    tarifaMode:'Rates mode activated. What service do you want to use?',
    trackingMode:'Tracking mode activated. Send me your tracking code.',
    tarifaCancelled:'Rates mode cancelled. Back to general chat.',
    trackingCancelled:'Tracking mode cancelled. Back to general chat.',
    nacional:'National', internacional:'International',
    ems:'Express Mail Service (EMS)', prioritario:'Priority',
    encomiendas:'Postal Parcels'
  },
  fr:{
    ph:'Saisissez votre question…', lbl:'Traitement en cours…',
    bye:'Conversation terminée', translating:'Traduction en cours…',
    chips:[]
  },
  pt:{
    ph:'Digite sua consulta aqui…', lbl:'Processando sua consulta…',
    bye:'Conversa encerrada', translating:'Traduzindo conversa…',
    chips:[]
  },
  zh:{
    ph:'请在此输入您的问题…', lbl:'正在处理您的请求…',
    bye:'对话已结束', translating:'正在翻译对话…',
    chips:[]
  },
  ru:{
    ph:'Введите ваш вопрос…', lbl:'Обработка запроса…',
    bye:'Разговор завершён', translating:'Перевод разговора…',
    chips:[]
  },
};

// Nombres de idioma para el prompt de traducción
const LANG_NAMES={es:'español',en:'inglés',fr:'francés',pt:'portugués',zh:'chino',ru:'ruso'};

function toggleSucursalMenu(){
  const menu = document.getElementById('sucursal-menu');
  const isOpen = menu.style.display === 'block';
  menu.style.display = isOpen ? 'none' : 'block';
}

function closeSucursalMenu(){
  document.getElementById('sucursal-menu').style.display = 'none';
}

// Cerrar si el usuario hace clic fuera del menú
document.addEventListener('click', function(e){
  const menu = document.getElementById('sucursal-menu');
  const btn = document.getElementById('nearby-toggle');
  if(menu.style.display === 'block' && !menu.contains(e.target) && e.target !== btn){
    menu.style.display = 'none';
  }
});

// ─── IDIOMA ───────────────────────────────────
function setLang(l){
  if(translating) return; // no cambiar idioma mientras se traduce
  lang=l;
  document.querySelectorAll('.lpill').forEach(b=>b.classList.toggle('on',b.dataset.lang===l));
  const t=TX[l]||TX.es;
  document.getElementById('input').placeholder=t.ph;

  // Actualizar botones y textos
  const tarifaBtn=document.getElementById('tarifa-toggle');
  const trackingBtn=document.getElementById('tracking-toggle');
  const nearbyBtn=document.getElementById('nearby-toggle');
  const fHint=document.querySelector('.f-hint');
  const confirmText=document.querySelector('#confirm-bar p');
  const cancelBtn=document.querySelector('.cno');
  const confirmBtn=document.querySelector('.csi');

  if(tarifaBtn){
    tarifaBtn.textContent=tarifaMode?t.tarifaCancel:t.tarifa;
  }
  if(trackingBtn){
    trackingBtn.textContent=trackingMode?t.trackingCancel:t.tracking;
  }
  if(nearbyBtn){
    nearbyBtn.textContent=t.nearby;
  }
  if(fHint){
    fHint.textContent=t.enterHint;
  }
  if(confirmText){
    confirmText.innerHTML=t.confirmText;
  }
  if(cancelBtn){
    cancelBtn.textContent=t.cancelBtn;
  }
  if(confirmBtn){
    confirmBtn.textContent=t.confirmBtn;
  }

  // Actualizar chips si la tarjeta de bienvenida está visible
  const cc=document.getElementById('chips-container');
  if(cc) cc.innerHTML=t.chips.map(c=>`<button class="chip" onclick="suggest(this)">${c}</button>`).join('');

  // Limpiar historial de sesión en el backend para que el LLM responda
  // en el nuevo idioma sin estar influenciado por el historial anterior.
  fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sid})}).catch(()=>{});

  // Traducir toda la conversación automáticamente
  translateConversation();
}

// ─── TRADUCIR TODA LA CONVERSACIÓN ───────────
// ahora usamos la ruta /api/translate para traducir en lote y **no
// necesitamos el modelo**; el servidor puede recurrir a librería local
// o a LibreTranslate y la operación es mucho más rápida.
async function translateConversation(){
  // Solo burbujas de texto (no farewell, no tarjetas de sucursal)
  const bubbles=Array.from(
    document.querySelectorAll('.msg .bub:not(.farewell):not(.no-translate)')
  ).filter(b=>!b.closest('.qr-message'));
  if(bubbles.length===0) return;

  translating=true;
  const t=TX[lang]||TX.es;
  const inp=document.getElementById('input');
  const banner=document.getElementById('translate-banner');
  const pills=document.querySelectorAll('.lpill');

  // Bloquear UI durante traducción
  inp.disabled=true;
  pills.forEach(p=>p.disabled=true);
  banner.textContent=`  ${t.translating}`;
  banner.classList.add('vis');

  // Animar burbujas con opacidad baja
  bubbles.forEach(b=>b.classList.add('translating-anim'));

  // Preparar array de textos originales
  const originals = bubbles.map(b => {
    const orig = b.dataset.original || b.textContent || '';
    if(!b.dataset.original) b.dataset.original = orig;
    return orig;
  });

  // para que el banner sea visible aunque la petición vuelva instantánea
  const start = Date.now();
  try{
    const res = await fetch('/api/translate', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ texts: originals, lang })
    });
    const data = await res.json();
    if(Array.isArray(data.translations)){
      data.translations.forEach((tr, idx)=>{
        if(bubbles[idx]){
          // fallback a original si la traducción viene vacía
          const out = (typeof tr==='string' && tr.trim()!=="" ) ? tr : originals[idx];
          bubbles[idx].innerHTML = formatBotText(out);
        }
      });
    }
  }catch(e){
    console.warn('Error traduciendo conversación:', e);
    // si falla todo, no rompemos la UI; dejaremos los originales
  }
  // mantener banner visible mínimo 300ms
  const elapsed = Date.now() - start;
  if(elapsed < 300) await new Promise(r=>setTimeout(r, 300 - elapsed));

  // Restaurar UI
  bubbles.forEach(b=>b.classList.remove('translating-anim'));
  banner.classList.remove('vis');
  inp.disabled=false;
  pills.forEach(p=>p.disabled=false);
  translating=false;
  if(!busy) inp.focus();
}

// ─── UI HELPERS ───────────────────────────────
function setStop(v){document.getElementById('stop').classList.toggle('vis',v);document.getElementById('send').style.display=v?'none':'flex';}
function stopResp(){
  if(!ctrl) return;
  fetch('/api/chat/cancel',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sid,request_id:currentRequestId}),
  }).catch(()=>{});
  ctrl.abort();
  ctrl=null;
  currentRequestId='';
}
function minimize(){
  document.getElementById('chat-window').classList.remove('open');
  document.getElementById('chat-bubble').style.display='flex';
  chatOpen=false;
}
function now(){return new Date().toLocaleTimeString('es-BO',{hour:'2-digit',minute:'2-digit'});}
function setTarifaModeUI(){
  const btn=document.getElementById('tarifa-toggle');
  if(!btn) return;
  const t=TX[lang]||TX.es;
  btn.classList.toggle('active', tarifaMode);
  btn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
}

function setTrackingModeUI(){
  const btn=document.getElementById('tracking-toggle');
  if(!btn) return;
  const t=TX[lang]||TX.es;
  btn.classList.toggle('active', trackingMode);
  btn.textContent = trackingMode ? t.trackingCancel : t.tracking;
}

async function cancelTarifaMode(notify=true){
  tarifaMode=false;
  setTarifaModeUI();
  try{
    const res = await fetch('/api/tarifa/cancel',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sid}),
    });
    const data = await res.json();
    if(data && data.sid){
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
  }catch(e){
    console.warn('No se pudo cancelar flujo tarifa:', e);
  }
  if(notify){
    const t=TX[lang]||TX.es;
    addMsg(t.tarifaCancelled,'b',false,null,true,null);
  }
}

async function cancelTrackingMode(notify=true){
  trackingMode=false;
  setTrackingModeUI();
  try{
    const res = await fetch('/api/tracking/cancel',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sid}),
    });
    const data = await res.json();
    if(data && data.sid){
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
  }catch(e){
    console.warn('No se pudo cancelar flujo tracking:', e);
  }
  if(notify){
    const t=TX[lang]||TX.es;
    addMsg(t.trackingCancelled,'b',false,null,true,null);
  }
}

async function toggleTarifaMode(){
  if(tarifaMode){
    await cancelTarifaMode(true);
    return;
  }
  if(trackingMode){
    await cancelTrackingMode(false);
  }
  tarifaMode=true;
  setTarifaModeUI();
  const t=TX[lang]||TX.es;
  try{
    const res = await fetch('/api/tarifa/start',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sid,lang}),
    });
    const data = await res.json();
    if(data && data.sid){
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
    addMsg(data.response||t.tarifaMode,'b',false,null,true,data.conversation_log_id||null);
    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
  }catch(e){
    addMsg(t.tarifaMode,'b',false,null,true,null);
  }
}

async function toggleTrackingMode(){
  if(trackingMode){
    await cancelTrackingMode(true);
    return;
  }
  if(tarifaMode){
    await cancelTarifaMode(false);
  }
  trackingMode=true;
  setTrackingModeUI();
  const t=TX[lang]||TX.es;
  try{
    const res = await fetch('/api/tracking/start',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sid,lang}),
    });
    const data = await res.json();
    if(data && data.sid){
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
    addMsg(data.response||t.trackingMode,'b',false,null,true,data.conversation_log_id||null);
    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
  }catch(e){
    addMsg(t.trackingMode,'b',false,null,true,null);
  }
}

function toggleChat(){
  chatOpen=!chatOpen;
  document.getElementById('chat-window').classList.toggle('open',chatOpen);
  const bubble=document.getElementById('chat-bubble');
  const isMobile=window.innerWidth<=480;
  if(chatOpen){
    document.getElementById('badge').style.display='none';
    if(isMobile) bubble.style.display='none';
    if(!welcomeLoaded){welcomeLoaded=true;loadWelcome();}
    setTimeout(()=>document.getElementById('input').focus(),420);
  } else {
    bubble.style.display='flex';
  }
}

// ─── AVATARES ─────────────────────────────────
function mkAv(t){
  const a=document.createElement('div');a.className='av';
  if(t==='b'){
    a.style.cssText='background:linear-gradient(145deg,#FFC145,#C8860E);border-radius:50%;display:flex;align-items:center;justify-content:center;width:44px;height:44px;flex-shrink:0;box-shadow:0 0 0 3px rgba(200,134,14,0.4),0 4px 12px rgba(122,79,0,0.5);';
    const uid='e'+Math.random().toString(36).slice(2,7);
    a.innerHTML=`<svg viewBox="0 0 44 44" width="44" height="44" xmlns="http://www.w3.org/2000/svg">
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
    let dir=1,pos=0;
    setInterval(()=>{
      pos+=dir*0.12;
      if(pos>3)dir=-1;
      if(pos<-3)dir=1;
      const el=a.querySelector(`#el_${uid}`);
      const er=a.querySelector(`#er_${uid}`);
      if(el)el.setAttribute('transform',`translate(${pos},0)`);
      if(er)er.setAttribute('transform',`translate(${pos},0)`);
    },30);
  } else {
    a.style.background='linear-gradient(135deg,var(--b500),var(--b900))';
    a.innerHTML='<svg viewBox="0 0 24 24" style="width:14px;height:14px;fill:#fff"><path d="M12 12c2.7 0 4-1.3 4-4s-1.3-4-4-4-4 1.3-4 4 1.3 4 4 4zm0 2c-2.7 0-8 1.35-8 4v2h16v-2c0-2.65-5.3-4-8-4z"/></svg>';
  }
  return a;
}

// ─── AÑADIR MENSAJE ───────────────────────────
async function rateConversation(logId, rating, likeBtn, dislikeBtn){
  if(!logId) return;
  try{
    await fetch(`/api/conversations/${encodeURIComponent(String(logId))}/rating`,{
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({rating}),
    });
    likeBtn?.classList.toggle('active-like', rating==='like');
    dislikeBtn?.classList.toggle('active-dislike', rating==='dislike');
  }catch(e){
    console.warn('No se pudo guardar rating:', e);
  }
}

function appendBotActions(body, conversationLogId){
  if(!conversationLogId) return;
  const acts=document.createElement('div');acts.className='msg-actions';

  const likeBtn=document.createElement('button');
  likeBtn.className='btn-rate';
  likeBtn.type='button';
  likeBtn.title='Me gustó esta respuesta';
  likeBtn.textContent='👍';

  const dislikeBtn=document.createElement('button');
  dislikeBtn.className='btn-rate';
  dislikeBtn.type='button';
  dislikeBtn.title='No me gustó esta respuesta';
  dislikeBtn.textContent='👎';

  likeBtn.onclick=()=>rateConversation(conversationLogId,'like',likeBtn,dislikeBtn);
  dislikeBtn.onclick=()=>rateConversation(conversationLogId,'dislike',likeBtn,dislikeBtn);

  acts.appendChild(likeBtn);
  acts.appendChild(dislikeBtn);
  body.appendChild(acts);
}

// ─── FORMATEAR TEXTO DEL BOT ──────────────────
// Convierte texto plano del LLM a HTML limpio.
// - Si ya viene con HTML del backend, lo usa directamente.
// - Colapsa \n simples en espacios (artefactos del tokenizer).
// - Convierte \n\n en separadores de párrafo.
// - Detecta listas inline (" - item. - item.") y las convierte a <ul>.
// - Detecta listas con \n por ítem y las convierte a <ul>.
function linkifyUrls(html){
  // Convierte URLs planas en <a> clickeables, evitando las que ya están dentro de href="..."
  return html.replace(
    /(?<![='"(>])(https?:\/\/[^\s<>"')\]]+)/g,
    url => {
      // Limpiar puntuación final que no forma parte de la URL
      const trail = url.match(/[.,;:!?)]+$/);
      const clean = trail ? url.slice(0, -trail[0].length) : url;
      const suffix = trail ? trail[0] : '';
      const display = clean.length > 50 ? clean.slice(0, 47) + '…' : clean;
      return `<a href="${clean}" target="_blank" rel="noopener noreferrer" style="color:var(--b500,#2255B8);text-decoration:underline;word-break:break-all">${display}</a>${suffix}`;
    }
  );
}

// Formato liviano para streaming: solo escapa HTML, saltos de línea y links.
// No intenta detectar listas para evitar saltos visuales mientras llegan tokens.
function formatStreamText(text){
  if(!text) return '';
  if(/<[a-z][\s\S]*>/i.test(text)) return linkifyUrls(text);
  let t = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  t = t.replace(/\r\n/g, '\n');
  t = t.replace(/\n{2,}/g, '<br><br>');
  t = t.replace(/\n/g, '<br>');
  return linkifyUrls(t.trim());
}

function formatBotText(text){
  if(!text) return '';
  // Si ya contiene etiquetas HTML del backend, linkificar y devolver directamente
  if(/<[a-z][\s\S]*>/i.test(text)) return linkifyUrls(text);

  // Escapar HTML
  let t = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  t = t.replace(/\r\n/g, '\n');

  // ── Detectar lista con \n por ítem ──────────────────────────────────
  // Patrón: líneas que empiezan con "- ", "* ", "• ", "N. " o "N) "
  const lineas = t.split('\n');
  const esItemLista = l => /^\s*[-*•]\s+\S/.test(l) || /^\s*\d+[.)]\s+\S/.test(l);
  const itemsConSalto = lineas.filter(l => l.trim()).filter(esItemLista);

  if(itemsConSalto.length >= 2){
    // Separar intro/cierre de los ítems
    const partes = [];
    let introLines = [], listaLines = [], cierreLines = [], enLista = false;
    for(const linea of lineas){
      if(!linea.trim()) continue;
      if(esItemLista(linea)){
        enLista = true;
        listaLines.push(linea.trim().replace(/^\s*[-*•\d.)]+\s*/, ''));
      } else if(enLista){
        cierreLines.push(linea.trim());
      } else {
        introLines.push(linea.trim());
      }
    }
    let html = '';
    if(introLines.length) html += `<p style="margin:0 0 6px 0">${linkifyUrls(introLines.join(' '))}</p>`;
    html += '<ul style="margin:4px 0 4px 0;padding-left:18px;line-height:1.7">';
    listaLines.forEach(item => { html += `<li>${linkifyUrls(item)}</li>`; });
    html += '</ul>';
    if(cierreLines.length) html += `<p style="margin:4px 0 0 0;color:#666;font-size:0.93em">${linkifyUrls(cierreLines.join(' '))}</p>`;
    return html;
  }

  // ── Detectar lista inline: "intro - item1 - item2 - cierre" ────────
  // Activa con 2+ ítems separados por " - " en una sola línea larga
  if(t.includes(' - ')){
    const partes = t.split(/\s+-\s+/);
    // Necesitamos al menos intro + 2 ítems
    if(partes.length >= 3){
      // El primer fragmento siempre es intro
      const intro = partes[0].trim();
      // El último puede ser cierre si no parece un ítem de lista
      // (los ítems de lista suelen ser cortos o empezar con mayúscula+sustantivo)
      const resto = partes.slice(1);
      // Detectar si el último fragmento es un párrafo de cierre
      // (más de 80 chars y no contiene ":" en los primeros 40 chars → es párrafo)
      let listaItems = resto;
      let cierre = '';
      const ultimo = resto[resto.length - 1];
      if(resto.length > 2 && ultimo.length > 80 && !/^[^:]{0,40}:/.test(ultimo)){
        listaItems = resto.slice(0, -1);
        cierre = ultimo;
      }
      let html = '';
      if(intro) html += `<p style="margin:0 0 6px 0">${linkifyUrls(intro)}</p>`;
      html += '<ul style="margin:4px 0 4px 0;padding-left:18px;line-height:1.7">';
      listaItems.forEach(item => {
        const colonIdx = item.indexOf(':');
        if(colonIdx > 0 && colonIdx < 50){
          const nombre = item.slice(0, colonIdx).trim();
          const desc = item.slice(colonIdx + 1).trim();
          html += `<li><strong>${nombre}</strong>${desc ? ': ' + linkifyUrls(desc) : ''}</li>`;
        } else {
          html += `<li>${linkifyUrls(item.trim())}</li>`;
        }
      });
      html += '</ul>';
      if(cierre) html += `<p style="margin:4px 0 0 0;color:#555;font-size:0.93em">${linkifyUrls(cierre)}</p>`;
      return html;
    }
  }

// ── Texto normal: preservar saltos de linea como <br> ──────────────
  // \n\n → párrafo nuevo. \n simple → salto de línea para listas.
  t = t.replace(/\n{2,}/g, '<br><br>');
  t = t.replace(/\n/g, '<br>');
  t = t.replace(/ {2,}/g, ' ');
  return linkifyUrls(t.trim());
}

function addMsg(text,type,bye=false,loc=null,noTranslate=false,conversationLogId=null){
  document.getElementById('welcomeCard')?.remove();
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');wrap.className=`msg ${type}`;

  if(loc&&loc.lat){
    // Tarjeta de sucursal
    const card=document.createElement('div');card.className='scard';
    card.innerHTML=`
      <div class="sc-head">
        <div class="sc-ico"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg></div>
        <div class="sc-htxt"><strong>${loc.nombre}</strong><span>Correos de Bolivia</span></div>
      </div>
      <div class="sc-body">
        <div class="sc-row"><svg viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg><span>${loc.direccion||'No disponible'}</span></div>
        <div class="sc-row"><svg viewBox="0 0 24 24"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg><span>${loc.telefono||'No disponible'}</span></div>
        ${loc.email?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg><span>${loc.email}</span></div>`:''}
        <div class="sc-sep"></div>
        <div class="sc-row"><svg viewBox="0 0 24 24"><path d="M12 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 12 2zm.5 5v6l5.25 3.15-.75 1.23L11 14V7h1.5z"/></svg><span>${loc.horario||'No disponible'}</span></div>
      </div>
      <a class="sc-cta" href="${loc.maps_url}" target="_blank" rel="noopener noreferrer">
        <svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
        Ver en Google Maps
      </a>`;
    wrap.appendChild(mkAv(type));wrap.appendChild(card);
  } else {
    // Burbuja de texto
    const b=document.createElement('div');b.className='bub'+(bye?' farewell':'');
    const formattedText = (type==='b') ? formatBotText(text) : text;
    if(type==='b'){
      b.innerHTML=formattedText;
    } else {
      b.textContent=formattedText;
    }
    // Guardar original para poder re-traducir en cambios de idioma
    b.dataset.original=text;
    const tm=document.createElement('span');tm.className='msg-time';tm.textContent=now();
    const body=document.createElement('div');
    body.style.cssText=`display:flex;flex-direction:column;align-items:${type==='u'?'flex-end':'flex-start'}`;
    body.appendChild(b);body.appendChild(tm);
    // Botón de traducción individual (solo para burbujas normales)
    if(!bye && !noTranslate){
      if(type==='b') appendBotActions(body, conversationLogId);
    }
    wrap.appendChild(mkAv(type));wrap.appendChild(body);
  }
  chat.appendChild(wrap);chat.scrollTop=chat.scrollHeight;
  if(!bye && !noTranslate && type==='b' && !loc){
    autoTranslateBubble(document.querySelector('#chat .msg.b:last-child .bub'), text);
  }
}

function createStreamingBotMessage(){
  document.getElementById('welcomeCard')?.remove();
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');wrap.className='msg b';
  const bubble=document.createElement('div');bubble.className='bub';bubble.textContent='';
  bubble.dataset.original='';
  const tm=document.createElement('span');tm.className='msg-time';tm.textContent=now();
  const body=document.createElement('div');
  body.style.cssText='display:flex;flex-direction:column;align-items:flex-start';
  body.appendChild(bubble);body.appendChild(tm);
  wrap.appendChild(mkAv('b'));wrap.appendChild(body);
  chat.appendChild(wrap);chat.scrollTop=chat.scrollHeight;
  return {wrap,body,bubble};
}

// ─── TRADUCIR MENSAJE INDIVIDUAL ─────────────
async function autoTranslateBubble(bubble, originalText){
  if(lang==='es' || !bubble || !originalText) return;
  if(bubble.classList.contains('no-translate') || bubble.closest('.qr-message')) return;
  try{
    const res=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({texts:[originalText],lang})});
    const data=await res.json();
    if(Array.isArray(data.translations)){
      const tr = data.translations[0];
      if(typeof tr==='string' && tr.trim()!==""){
        bubble.innerHTML = formatBotText(tr);
      }
    }
  }catch{}
}

async function translateMsg(bubble,btn,originalText){
  btn.classList.add('loading');btn.textContent=' ';
  try{
    const res=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({texts:[originalText],lang})});
    const data=await res.json();
    if(Array.isArray(data.translations)){
      const tr = data.translations[0];
      bubble.innerHTML = formatBotText((typeof tr==='string' && tr.trim()!="") ? tr : originalText);
      btn.textContent='↩ Original';btn.style.color='var(--y700)';
      btn.onclick=()=>{
        bubble.innerHTML=formatBotText(originalText);
      };
    }else{btn.textContent='🌐 Traducir';}
  }catch{btn.textContent='🌐 Traducir';}
  btn.classList.remove('loading');
}

// ─── TYPING ───────────────────────────────────
function showTyping(){
  document.getElementById('welcomeCard')?.remove();
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');wrap.className='msg b typing';wrap.id='tyEl';
  const b=document.createElement('div');b.className='bub';
  b.innerHTML=`<span class="t-lbl">${(TX[lang]||TX.es).lbl}</span><div class="dots"><div class="td"></div><div class="td"></div><div class="td"></div></div>`;
  wrap.appendChild(mkAv('b'));wrap.appendChild(b);
  chat.appendChild(wrap);chat.scrollTop=chat.scrollHeight;
}
function removeTyping(){document.getElementById('tyEl')?.remove();}

function clearQuickReplies(){
  document.querySelectorAll('.quick-replies').forEach(el=>el.remove());
}

function addQuickReplies(options){
  if(!Array.isArray(options)||options.length===0)return;
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');
  wrap.className='msg b quick-replies';
  const body=document.createElement('div');
  body.className='chips';
  body.style.marginLeft='35px';
  body.style.marginTop='2px';
  options.forEach(opt=>{
    if(!opt||!opt.value)return;
    const btn=document.createElement('button');
    btn.className='chip';
    btn.type='button';
    btn.textContent=opt.label||opt.value;
    btn.onclick=()=>sendMsg(opt.value);
    body.appendChild(btn);
  });
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop=chat.scrollHeight;
}


function addTrackingCard(trackingData){
  if(!trackingData||!trackingData.found) return;
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');
  wrap.className='msg b';

  const ev=trackingData.ultimo_evento||{};
  const estado=ev.nombre_evento||'Sin descripcion';
  const fecha=(ev.created_at||'—').replace('T',' ').substring(0,16);
  const servicio=ev.servicio||'—';
  const oficina=ev.office||ev.ciudad_origen||'—';
  const total=trackingData.total_eventos||0;
  const codigo=trackingData.codigo||'';
  const trackingUrl=trackingData.tracking_url||`https://trackingbo.correos.gob.bo:8100/?codigo=${codigo}`;

  const estadoLower=estado.toLowerCase();
  let estadoIcon='📦';
  if(estadoLower.includes('transit')||estadoLower.includes('proceso')){estadoIcon='🚚';}
  if(estadoLower.includes('entregad')){estadoIcon='✅';}
  if(estadoLower.includes('retenid')||estadoLower.includes('aduana')){estadoIcon='⚠️';}
  if(estadoLower.includes('devuelt')){estadoIcon='↩️';}

  // Flight radar timeline
  const eventos=Array.isArray(trackingData.eventos)?trackingData.eventos:[];
  let timelineHTML='';
  if(eventos.length>=2){
    const dots=eventos.slice(-4).map((e,i)=>{
      const isLast=i===Math.min(eventos.length,4)-1;
      const eName=(e.nombre_evento||'').toLowerCase();
      let dot='○',icon='⏳';
      if(eName.includes('entregad')){dot='●';icon='✅';}
      else if(eName.includes('transit')||eName.includes('proceso')){dot='●';icon='🚚';}
      else if(eName.includes('recibid')||eName.includes('registrad')){dot='●';icon='📍';}
      else{dot=isLast?'○':'●';}
      const ciudad=(e.office||e.ciudad_origen||e.ciudad_destino||'...').substring(0,4).toUpperCase();
      return{dot,icon,ciudad};
    });
    timelineHTML=`
      <div style="margin-top:10px;padding:10px;background:#f8f9fa;border-radius:10px;text-align:center">
        <div style="font-size:0.6rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px">Linea de tiempo</div>
        <div style="display:flex;align-items:center;justify-content:center;gap:0;margin-bottom:6px">
          ${dots.map(d=>`<span style="font-size:1.1rem;line-height:1;width:36px;text-align:center">${d.dot}</span>`).join('<span style="color:#ccc;width:20px;text-align:center">—</span>')}
        </div>
        <div style="display:flex;align-items:center;justify-content:center;gap:0;margin-bottom:4px">
          ${dots.map(d=>`<span style="font-size:0.55rem;color:#999;font-weight:600;letter-spacing:0.04em;width:36px;text-align:center">${d.ciudad}</span>`).join('<span style="width:20px"></span>')}
        </div>
        <div style="display:flex;align-items:center;justify-content:center;gap:0">
          ${dots.map(d=>`<span style="font-size:0.85rem;width:36px;text-align:center">${d.icon}</span>`).join('<span style="width:20px"></span>')}
        </div>
        <div style="margin-top:8px;font-size:0.6rem;color:#aaa">
          ${eventos.slice(-4).map(e=>(e.created_at||'').replace('T',' ').substring(11,16)).join(' → ')}
        </div>
      </div>`;
  }

  const cardEl=document.createElement('div');
  cardEl.className='scard no-translate';
  cardEl.innerHTML=`
    <div class="sc-head" style="background:linear-gradient(135deg,#163A80,#2255B8)">
      <div class="sc-ico"><svg viewBox="0 0 24 24"><path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg></div>
      <div class="sc-htxt"><strong>Estado del envio</strong><span style="font-family:monospace;letter-spacing:0.04em;font-size:0.7rem">${codigo}</span></div>
    </div>
    <div class="sc-body" style="gap:0;padding:12px 14px">
      <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;background:#FFF8E7;border-radius:10px;margin-bottom:10px;border-left:3px solid var(--y600,#E6A817)">
        <span style="font-size:1.3rem;line-height:1">${estadoIcon}</span>
        <div>
          <div style="font-size:0.62rem;color:#888;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:1px">Ultimo estado</div>
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
          <div style="font-size:0.75rem;font-weight:600;color:#1a1a1a">${total} registrado${total!==1?'s':''}</div>
        </div>
      </div>
      ${timelineHTML}
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
  chat.scrollTop=chat.scrollHeight;

  const qrEl=cardEl.querySelector('#qr-'+codigo.replace(/[^a-zA-Z0-9]/g,''));
  if(qrEl){
    try{
      new QRCode(qrEl,{text:trackingUrl,width:72,height:72,colorDark:'#163A80',colorLight:'#f8f9fa',correctLevel:QRCode.CorrectLevel.M});
    }catch(e){
      qrEl.style.display='none';
    }
  }
  chat.scrollTop=chat.scrollHeight;
}

let isLocating = false; // Flag para evitar llamadas múltiples

async function findNearestBranch(){
  if(isLocating) return;
  if(!navigator.geolocation){
    addMsg('❌ Tu navegador no soporta geolocalización.','b');
    return;
  }
  isLocating = true;
  addMsg('📍 Solicitando acceso a tu ubicación...','b');

  let position;
  try {
    position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0
      });
    });
  } catch(err) {
    isLocating = false;
    let msg = '❌ No se pudo obtener tu ubicación.';
    const s = ' Escribe "sucursales" para ver la lista completa.';
    if(err.code === 1) msg = '❌ Permiso de ubicación denegado.' + s;
    if(err.code === 2) msg = '❌ Ubicación no disponible en este momento.' + s;
    if(err.code === 3) msg = '❌ Tiempo de espera agotado. Intenta de nuevo.' + s;
    addMsg(msg,'b');
    return;
  }

  try{
    const lat = position.coords.latitude;
    const lng = position.coords.longitude;
    const res = await fetch('/api/sucursal/cercana',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({lat,lng,lang,sid})
    });
    const data = await res.json();
    if(data.ok && data.sucursal){
      addMsg(data.response,'b');
      addBranchMap(data.mi_ubicacion, data.sucursal);
      if(data.quick_replies) addQuickReplies(data.quick_replies);
    }else if(data.error === 'ubicacion_fuera_bolivia'){
      addMsg(data.response,'b');
    }else{
      addMsg('❌ No se pudo encontrar sucursal cercana. Escribe "sucursales" para ver la lista.','b');
    }
  }catch(e){
    addMsg('❌ Error consultando sucursal cercana.','b');
  } finally {
    isLocating = false;
  }
}

function addBranchesList(branches, intro=''){
  // Mostrar mensaje introductorio
  if(intro) addMsg(intro, 'b', false, null, true, null);
  
  const chat=document.getElementById('chat');
  branches.forEach((s,i)=>{
    const nombre =(s.nombre ||'').trim();
    const dir    =(s.direccion||'').trim();
    const tel    =(s.telefono||'').trim();
    const horario=(s.horario ||'').trim();
    const mapsUrl=s?.enlaces?.mapa||s?.enlaces?.busqueda||'';

    const wrap=document.createElement('div');
    wrap.className='msg b';

    const card=document.createElement('div');
    card.className='scard no-translate';
    card.style.marginBottom=i<branches.length-1?'8px':'0';
    card.innerHTML=`
      <div class="sc-head" style="background:linear-gradient(135deg,#163A80,#2255B8)">
        <div class="sc-ico">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="var(--y400)">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
          </svg>
        </div>
        <div class="sc-htxt"><strong>${nombre}</strong><span>Correos de Bolivia</span></div>
      </div>
      <div class="sc-body">
        ${dir?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg><span>${dir}</span></div>`:''}
        ${tel?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg><span>${tel}</span></div>`:''}
        ${horario?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M12 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 12 2zm.5 5v6l5.25 3.15-.75 1.23L11 14V7h1.5z"/></svg><span>${horario}</span></div>`:''}
      </div>
      ${mapsUrl?`<a class="sc-cta" href="${mapsUrl}" target="_blank" rel="noopener noreferrer">
        <svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>Ver en Google Maps</a>`:''}
    `;

    wrap.appendChild(mkAv('b'));
    wrap.appendChild(card);
    chat.appendChild(wrap);
  });
  chat.scrollTop=chat.scrollHeight;
}

// ─── TARJETA VISUAL DE TARIFA ─────────────────────────────────────────
function addTarifaCard(card){
  if(!card || !card.precio) return;
  document.getElementById('welcomeCard')?.remove();
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');
  wrap.className='msg b';

  const scopeLabel={
    'nacional':'EMS Nacional',
    'internacional':'EMS Internacional',
    'encomienda_nacional':'Encomienda Nacional',
    'encomienda_internacional':'Encomienda Internacional',
    'super_express_nacional':'Super Express Nacional',
    'ems_contratos_nacional':'EMS Contratos Nacional',
  }[card.scope]||(card.scope||'Servicio Postal');

  const cardEl=document.createElement('div');
  cardEl.className='scard no-translate';
  cardEl.innerHTML=`
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
      ${card.servicio?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M20 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg><span>Servicio: ${card.servicio}</span></div>`:''}
      ${card.peso_g?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M12 2a5 5 0 0 1 5 5H7a5 5 0 0 1 5-5zM3 9h18l-2 13H5L3 9z"/></svg><span>Peso: ${card.peso_g} g</span></div>`:''}
      ${card.rango_min&&card.rango_max?`<div class="sc-row"><svg viewBox="0 0 24 24"><path d="M3 3h18v18H3z" fill="none"/><path d="M8 12h8M12 8v8"/></svg><span>Rango: ${card.rango_min}–${card.rango_max} g</span></div>`:''}
    </div>
    <a class="sc-cta" href="https://correos.gob.bo" target="_blank" rel="noopener noreferrer">
      <svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      Ver más en correos.gob.bo
    </a>
  `;
  wrap.appendChild(mkAv('b'));
  wrap.appendChild(cardEl);
  chat.appendChild(wrap);
  chat.scrollTop=chat.scrollHeight;
}

function suggestBranch(nombre){
  const inp = document.getElementById('userInput');
  inp.value = nombre;
  sendMsg();
}

function addBranchMap(userLoc,sucursal){
  const chat=document.getElementById('chat');
  const wrap=document.createElement('div');
  wrap.className='msg b map-message';
  
  const body=document.createElement('div');
  body.className='bub';
  body.classList.add('no-translate');
  body.style.background='var(--white)';
  body.style.border='1px solid var(--border)';
  body.style.borderRadius='12px';
  body.style.padding='8px';
  body.style.width='100%';
  body.style.maxWidth='320px';
  
  // Título
  const title=document.createElement('div');
  title.textContent='🗺️ Sucursal más cercana';
  title.style.fontSize='0.75rem';
  title.style.fontWeight='600';
  title.style.color='var(--b700)';
  title.style.marginBottom='8px';
  title.style.textAlign='center';
  body.appendChild(title);
  
  // Contenedor del mapa
  const mapDiv=document.createElement('div');
  mapDiv.id='map-'+Date.now();
  mapDiv.style.height='200px';
  mapDiv.style.borderRadius='8px';
  mapDiv.style.overflow='hidden';
  body.appendChild(mapDiv);
  
  // Info de la sucursal
  const info=document.createElement('div');
  info.style.marginTop='8px';
  info.style.fontSize='0.7rem';
  info.style.color='var(--ink2)';
  info.innerHTML=`
    <strong>${sucursal.nombre||'Sucursal'}</strong><br>
      ${sucursal.direccion||'Dirección no disponible'}<br>
    📏 Distancia: ${sucursal.distancia_km||'?'} km<br>
    🕐 Horario: ${sucursal.horario||'Consultar'}
  `;
  body.appendChild(info);
  
  wrap.appendChild(mkAv('b'));
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop=chat.scrollHeight;
  
  // Inicializar mapa de Leaflet
  setTimeout(()=>{
    try{
      const map=L.map(mapDiv.id).setView([sucursal.lat,sucursal.lng],13);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
        attribution:'© OpenStreetMap'
      }).addTo(map);
      
      // Marcador de usuario (azul)
      const userIcon=L.divIcon({
        className:'user-marker',
        html:'<div style="background:#2255B8;width:12px;height:12px;border-radius:50%;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)"></div>',
        iconSize:[16,16]
      });
      L.marker([userLoc.lat,userLoc.lng],{icon:userIcon}).addTo(map).bindPopup('Tú');
      
      // Marcador de sucursal (rojo/dorado)
      const branchIcon=L.divIcon({
        className:'branch-marker',
        html:'<div style="background:#F5A623;width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)"></div>',
        iconSize:[20,20]
      });
      L.marker([sucursal.lat,sucursal.lng],{icon:branchIcon}).addTo(map).bindPopup(sucursal.nombre||'Sucursal');
      
      // Ajustar vista para ver ambos marcadores
      const bounds=L.latLngBounds([
        [userLoc.lat,userLoc.lng],
        [sucursal.lat,sucursal.lng]
      ]);
      map.fitBounds(bounds,{padding:[20,20]});
    }catch(e){
      console.error('Error mapa:',e);
      mapDiv.innerHTML='<div style="padding:20px;color:#999">🗺️ Mapa no disponible</div>';
    }
  },100);
}

function quickRepliesFromTarifa(data){
  const t=TX[lang]||TX.es;
  const missing = data && data.tarifa && Array.isArray(data.tarifa.missing) ? data.tarifa.missing : [];
  if(missing.includes('alcance')){
    return [
      {label:t.nacional,value:'nacional'},
      {label:t.internacional,value:'internacional'},
    ];
  }
  if(missing.includes('tipo_nacional')){
    return [
      {label:t.ems,value:'ems'},
      {label:t.prioritario,value:'encomienda'},
    ];
  }
  if(missing.includes('tipo_internacional')){
    return [
      {label:t.ems,value:'ems'},
      {label:t.encomiendas,value:'encomienda'},
    ];
  }
  return [];
}

// ─── WELCOME ──────────────────────────────────
async function loadWelcome(){
  await new Promise(r=>setTimeout(r,300));
  showTyping();
  await new Promise(r=>setTimeout(r,900));
  removeTyping();
  try{
    const d=await(await fetch(`/api/welcome?lang=${lang}`)).json();
    addMsg(d.response,'b',false,null,false);
  }catch{
    addMsg('Bienvenido al asistente oficial de Correos de Bolivia. ¿En qué puedo ayudarte?','b',false,null,false);
  }
}

// ─── ENVIAR MENSAJE ───────────────────────────
async function sendMsg(msg){
  if(busy||translating||!msg.trim())return;
  busy=true;
  localStorage.setItem('chat_sid_ts', Date.now().toString()); // actualizar timestamp
  clearQuickReplies();
  const inp=document.getElementById('input');
  inp.disabled=true;setStop(true);
  addMsg(msg,'u');showTyping();
  ctrl=new AbortController();
  currentRequestId=newRequestId();
  try{
    const res=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg,lang,sid,request_id:currentRequestId,tarifa_mode:tarifaMode,tracking_mode:trackingMode}),signal:ctrl.signal});
    if(!res.ok || !res.body) throw new Error('stream_failed');

    const reader=res.body.getReader();
    const decoder=new TextDecoder();
    let buffer='';
    let streamMsg=null;

    while(true){
      const {value,done}=await reader.read();
      if(done) break;
      buffer+=decoder.decode(value,{stream:true});
      const lines=buffer.split('\n');
      buffer=lines.pop()||'';

      for(const line of lines){
        if(!line.trim()) continue;
        const evt=JSON.parse(line);

        if(evt.type==='start'){
          if(evt.sid){
            sid=evt.sid;
            localStorage.setItem('chat_sid',sid);
          }
          continue;
        }

        if(evt.type==='token'){
          if(!streamMsg){
            removeTyping();
            streamMsg=createStreamingBotMessage();
            streamMsg._fullText='';
            // Inicializar con cursor parpadeante
            streamMsg.bubble.innerHTML='<span class="typing-cursor">|</span>';
          }
          
          // Acumular el texto completo
          streamMsg._fullText+=evt.content||'';
          
          // Durante el stream: formato liviano (sin detección de listas)
          const textToShow = formatStreamText(streamMsg._fullText);
          streamMsg.bubble.innerHTML = textToShow + '<span class="typing-cursor">|</span>';
          streamMsg.bubble.dataset.original = textToShow;
          
          // Auto-scroll suave
          const chat=document.getElementById('chat');
          chat.scrollTop=chat.scrollHeight;
          continue;
        }

        if(evt.type==='end'){
          const data=evt;
          if(data && data.sid){
            sid = data.sid;
            localStorage.setItem('chat_sid', sid);
          }
          removeTyping();
          const bye=data.despedida===true;

          if(streamMsg){
            const streamedText = streamMsg._fullText || streamMsg.bubble.textContent || '';
            const isBranchesList = data?.response_type === 'branches_list' && Array.isArray(data?.branches);
            if(isBranchesList){
              streamMsg.wrap.remove();
              streamMsg = null;
            }
            const finalText=formatBotText(data.response||streamedText||'Sin respuesta disponible');
            if(streamMsg){
              // Remover cursor y mostrar texto final
              streamMsg.bubble.innerHTML = finalText;
              streamMsg.bubble.dataset.original=finalText;
              if(!bye && !data.no_translate){
                appendBotActions(streamMsg.body, data.conversation_log_id||null);
                autoTranslateBubble(streamMsg.bubble, finalText);
              }
            }
          }else{
            addMsg(
              data.response||data.error||'Sin respuesta disponible',
              'b',
              bye,
              data.ubicacion||null,
              data.no_translate,
              data.conversation_log_id||null
            );
          }

          if(data?.tarifa?.requires_mode){
            tarifaMode=false;
            setTarifaModeUI();
          }
          // Mostrar tarjeta visual de tarifa si el backend la devuelve
          if(data?.tarifa_card && data.tarifa_card.precio){
            addTarifaCard(data.tarifa_card);
          }
          // Si hay tracking con URL, mostrar QR
          if(data?.tracking?.found){
            addTrackingCard(data.tracking);
          }
          // QR eliminado — el botón de la tarjeta lleva directo al link
          // Si es lista de sucursales, mostrar diseño mejorado
          if(data?.response_type === 'branches_list' && data?.branches){
            addBranchesList(data.branches, data.message||'');
          }
          addQuickReplies((Array.isArray(data.quick_replies)&&data.quick_replies.length>0)?data.quick_replies:quickRepliesFromTarifa(data));
          if(bye){
            inp.disabled=true;inp.placeholder=(TX[lang]||TX.es).bye;
            setStop(false);document.getElementById('send').disabled=true;return;
          }
        }
      }
    }
  }catch(e){
    removeTyping();
    addMsg(e.name==='AbortError'?'Consulta cancelada.':'Error de conexión. Verifique que el servidor esté activo.','b');
  }
  ctrl=null;currentRequestId='';busy=false;setStop(false);inp.disabled=false;inp.focus();
}

function suggest(btn){sendMsg(btn.textContent);}

// ─── LIMPIAR CONVERSACIÓN ─────────────────────
function clearConv(){document.getElementById('confirm-bar').classList.add('open');}
function closeConf(){document.getElementById('confirm-bar').classList.remove('open');}

async function doClear(){
  closeConf();
  try{
    const res = await fetch('/api/reset',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sid}),
    });
    const data = await res.json();
    if(data && data.sid){
      sid = data.sid;
      localStorage.setItem('chat_sid', sid);
    }
  }catch{}
  const chat=document.getElementById('chat');
  chat.innerHTML='';
  const t=TX[lang]||TX.es;
  const wc=document.createElement('div');wc.className='welcome';wc.id='welcomeCard';
  wc.innerHTML=`
    <div class="wc-icon"><svg viewBox="0 0 24 24"><path d="M20 4H4C2.9 4 2 4.9 2 6v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg></div>
    <div class="wc-title"> </div>
    <div class="wc-sub">Consulte sobre envíos, rastreo de paquetes, sucursales y servicios postales de Correos de Bolivia.</div>
    <div class="wc-sep"><div class="wc-sep-l"></div><div class="wc-sep-d"></div><div class="wc-sep-l"></div></div>
    <div class="chips" id="chips-container">
      ${t.chips.map(c=>`<button class="chip" onclick="suggest(this)">${c}</button>`).join('')}
    </div>`;
  chat.appendChild(wc);
  const inp=document.getElementById('input');
  inp.disabled=false;inp.placeholder=t.ph;
  document.getElementById('send').disabled=false;
  tarifaMode=false;setTarifaModeUI();
  trackingMode=false;setTrackingModeUI();
  busy=false;setStop(false);welcomeLoaded=true;loadWelcome();
}

// ─── FORM SUBMIT ──────────────────────────────
document.getElementById('form').addEventListener('submit',e=>{
  e.preventDefault();
  const inp=document.getElementById('input');
  const t=inp.value.trim();if(!t)return;
  inp.value='';sendMsg(t);
});

// ─── MAPA ─────────────────────────────────────
let mapInst=null;

async function openMap(){
  document.getElementById('mapa-modal').classList.add('open');
  if(mapInst){setTimeout(()=>mapInst.invalidateSize(),100);return;}
  let branches=[];
  try{branches=(await(await fetch('/api/sucursales')).json()).sucursales||[];}catch{}
  const center=branches.find(s=>s.lat)||{lat:-16.5,lng:-68.15};
  mapInst=L.map('mapa').setView([center.lat,center.lng],6);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {attribution:'© OpenStreetMap contributors'}).addTo(mapInst);
  const ico=L.divIcon({className:'',
    html:`<div style="width:32px;height:32px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:#F5A623;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(122,79,0,0.5);border:2px solid rgba(255,255,255,0.5)"><span style="transform:rotate(45deg);font-size:13px;line-height:1;color:#0B1F4E">✉</span></div>`,
    iconSize:[32,32],iconAnchor:[16,32],popupAnchor:[0,-36]});
  const list=document.getElementById('suc-list');list.innerHTML='';
  branches.forEach(s=>{
    if(!s.lat||!s.lng)return;
    const m=L.marker([s.lat,s.lng],{icon:ico}).addTo(mapInst)
      .bindPopup(`<div style="font-family:'DM Sans',sans-serif;font-size:12px;line-height:1.5;color:#1A0E00"><strong>${s.nombre}</strong><br> ${s.direccion||''}<br>🕐 ${s.horario||''}</div>`);
    const item=document.createElement('div');item.className='suc-item';
    item.innerHTML=`<div class="suc-ico"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg></div><div class="suc-nfo"><h4>${s.nombre}</h4><p>${s.direccion||'No disponible'}<br>${s.horario||'No disponible'}</p></div>`;
    item.onclick=()=>{mapInst.setView([s.lat,s.lng],16);m.openPopup();};
    list.appendChild(item);
  });
  setTimeout(()=>mapInst.invalidateSize(),100);
}
function closeMap(){document.getElementById('mapa-modal').classList.remove('open');}
document.getElementById('mapa-modal').addEventListener('click',e=>{if(e.target===e.currentTarget)closeMap();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMap();if(chatOpen)minimize();}});
setTarifaModeUI();
setTrackingModeUI();
