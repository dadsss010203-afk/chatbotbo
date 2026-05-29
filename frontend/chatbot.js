     1|// ─── ESTADO ───────────────────────────────────
     2|let chatOpen=false, welcomeLoaded=false, busy=false, ctrl=null, lang='es';
     3|let translating=false; // flag para evitar traducciones simultáneas
     4|let tarifaMode=false;
     5|let trackingMode=false;
     6|let sid = localStorage.getItem('chat_sid') || '';
     7|let currentRequestId='';
     8|
     9|function newRequestId(){
    10|  if(window.crypto && typeof window.crypto.randomUUID==='function'){
    11|    return window.crypto.randomUUID();
    12|  }
    13|  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    14|}
    15|
    16|// ─── TEXTOS POR IDIOMA ────────────────────────
    17|const TX={
    18|  es:{
    19|    ph:'Escriba su consulta aquí…', lbl:'Analizando consulta…',
    20|    bye:'Conversación finalizada', translating:'Traduciendo conversación…',
    21|    welcome:'Hola, soy ChatbotBO, el asistente oficial de Correos de Bolivia. Puedo ayudarte con envíos, rastreo de paquetes, sucursales y más. ¿En qué puedo ayudarte?',
    22|    chips:['📦 Rastrear paquete','💰 Ver tarifas','📍 Sucursales','📋 Hacer reclamo','📮 Servicios','🕐 Horarios'],
    23|    tarifa:'Tarifas', tarifaCancel:'Cancelar tarifa',
    24|    tracking:'Rastreo', trackingCancel:'Cancelar rastreo',
    25|    nearby:'Sucursales',
    26|    enterHint:'Enter para enviar',
    27|    confirmText:'¿Borrar toda la conversación?',
    28|    cancelBtn:'Cancelar', confirmBtn:'Confirmar',
    29|    tarifaMode:'Modo tarifas activado. ¿Qué servicio quieres usar?',
    30|    trackingMode:'Modo rastreo activado. Envíame tu código de rastreo.',
    31|    tarifaCancelled:'Modo tarifas cancelado. Volviste al chat general.',
    32|    trackingCancelled:'Modo rastreo cancelado. Volviste al chat general.',
    33|    nacional:'Nacional', internacional:'Internacional',
    34|    ems:'Express Mail Service (EMS)', prioritario:'Prioritario',
    35|    encomiendas:'Encomiendas Postales'
    36|  },
    37|  en:{
    38|    ph:'Type your question here…', lbl:'Processing request…',
    39|    bye:'Conversation ended', translating:'Translating conversation…',
    40|    welcome:'Hello  I am chatboBo the virtual assistant of the Bolivian Postal Agency. I can help you with shipments, package tracking, branches and more. How can I help you?',
    41|    chips:['📦 Track package','💰 View rates','📍 Branches','📋 File complaint','📮 Services','🕐 Hours'],
    42|    tarifa:'Rates', tarifaCancel:'Cancel rates',
    43|    tracking:'Tracking', trackingCancel:'Cancel tracking',
    44|    nearby:'Branches',
    45|    enterHint:'Enter to send',
    46|    confirmText:'Delete entire conversation?',
    47|    cancelBtn:'Cancel', confirmBtn:'Confirm',
    48|    tarifaMode:'Rates mode activated. What service do you want to use?',
    49|    trackingMode:'Tracking mode activated. Send me your tracking code.',
    50|    tarifaCancelled:'Rates mode cancelled. Back to general chat.',
    51|    trackingCancelled:'Tracking mode cancelled. Back to general chat.',
    52|    nacional:'National', internacional:'International',
    53|    ems:'Express Mail Service (EMS)', prioritario:'Priority',
    54|    encomiendas:'Postal Parcels'
    55|  },
    56|  fr:{
    57|    ph:'Saisissez votre question…', lbl:'Traitement en cours…',
    58|    bye:'Conversation terminée', translating:'Traduction en cours…',
    59|    chips:[]
    60|  },
    61|  pt:{
    62|    ph:'Digite sua consulta aqui…', lbl:'Processando sua consulta…',
    63|    bye:'Conversa encerrada', translating:'Traduzindo conversa…',
    64|    chips:[]
    65|  },
    66|  zh:{
    67|    ph:'请在此输入您的问题…', lbl:'正在处理您的请求…',
    68|    bye:'对话已结束', translating:'正在翻译对话…',
    69|    chips:[]
    70|  },
    71|  ru:{
    72|    ph:'Введите ваш вопрос…', lbl:'Обработка запроса…',
    73|    bye:'Разговор завершён', translating:'Перевод разговора…',
    74|    chips:[]
    75|  },
    76|};
    77|
    78|// Nombres de idioma para el prompt de traducción
    79|const LANG_NAMES={es:'español',en:'inglés',fr:'francés',pt:'portugués',zh:'chino',ru:'ruso'};
    80|
    81|function toggleSucursalMenu(){
    82|  const menu = document.getElementById('sucursal-menu');
    83|  const isOpen = menu.style.display === 'block';
    84|  menu.style.display = isOpen ? 'none' : 'block';
    85|}
    86|
    87|function closeSucursalMenu(){
    88|  document.getElementById('sucursal-menu').style.display = 'none';
    89|}
    90|
    91|// Cerrar si el usuario hace clic fuera del menú
    92|document.addEventListener('click', function(e){
    93|  const menu = document.getElementById('sucursal-menu');
    94|  const btn = document.getElementById('nearby-toggle');
    95|  if(menu.style.display === 'block' && !menu.contains(e.target) && e.target !== btn){
    96|    menu.style.display = 'none';
    97|  }
    98|});
    99|
   100|// ─── IDIOMA ───────────────────────────────────
   101|function setLang(l){
   102|  if(translating) return; // no cambiar idioma mientras se traduce
   103|  lang=l;
   104|  document.querySelectorAll('.lpill').forEach(b=>b.classList.toggle('on',b.dataset.lang===l));
   105|  const t=TX[l]||TX.es;
   106|  document.getElementById('input').placeholder=t.ph;
   107|
   108|  // Actualizar botones y textos
   109|  const tarifaBtn=document.getElementById('tarifa-toggle');
   110|  const trackingBtn=document.getElementById('tracking-toggle');
   111|  const nearbyBtn=document.getElementById('nearby-toggle');
   112|  const fHint=document.querySelector('.f-hint');
   113|  const confirmText=document.querySelector('#confirm-bar p');
   114|  const cancelBtn=document.querySelector('.cno');
   115|  const confirmBtn=document.querySelector('.csi');
   116|
   117|  if(tarifaBtn){
   118|    tarifaBtn.textContent=tarifaMode?t.tarifaCancel:t.tarifa;
   119|  }
   120|  if(trackingBtn){
   121|    trackingBtn.textContent=trackingMode?t.trackingCancel:t.tracking;
   122|  }
   123|  if(nearbyBtn){
   124|    nearbyBtn.textContent=t.nearby;
   125|  }
   126|  if(fHint){
   127|    fHint.textContent=t.enterHint;
   128|  }
   129|  if(confirmText){
   130|    confirmText.innerHTML=t.confirmText;
   131|  }
   132|  if(cancelBtn){
   133|    cancelBtn.textContent=t.cancelBtn;
   134|  }
   135|  if(confirmBtn){
   136|    confirmBtn.textContent=t.confirmBtn;
   137|  }
   138|
   139|  // Actualizar chips si la tarjeta de bienvenida está visible
   140|  const cc=document.getElementById('chips-container');
   141|  if(cc) cc.innerHTML=t.chips.map(c=>`<button class="chip" onclick="suggest(this)">${c}</button>`).join('');
   142|
   143|  // Limpiar historial de sesión en el backend para que el LLM responda
   144|  // en el nuevo idioma sin estar influenciado por el historial anterior.
   145|  fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sid})}).catch(()=>{});
   146|
   147|  // Traducir toda la conversación automáticamente
   148|  translateConversation();
   149|}
   150|
   151|// ─── TRADUCIR TODA LA CONVERSACIÓN ───────────
   152|// ahora usamos la ruta /api/translate para traducir en lote y **no
   153|// necesitamos el modelo**; el servidor puede recurrir a librería local
   154|// o a LibreTranslate y la operación es mucho más rápida.
   155|async function translateConversation(){
   156|  // Solo burbujas de texto (no farewell, no tarjetas de sucursal)
   157|  const bubbles=Array.from(
   158|    document.querySelectorAll('.msg .bub:not(.farewell):not(.no-translate)')
   159|  ).filter(b=>!b.closest('.qr-message'));
   160|  if(bubbles.length===0) return;
   161|
   162|  translating=true;
   163|  const t=TX[lang]||TX.es;
   164|  const inp=document.getElementById('input');
   165|  const banner=document.getElementById('translate-banner');
   166|  const pills=document.querySelectorAll('.lpill');
   167|
   168|  // Bloquear UI durante traducción
   169|  inp.disabled=true;
   170|  pills.forEach(p=>p.disabled=true);
   171|  banner.textContent=`  ${t.translating}`;
   172|  banner.classList.add('vis');
   173|
   174|  // Animar burbujas con opacidad baja
   175|  bubbles.forEach(b=>b.classList.add('translating-anim'));
   176|
   177|  // Preparar array de textos originales
   178|  const originals = bubbles.map(b => {
   179|    const orig = b.dataset.original || b.textContent || '';
   180|    if(!b.dataset.original) b.dataset.original = orig;
   181|    return orig;
   182|  });
   183|
   184|  // para que el banner sea visible aunque la petición vuelva instantánea
   185|  const start = Date.now();
   186|  try{
   187|    const res = await fetch('/api/translate', {
   188|      method:'POST',
   189|      headers:{'Content-Type':'application/json'},
   190|      body: JSON.stringify({ texts: originals, lang })
   191|    });
   192|    const data = await res.json();
   193|    if(Array.isArray(data.translations)){
   194|      data.translations.forEach((tr, idx)=>{
   195|        if(bubbles[idx]){
   196|          // fallback a original si la traducción viene vacía
   197|          const out = (typeof tr==='string' && tr.trim()!=="" ) ? tr : originals[idx];
   198|          bubbles[idx].innerHTML = formatBotText(out);
   199|        }
   200|      });
   201|    }
   202|  }catch(e){
   203|    console.warn('Error traduciendo conversación:', e);
   204|    // si falla todo, no rompemos la UI; dejaremos los originales
   205|  }
   206|  // mantener banner visible mínimo 300ms
   207|  const elapsed = Date.now() - start;
   208|  if(elapsed < 300) await new Promise(r=>setTimeout(r, 300 - elapsed));
   209|
   210|  // Restaurar UI
   211|  bubbles.forEach(b=>b.classList.remove('translating-anim'));
   212|  banner.classList.remove('vis');
   213|  inp.disabled=false;
   214|  pills.forEach(p=>p.disabled=false);
   215|  translating=false;
   216|  if(!busy) inp.focus();
   217|}
   218|
   219|// ─── UI HELPERS ───────────────────────────────
   220|function setStop(v){document.getElementById('stop').classList.toggle('vis',v);document.getElementById('send').style.display=v?'none':'flex';}
   221|function stopResp(){
   222|  if(!ctrl) return;
   223|  fetch('/api/chat/cancel',{
   224|    method:'POST',
   225|    headers:{'Content-Type':'application/json'},
   226|    body:JSON.stringify({sid,request_id:currentRequestId}),
   227|  }).catch(()=>{});
   228|  ctrl.abort();
   229|  ctrl=null;
   230|  currentRequestId='';
   231|}
   232|function minimize(){
   233|  document.getElementById('chat-window').classList.remove('open');
   234|  document.getElementById('chat-bubble').style.display='flex';
   235|  chatOpen=false;
   236|}
   237|function now(){return new Date().toLocaleTimeString('es-BO',{hour:'2-digit',minute:'2-digit'});}
   238|function setTarifaModeUI(){
   239|  const btn=document.getElementById('tarifa-toggle');
   240|  if(!btn) return;
   241|  const t=TX[lang]||TX.es;
   242|  btn.classList.toggle('active', tarifaMode);
   243|  btn.textContent = tarifaMode ? t.tarifaCancel : t.tarifa;
   244|}
   245|
   246|function setTrackingModeUI(){
   247|  const btn=document.getElementById('tracking-toggle');
   248|  if(!btn) return;
   249|  const t=TX[lang]||TX.es;
   250|  btn.classList.toggle('active', trackingMode);
   251|  btn.textContent = trackingMode ? t.trackingCancel : t.tracking;
   252|}
   253|
   254|async function cancelTarifaMode(notify=true){
   255|  tarifaMode=false;
   256|  setTarifaModeUI();
   257|  try{
   258|    const res = await fetch('/api/tarifa/cancel',{
   259|      method:'POST',
   260|      headers:{'Content-Type':'application/json'},
   261|      body:JSON.stringify({sid}),
   262|    });
   263|    const data = await res.json();
   264|    if(data && data.sid){
   265|      sid = data.sid;
   266|      localStorage.setItem('chat_sid', sid);
   267|    }
   268|  }catch(e){
   269|    console.warn('No se pudo cancelar flujo tarifa:', e);
   270|  }
   271|  if(notify){
   272|    const t=TX[lang]||TX.es;
   273|    addMsg(t.tarifaCancelled,'b',false,null,true,null);
   274|  }
   275|}
   276|
   277|async function cancelTrackingMode(notify=true){
   278|  trackingMode=false;
   279|  setTrackingModeUI();
   280|  try{
   281|    const res = await fetch('/api/tracking/cancel',{
   282|      method:'POST',
   283|      headers:{'Content-Type':'application/json'},
   284|      body:JSON.stringify({sid}),
   285|    });
   286|    const data = await res.json();
   287|    if(data && data.sid){
   288|      sid = data.sid;
   289|      localStorage.setItem('chat_sid', sid);
   290|    }
   291|  }catch(e){
   292|    console.warn('No se pudo cancelar flujo tracking:', e);
   293|  }
   294|  if(notify){
   295|    const t=TX[lang]||TX.es;
   296|    addMsg(t.trackingCancelled,'b',false,null,true,null);
   297|  }
   298|}
   299|
   300|async function toggleTarifaMode(){
   301|  if(tarifaMode){
   302|    await cancelTarifaMode(true);
   303|    return;
   304|  }
   305|  if(trackingMode){
   306|    await cancelTrackingMode(false);
   307|  }
   308|  tarifaMode=true;
   309|  setTarifaModeUI();
   310|  const t=TX[lang]||TX.es;
   311|  try{
   312|    const res = await fetch('/api/tarifa/start',{
   313|      method:'POST',
   314|      headers:{'Content-Type':'application/json'},
   315|      body:JSON.stringify({sid,lang}),
   316|    });
   317|    const data = await res.json();
   318|    if(data && data.sid){
   319|      sid = data.sid;
   320|      localStorage.setItem('chat_sid', sid);
   321|    }
   322|    addMsg(data.response||t.tarifaMode,'b',false,null,true,data.conversation_log_id||null);
   323|    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
   324|  }catch(e){
   325|    addMsg(t.tarifaMode,'b',false,null,true,null);
   326|  }
   327|}
   328|
   329|async function toggleTrackingMode(){
   330|  if(trackingMode){
   331|    await cancelTrackingMode(true);
   332|    return;
   333|  }
   334|  if(tarifaMode){
   335|    await cancelTarifaMode(false);
   336|  }
   337|  trackingMode=true;
   338|  setTrackingModeUI();
   339|  const t=TX[lang]||TX.es;
   340|  try{
   341|    const res = await fetch('/api/tracking/start',{
   342|      method:'POST',
   343|      headers:{'Content-Type':'application/json'},
   344|      body:JSON.stringify({sid,lang}),
   345|    });
   346|    const data = await res.json();
   347|    if(data && data.sid){
   348|      sid = data.sid;
   349|      localStorage.setItem('chat_sid', sid);
   350|    }
   351|    addMsg(data.response||t.trackingMode,'b',false,null,true,data.conversation_log_id||null);
   352|    addQuickReplies(Array.isArray(data.quick_replies) ? data.quick_replies : []);
   353|  }catch(e){
   354|    addMsg(t.trackingMode,'b',false,null,true,null);
   355|  }
   356|}
   357|
   358|function toggleChat(){
   359|  chatOpen=!chatOpen;
   360|  document.getElementById('chat-window').classList.toggle('open',chatOpen);
   361|  const bubble=document.getElementById('chat-bubble');
   362|  const isMobile=window.innerWidth<=480;
   363|  if(chatOpen){
   364|    document.getElementById('badge').style.display='none';
   365|    if(isMobile) bubble.style.display='none';
   366|    if(!welcomeLoaded){welcomeLoaded=true;loadWelcome();}
   367|    setTimeout(()=>document.getElementById('input').focus(),420);
   368|  } else {
   369|    bubble.style.display='flex';
   370|  }
   371|}
   372|
   373|// ─── AVATARES ─────────────────────────────────
   374|function mkAv(t){
   375|  const a=document.createElement('div');a.className='av';
   376|  if(t==='b'){
   377|    a.style.cssText='background:linear-gradient(145deg,#FFC145,#C8860E);border-radius:50%;display:flex;align-items:center;justify-content:center;width:44px;height:44px;flex-shrink:0;box-shadow:0 0 0 3px rgba(200,134,14,0.4),0 4px 12px rgba(122,79,0,0.5);';
   378|    const uid='e'+Math.random().toString(36).slice(2,7);
   379|    a.innerHTML=`<svg viewBox="0 0 44 44" width="44" height="44" xmlns="http://www.w3.org/2000/svg">
   380|      <circle cx="22" cy="22" r="18" fill="white"/>
   381|      <g id="el_${uid}">
   382|        <ellipse cx="14" cy="20" rx="6.5" ry="5" fill="#1A0E00"/>
   383|        <ellipse cx="16" cy="17.5" rx="1.8" ry="1.3" fill="white"/>
   384|      </g>
   385|      <g id="er_${uid}">
   386|        <ellipse cx="30" cy="20" rx="6.5" ry="5" fill="#1A0E00"/>
   387|        <ellipse cx="32" cy="17.5" rx="1.8" ry="1.3" fill="white"/>
   388|      </g>
   389|    </svg>`;
   390|    let dir=1,pos=0;
   391|    setInterval(()=>{
   392|      pos+=dir*0.12;
   393|      if(pos>3)dir=-1;
   394|      if(pos<-3)dir=1;
   395|      const el=a.querySelector(`#el_${uid}`);
   396|      const er=a.querySelector(`#er_${uid}`);
   397|      if(el)el.setAttribute('transform',`translate(${pos},0)`);
   398|      if(er)er.setAttribute('transform',`translate(${pos},0)`);
   399|    },30);
   400|  } else {
   401|    a.style.background='linear-gradient(135deg,var(--b500),var(--b900))';
   402|    a.innerHTML='<svg viewBox="0 0 24 24" style="width:14px;height:14px;fill:#fff"><path d="M12 12c2.7 0 4-1.3 4-4s-1.3-4-4-4-4 1.3-4 4 1.3 4 4 4zm0 2c-2.7 0-8 1.35-8 4v2h16v-2c0-2.65-5.3-4-8-4z"/></svg>';
   403|  }
   404|  return a;
   405|}
   406|
   407|// ─── AÑADIR MENSAJE ───────────────────────────
   408|async function rateConversation(logId, rating, likeBtn, dislikeBtn){
   409|  if(!logId) return;
   410|  try{
   411|    await fetch(`/api/conversations/${encodeURIComponent(String(logId))}/rating`,{
   412|      method:'PUT',
   413|      headers:{'Content-Type':'application/json'},
   414|      body:JSON.stringify({rating}),
   415|    });
   416|    likeBtn?.classList.toggle('active-like', rating==='like');
   417|    dislikeBtn?.classList.toggle('active-dislike', rating==='dislike');
   418|  }catch(e){
   419|    console.warn('No se pudo guardar rating:', e);
   420|  }
   421|}
   422|
   423|function appendBotActions(body, conversationLogId){
   424|  if(!conversationLogId) return;
   425|  const acts=document.createElement('div');acts.className='msg-actions';
   426|
   427|  const likeBtn=document.createElement('button');
   428|  likeBtn.className='btn-rate';
   429|  likeBtn.type='button';
   430|  likeBtn.title='Me gustó esta respuesta';
   431|  likeBtn.textContent='👍';
   432|
   433|  const dislikeBtn=document.createElement('button');
   434|  dislikeBtn.className='btn-rate';
   435|  dislikeBtn.type='button';
   436|  dislikeBtn.title='No me gustó esta respuesta';
   437|  dislikeBtn.textContent='👎';
   438|
   439|  likeBtn.onclick=()=>rateConversation(conversationLogId,'like',likeBtn,dislikeBtn);
   440|  dislikeBtn.onclick=()=>rateConversation(conversationLogId,'dislike',likeBtn,dislikeBtn);
   441|
   442|  acts.appendChild(likeBtn);
   443|  acts.appendChild(dislikeBtn);
   444|  body.appendChild(acts);
   445|}
   446|
   447|// ─── FORMATEAR TEXTO DEL BOT ──────────────────
   448|// Convierte texto plano del LLM a HTML limpio.
   449|// - Si ya viene con HTML del backend, lo usa directamente.
   450|// - Colapsa \n simples en espacios (artefactos del tokenizer).
   451|// - Convierte \n\n en separadores de párrafo.
   452|// - Detecta listas inline (" - item. - item.") y las convierte a <ul>.
   453|// - Detecta listas con \n por ítem y las convierte a <ul>.
   454|function linkifyUrls(html){
   455|  // Convierte URLs planas en <a> clickeables, evitando las que ya están dentro de href="..."
   456|  return html.replace(
   457|    /(?<![='"(>])(https?:\/\/[^\s<>"')\]]+)/g,
   458|    url => {
   459|      // Limpiar puntuación final que no forma parte de la URL
   460|      const trail = url.match(/[.,;:!?)]+$/);
   461|      const clean = trail ? url.slice(0, -trail[0].length) : url;
   462|      const suffix = trail ? trail[0] : '';
   463|      const display = clean.length > 50 ? clean.slice(0, 47) + '…' : clean;
   464|      return `<a href="${clean}" target="_blank" rel="noopener noreferrer" style="color:var(--b500,#2255B8);text-decoration:underline;word-break:break-all">${display}</a>${suffix}`;
   465|    }
   466|  );
   467|}
   468|
   469|// Formato liviano para streaming: solo escapa HTML, saltos de línea y links.
   470|// No intenta detectar listas para evitar saltos visuales mientras llegan tokens.
   471|function formatStreamText(text){
   472|  if(!text) return '';
   473|  if(/<[a-z][\s\S]*>/i.test(text)) return linkifyUrls(text);
   474|  let t = text
   475|    .replace(/&/g, '&amp;')
   476|    .replace(/</g, '&lt;')
   477|    .replace(/>/g, '&gt;');
   478|  t = t.replace(/\r\n/g, '\n');
   479|  t = t.replace(/\n{2,}/g, '<br><br>');
   480|  t = t.replace(/\n/g, '<br>');
   481|  return linkifyUrls(t.trim());
   482|}
   483|
   484|function formatBotText(text){
   485|  if(!text) return '';
   486|  // Si ya contiene etiquetas HTML del backend, linkificar y devolver directamente
   487|  if(/<[a-z][\s\S]*>/i.test(text)) return linkifyUrls(text);
   488|
   489|  // Escapar HTML
   490|  let t = text
   491|    .replace(/&/g, '&amp;')
   492|    .replace(/</g, '&lt;')
   493|    .replace(/>/g, '&gt;');
   494|
   495|  t = t.replace(/\r\n/g, '\n');
   496|
   497|  // ── Detectar lista con \n por ítem ──────────────────────────────────
   498|  // Patrón: líneas que empiezan con "- ", "* ", "• ", "N. " o "N) "
   499|  const lineas = t.split('\n');
   500|  const esItemLista = l => /^\s*[-*•]\s+\S/.test(l) || /^\s*\d+[.)]\s+\S/.test(l);
   501|