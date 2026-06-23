/**
 * ChatbotBO embed loader.
 *
 * Instalacion en una pagina externa:
 * <script src="https://tu-dominio.com/widget-embed.js" defer></script>
 */
(function () {
  'use strict';

  if (window.ChatbotBOEmbed && window.ChatbotBOEmbed.loaded) return;

  const script =
    document.currentScript ||
    Array.from(document.getElementsByTagName('script')).find((s) =>
      (s.src || '').includes('widget-embed.js')
    );

  const scriptUrl = script && script.src ? new URL(script.src, window.location.href) : null;
  const baseUrl = (script?.dataset.baseUrl || (scriptUrl ? scriptUrl.origin : '')).replace(/\/+$/, '');
  const position = script?.dataset.position || 'right';
  const lang = script?.dataset.lang || 'es';
  const zIndex = script?.dataset.zIndex || '2147483000';
  const closedSize = {
    width: Number(script?.dataset.closedWidth || 124),
    height: Number(script?.dataset.closedHeight || 124),
  };
  const openSize = {
    width: Number(script?.dataset.openWidth || 520),
    height: Number(script?.dataset.openHeight || 760),
  };

  if (!baseUrl) {
    console.error('[ChatbotBO] No se pudo determinar la URL base del widget.');
    return;
  }

  const frame = document.createElement('iframe');
  const iframeUrl = new URL('/widget.html', baseUrl);
  iframeUrl.searchParams.set('embed', '1');
  iframeUrl.searchParams.set('lang', lang);
  iframeUrl.searchParams.set('pos', position === 'left' ? 'left' : 'right');

  frame.id = script?.dataset.frameId || 'chatbotbo-widget-frame';
  frame.title = script?.dataset.title || 'Asistente virtual Correos de Bolivia';
  frame.src = iframeUrl.toString();
  frame.allow = 'geolocation';
  frame.setAttribute('allowtransparency', 'true');
  frame.setAttribute('loading', 'eager');

  const sideProp = position === 'left' ? 'left' : 'right';
  const sideOffset = script?.dataset.sideOffset || '0px';
  const bottomOffset = script?.dataset.bottomOffset || '0px';

  Object.assign(frame.style, {
    position: 'fixed',
    [sideProp]: sideOffset,
    bottom: bottomOffset,
    width: `${closedSize.width}px`,
    height: `${closedSize.height}px`,
    border: '0',
    margin: '0',
    padding: '0',
    display: 'block',
    overflow: 'hidden',
    background: 'transparent',
    colorScheme: 'normal',
    zIndex: String(zIndex),
  });

  function fitSize(size) {
    return {
      width: Math.min(size.width, window.innerWidth),
      height: Math.min(size.height, window.innerHeight),
    };
  }

  function setOpenState(isOpen) {
    const size = fitSize(isOpen ? openSize : closedSize);
    frame.style.width = `${size.width}px`;
    frame.style.height = `${size.height}px`;
  }

  window.addEventListener('message', (event) => {
    if (event.origin !== baseUrl) return;
    const data = event.data || {};
    if (data.type === 'chatbotbo:state') {
      setOpenState(Boolean(data.open));
    }
  });

  window.addEventListener('resize', () => {
    const isOpen = frame.dataset.open === '1';
    setOpenState(isOpen);
  });

  window.ChatbotBOEmbed = {
    loaded: true,
    frame,
    open() {
      frame.contentWindow?.postMessage({ type: 'chatbotbo:command', action: 'open' }, baseUrl);
      frame.dataset.open = '1';
      setOpenState(true);
    },
    close() {
      frame.contentWindow?.postMessage({ type: 'chatbotbo:command', action: 'close' }, baseUrl);
      frame.dataset.open = '0';
      setOpenState(false);
    },
  };

  window.addEventListener('message', (event) => {
    if (event.origin !== baseUrl) return;
    if (event.data?.type === 'chatbotbo:state') {
      frame.dataset.open = event.data.open ? '1' : '0';
    }
  });

  if (document.body) {
    document.body.appendChild(frame);
  } else {
    document.addEventListener('DOMContentLoaded', () => document.body.appendChild(frame), { once: true });
  }
})();
