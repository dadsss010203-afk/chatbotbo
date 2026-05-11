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
  const trustedOrigin = baseUrl ? new URL(baseUrl, window.location.href).origin : '';
  const position = script?.dataset.position || 'right';
  const lang = script?.dataset.lang || 'es';
  const zIndex = script?.dataset.zIndex || '2147483000';
  const mobileFullscreen = script?.dataset.mobileFullscreen !== 'false';
  const mobileBreakpoint = Number(script?.dataset.mobileBreakpoint || 480);
  const closedSize = {
    width: Number(script?.dataset.closedWidth || 124),
    height: Number(script?.dataset.closedHeight || 124),
  };
  const openSize = {
    width: Number(script?.dataset.openWidth || 450),
    height: Number(script?.dataset.openHeight || 638),
  };

  if (!baseUrl) {
    console.error('[ChatbotBO] No se pudo determinar la URL base del widget.');
    return;
  }

  function ensureViewportMeta() {
    if (document.querySelector('meta[name="viewport"]')) return;
    const meta = document.createElement('meta');
    meta.name = 'viewport';
    meta.content = 'width=device-width, initial-scale=1, viewport-fit=cover';
    document.head?.appendChild(meta);
  }

  if (mobileFullscreen) ensureViewportMeta();

  function viewportSize() {
    const visual = window.visualViewport || {};
    const root = document.documentElement || {};
    const widths = [
      visual.width,
      window.innerWidth,
      root.clientWidth,
      window.outerWidth,
    ].filter((value) => Number.isFinite(value) && value > 0);
    const heights = [
      visual.height,
      window.innerHeight,
      root.clientHeight,
      window.outerHeight,
    ].filter((value) => Number.isFinite(value) && value > 0);
    return {
      width: Math.ceil(widths.length ? Math.min(...widths) : 360),
      height: Math.ceil(heights.length ? Math.min(...heights) : 640),
    };
  }

  function isCompactViewport() {
    const viewport = viewportSize();
    const ua = navigator.userAgent || "";
    const mobileUA = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua);
    const screenMin = Math.min(
      window.screen?.width || Number.POSITIVE_INFINITY,
      window.screen?.height || Number.POSITIVE_INFINITY
    );
    if (!mobileFullscreen) return false;
    return (
      viewport.width <= mobileBreakpoint ||
      (mobileUA && screenMin <= mobileBreakpoint)
    );
  }

  const frame = document.createElement('iframe');
  const iframeUrl = new URL('/widget.html', baseUrl);
  iframeUrl.searchParams.set('embed', '1');
  iframeUrl.searchParams.set('lang', lang);
  iframeUrl.searchParams.set('pos', position === 'left' ? 'left' : 'right');
  iframeUrl.searchParams.set('viewport', isCompactViewport() ? 'mobile' : 'desktop');

  frame.id = script?.dataset.frameId || 'chatbotbo-widget-frame';
  frame.title = script?.dataset.title || 'Asistente virtual Correos de Bolivia';
  frame.src = iframeUrl.toString();
  frame.allow = 'geolocation';
  frame.setAttribute('allowtransparency', 'true');
  frame.setAttribute('loading', 'eager');

  const sideProp = position === 'left' ? 'left' : 'right';
  const sideOffset = script?.dataset.sideOffset || '0px';
  const bottomOffset = script?.dataset.bottomOffset || '0px';
  let previousRootOverflow = '';
  let previousBodyOverflow = '';

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
    transition: 'none',
  });

  const oppositeSideProp = sideProp === 'left' ? 'right' : 'left';

  function fitSize(size) {
    return {
      width: Math.min(size.width, window.innerWidth),
      height: Math.min(size.height, window.innerHeight),
    };
  }

  function shouldUseFullscreen(isOpen) {
    return isOpen && isCompactViewport();
  }

  function setHostScrollLock(locked) {
    const root = document.documentElement;
    if (!root || !document.body) return;
    if (locked) {
      if (frame.dataset.scrollLocked !== '1') {
        previousRootOverflow = root.style.overflow;
        previousBodyOverflow = document.body.style.overflow;
      }
      root.style.overflow = 'hidden';
      document.body.style.overflow = 'hidden';
      frame.dataset.scrollLocked = '1';
      return;
    }
    if (frame.dataset.scrollLocked === '1') {
      root.style.overflow = previousRootOverflow;
      document.body.style.overflow = previousBodyOverflow;
      frame.dataset.scrollLocked = '0';
    }
  }

  function setFrameStyle(name, value, important = false) {
    frame.style.setProperty(name, value, important ? 'important' : '');
  }

  function notifyViewportMode() {
    const viewport = viewportSize();
    frame.contentWindow?.postMessage(
      {
        type: 'chatbotbo:viewport',
        mobile: isCompactViewport(),
        width: viewport.width,
        height: viewport.height,
      },
      trustedOrigin
    );
  }

  function setOpenState(isOpen) {
    frame.dataset.open = isOpen ? '1' : '0';
    notifyViewportMode();
    if (shouldUseFullscreen(isOpen)) {
      const viewport = viewportSize();
      const fullscreenWidth = `${viewport.width}px`;
      const fullscreenHeight = `${viewport.height}px`;
      setHostScrollLock(true);
      setFrameStyle('position', 'fixed', true);
      setFrameStyle('inset', '0', true);
      setFrameStyle('top', '0', true);
      setFrameStyle('left', '0', true);
      setFrameStyle('right', '0', true);
      setFrameStyle('bottom', '0', true);
      setFrameStyle('width', fullscreenWidth, true);
      setFrameStyle('min-width', fullscreenWidth, true);
      setFrameStyle('max-width', fullscreenWidth, true);
      setFrameStyle('inline-size', fullscreenWidth, true);
      setFrameStyle('height', fullscreenHeight, true);
      setFrameStyle('min-height', fullscreenHeight, true);
      setFrameStyle('max-height', fullscreenHeight, true);
      setFrameStyle('block-size', fullscreenHeight, true);
      setFrameStyle('margin', '0', true);
      setFrameStyle('border', '0', true);
      setFrameStyle('border-radius', '0', true);
      setFrameStyle('transform', 'none', true);
      setFrameStyle('overflow', 'hidden', true);
      setFrameStyle('display', 'block', true);
      setFrameStyle('z-index', String(zIndex), true);
      setFrameStyle('transition', 'none', true);
      return;
    }

    setHostScrollLock(false);
    const size = fitSize(isOpen ? openSize : closedSize);
    setFrameStyle('position', 'fixed');
    setFrameStyle('inset', 'auto');
    setFrameStyle('top', 'auto');
    setFrameStyle(sideProp, sideOffset);
    setFrameStyle(oppositeSideProp, 'auto');
    setFrameStyle('bottom', bottomOffset);
    setFrameStyle('width', `${size.width}px`);
    setFrameStyle('min-width', '');
    setFrameStyle('max-width', '');
    setFrameStyle('inline-size', '');
    setFrameStyle('height', `${size.height}px`);
    setFrameStyle('min-height', '');
    setFrameStyle('max-height', '');
    setFrameStyle('block-size', '');
    setFrameStyle('margin', '0');
    setFrameStyle('border', '0');
    setFrameStyle('border-radius', '');
    setFrameStyle('transform', '');
    setFrameStyle('overflow', 'hidden');
    setFrameStyle('display', 'block');
    setFrameStyle('z-index', String(zIndex));
    setFrameStyle('transition', 'none');
  }

  window.addEventListener('message', (event) => {
    if (event.origin !== trustedOrigin) return;
    const data = event.data || {};
    if (data.type === 'chatbotbo:state') {
      setOpenState(Boolean(data.open));
    }
  });

  window.addEventListener('resize', () => {
    const isOpen = frame.dataset.open === '1';
    setOpenState(isOpen);
  });

  window.addEventListener('orientationchange', () => {
    const isOpen = frame.dataset.open === '1';
    setTimeout(() => setOpenState(isOpen), 120);
  });

  window.visualViewport?.addEventListener('resize', () => {
    const isOpen = frame.dataset.open === '1';
    setOpenState(isOpen);
  });

  frame.addEventListener('load', notifyViewportMode);

  window.ChatbotBOEmbed = {
    loaded: true,
    frame,
    open() {
      frame.contentWindow?.postMessage({ type: 'chatbotbo:command', action: 'open' }, trustedOrigin);
      setOpenState(true);
    },
    close() {
      frame.contentWindow?.postMessage({ type: 'chatbotbo:command', action: 'close' }, trustedOrigin);
      setOpenState(false);
    },
  };

  window.addEventListener('message', (event) => {
    if (event.origin !== trustedOrigin) return;
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
