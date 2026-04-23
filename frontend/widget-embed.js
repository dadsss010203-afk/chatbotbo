/**
 * Widget Flotante Mejorado - ChatbotBO
 * Para sitios externos. Incluir en cualquier página:
 * 
 * <script src="https://tudominio.com/widget-embed.js"></script>
 * <script>
 *   ChatbotBOWidget.init({
 *     position: 'bottom-right',
 *     primaryColor: '#F5A623',
 *     greeting: '¡Hola! ¿En qué puedo ayudarte?'
 *   });
 * </script>
 */

(function() {
    'use strict';

    const CONFIG = {
        apiUrl: '',
        position: 'bottom-right',
        primaryColor: '#F5A623',
        secondaryColor: '#163A80',
        greeting: '¡Hola! Soy el asistente de Correos Bolivia. ¿En qué puedo ayudarte?',
        placeholder: 'Escribe tu mensaje...',
        title: 'Asistente Virtual',
        subtitle: 'Correos de Bolivia',
        logo: '<img src="/logo_chatbot.png" alt="Logo" style="width:32px;height:32px;object-fit:contain;border-radius:6px;">',
        autoOpen: false,
        autoOpenDelay: 5000,
        showBadge: true,
        draggable: true,
        soundEnabled: true,
        width: 380,
        height: 550
    };

    let widgetContainer = null;
    let chatWindow = null;
    let isOpen = false;
    let sessionId = null;
    let unreadCount = 0;
    let messageHistory = [];
    let currentRequestId = null;
    let ctrl = null;

    // Sonido de notificación
    const notificationSound = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBjGH0fPTgjMGHm7A7+OZSA0PVanu8LdnHAU1kNbxz4AzBhxqv+zplEYNDVGm5O+4ZSAEMY/P8ti+ZSAFNo/L8s2AMQYdcfDr4ZdJDQtPp+XysWUeBDeV1/LNfi0GI33R8tOENAcdcO/t4phJDQxPqOXyxWUeBDeZ1/PQfS4GI4DR8tKBNQYccPDs4plIDAtQp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApRp+TwxWUeBDea1/LQfS0GI4XR8tOENQYcb/Dr4plHDApQ==');

    function generateId() {
        return Math.random().toString(36).substring(2, 9);
    }

    function createStyles() {
        const styles = document.createElement('style');
        styles.textContent = `
            .cb-widget-container {
                position: fixed;
                ${CONFIG.position.includes('right') ? 'right: 20px;' : 'left: 20px;'}
                ${CONFIG.position.includes('bottom') ? 'bottom: 20px;' : 'top: 20px;'}
                z-index: 999999;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            .cb-bubble {
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: linear-gradient(135deg, ${CONFIG.primaryColor}, ${CONFIG.secondaryColor});
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 28px;
                transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
                position: relative;
                animation: cb-pulse 2s infinite;
            }
            
            @keyframes cb-pulse {
                0%, 100% { box-shadow: 0 4px 20px rgba(0,0,0,0.3), 0 0 0 0 rgba(245, 166, 35, 0.4); }
                50% { box-shadow: 0 4px 20px rgba(0,0,0,0.3), 0 0 0 10px rgba(245, 166, 35, 0); }
            }
            
            .cb-bubble:hover {
                transform: scale(1.1);
                animation: none;
            }
            
            .cb-badge {
                position: absolute;
                top: -2px;
                right: -2px;
                background: #e74c3c;
                color: white;
                border-radius: 50%;
                width: 22px;
                height: 22px;
                font-size: 12px;
                font-weight: bold;
                display: flex;
                align-items: center;
                justify-content: center;
                animation: cb-bounce 0.5s;
            }
            
            @keyframes cb-bounce {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.3); }
            }
            
            .cb-chat-window {
                position: absolute;
                ${CONFIG.position.includes('right') ? 'right: 0;' : 'left: 0;'}
                ${CONFIG.position.includes('bottom') ? 'bottom: 75px;' : 'top: 75px;'}
                width: ${CONFIG.width}px;
                height: ${CONFIG.height}px;
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                display: none;
                flex-direction: column;
                overflow: hidden;
                opacity: 0;
                transform: scale(0.9) translateY(20px);
                transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            }
            
            .cb-chat-window.open {
                display: flex;
                opacity: 1;
                transform: scale(1) translateY(0);
            }
            
            .cb-header {
                background: linear-gradient(135deg, ${CONFIG.primaryColor}, ${CONFIG.secondaryColor});
                color: white;
                padding: 16px;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .cb-header-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: rgba(255,255,255,0.2);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
            }
            
            .cb-header-info {
                flex: 1;
            }
            
            .cb-header-title {
                font-weight: 600;
                font-size: 15px;
            }
            
            .cb-header-subtitle {
                font-size: 12px;
                opacity: 0.9;
            }
            
            .cb-header-actions {
                display: flex;
                gap: 8px;
            }
            
            .cb-header-btn {
                width: 32px;
                height: 32px;
                border: none;
                background: rgba(255,255,255,0.2);
                color: white;
                border-radius: 8px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
            }
            
            .cb-header-btn:hover {
                background: rgba(255,255,255,0.3);
            }
            
            .cb-messages {
                flex: 1;
                overflow-y: auto;
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                background: #f8f9fa;
            }
            
            .cb-message {
                max-width: 85%;
                padding: 12px 16px;
                border-radius: 18px;
                font-size: 14px;
                line-height: 1.5;
                animation: cb-message-in 0.3s ease;
            }
            
            @keyframes cb-message-in {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
            }
            
            .cb-message.user {
                align-self: flex-end;
                background: ${CONFIG.primaryColor};
                color: #1a1a1a;
                border-bottom-right-radius: 4px;
            }
            
            .cb-message.bot {
                align-self: flex-start;
                background: white;
                color: #333;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            
            .cb-message.typing {
                background: white;
                padding: 16px 20px;
            }
            
            .cb-typing-dots {
                display: flex;
                gap: 4px;
            }
            
            .cb-typing-dots span {
                width: 8px;
                height: 8px;
                background: #999;
                border-radius: 50%;
                animation: cb-typing 1.4s infinite;
            }
            
            .cb-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
            .cb-typing-dots span:nth-child(3) { animation-delay: 0.4s; }
            
            @keyframes cb-typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-10px); }
            }
            
            .cb-input-area {
                padding: 12px 16px;
                background: white;
                border-top: 1px solid #eee;
                display: flex;
                gap: 8px;
            }
            
            .cb-input {
                flex: 1;
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 24px;
                font-size: 14px;
                outline: none;
                transition: border-color 0.2s;
            }
            
            .cb-input:focus {
                border-color: ${CONFIG.primaryColor};
            }
            
            .cb-send-btn {
                width: 44px;
                height: 44px;
                border: none;
                background: ${CONFIG.primaryColor};
                color: #1a1a1a;
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
            }
            
            .cb-send-btn:hover:not(:disabled) {
                transform: scale(1.05);
            }
            
            .cb-send-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .cb-quick-replies {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding: 8px 16px;
                background: white;
            }
            
            .cb-quick-reply {
                padding: 8px 16px;
                background: #f0f0f0;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .cb-quick-reply:hover {
                background: ${CONFIG.primaryColor};
                color: #1a1a1a;
            }
            
            .cb-timestamp {
                font-size: 11px;
                color: #999;
                margin-top: 4px;
                text-align: right;
            }
            
            .cb-escalate-btn {
                padding: 8px 16px;
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 12px;
                cursor: pointer;
                margin-top: 8px;
                transition: all 0.2s;
            }
            
            .cb-escalate-btn:hover {
                background: #c0392b;
            }
            
            /* Cursor parpadeante para efecto máquina de escribir */
            .cb-typing-cursor {
                display: inline-block;
                color: #163A80;
                font-weight: 300;
                animation: cbCursorBlink 0.8s ease-in-out infinite;
                margin-left: 2px;
            }
            
            @keyframes cbCursorBlink {
                0%, 100% { opacity: 1; }
                50% { opacity: 0; }
            }
        `;
        document.head.appendChild(styles);
    }

    function createWidget() {
        widgetContainer = document.createElement('div');
        widgetContainer.className = 'cb-widget-container';
        
        // Bubble
        const bubble = document.createElement('div');
        bubble.className = 'cb-bubble';
        bubble.innerHTML = CONFIG.logo;
        bubble.onclick = toggleChat;
        
        if (CONFIG.showBadge) {
            const badge = document.createElement('div');
            badge.className = 'cb-badge';
            badge.id = 'cb-badge';
            badge.style.display = 'none';
            badge.textContent = '0';
            bubble.appendChild(badge);
        }
        
        // Chat Window
        chatWindow = document.createElement('div');
        chatWindow.className = 'cb-chat-window';
        chatWindow.id = 'cb-chat-window';
        
        chatWindow.innerHTML = `
            <div class="cb-header">
                <div class="cb-header-avatar">${CONFIG.logo}</div>
                <div class="cb-header-info">
                    <div class="cb-header-title">${CONFIG.title}</div>
                    <div class="cb-header-subtitle">${CONFIG.subtitle}</div>
                </div>
                <div class="cb-header-actions">
                    <button class="cb-header-btn" onclick="ChatbotBOWidget.clearChat()" title="Nuevo chat">🗑️</button>
                    <button class="cb-header-btn" onclick="ChatbotBOWidget.toggleChat()" title="Cerrar">✕</button>
                </div>
            </div>
            <div class="cb-messages" id="cb-messages"></div>
            <div class="cb-quick-replies" id="cb-quick-replies"></div>
            <div class="cb-input-area">
                <input type="text" class="cb-input" id="cb-input" placeholder="${CONFIG.placeholder}" 
                    onkeypress="if(event.key==='Enter')ChatbotBOWidget.sendMessage()">
                <button class="cb-send-btn" id="cb-send-btn" onclick="ChatbotBOWidget.sendMessage()">
                    ➤
                </button>
            </div>
        `;
        
        widgetContainer.appendChild(chatWindow);
        widgetContainer.appendChild(bubble);
        document.body.appendChild(widgetContainer);
        
        // Load session
        sessionId = localStorage.getItem('cb_widget_sid') || generateId();
        localStorage.setItem('cb_widget_sid', sessionId);
    }

    function toggleChat() {
        isOpen = !isOpen;
        chatWindow.classList.toggle('open', isOpen);
        
        if (isOpen) {
            unreadCount = 0;
            updateBadge();
            document.getElementById('cb-input').focus();
            
            // Send greeting if first time
            const messages = document.getElementById('cb-messages');
            if (messages.children.length === 0) {
                addMessage(CONFIG.greeting, 'bot');
                loadQuickReplies();
            }
        }
    }

    function updateBadge() {
        const badge = document.getElementById('cb-badge');
        if (badge) {
            badge.textContent = unreadCount > 9 ? '9+' : unreadCount;
            badge.style.display = unreadCount > 0 ? 'flex' : 'none';
        }
    }

    function addMessage(text, type, timestamp = true) {
        const messages = document.getElementById('cb-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `cb-message ${type}`;
        
        let content = text;
        if (timestamp) {
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            content += `<div class="cb-timestamp">${time}</div>`;
        }
        
        messageDiv.innerHTML = content;
        messages.appendChild(messageDiv);
        messages.scrollTop = messages.scrollHeight;
        
        messageHistory.push({ type, text, time: new Date() });
    }

    function showTyping() {
        const messages = document.getElementById('cb-messages');
        const typingDiv = document.createElement('div');
        typingDiv.className = 'cb-message typing';
        typingDiv.id = 'cb-typing';
        typingDiv.innerHTML = `
            <div class="cb-typing-dots">
                <span></span><span></span><span></span>
            </div>
        `;
        messages.appendChild(typingDiv);
        messages.scrollTop = messages.scrollHeight;
    }

    function hideTyping() {
        const typing = document.getElementById('cb-typing');
        if (typing) typing.remove();
    }

    function loadQuickReplies() {
        const quickReplies = [
            '💰 Calcular tarifa',
            '  Sucursales cercanas',
            '📦 Rastrear paquete',
            '⏰ Horarios de atención'
        ];
        
        const container = document.getElementById('cb-quick-replies');
        container.innerHTML = quickReplies.map(text => 
            `<button class="cb-quick-reply" onclick="ChatbotBOWidget.sendQuickReply('${text}')">${text}</button>`
        ).join('');
    }

    async function sendMessage(text = null) {
        const input = document.getElementById('cb-input');
        const message = text || input.value.trim();
        if (!message) return;
        
        if (!text) input.value = '';
        
        addMessage(message, 'user');
        showTyping();
        
        document.getElementById('cb-send-btn').disabled = true;
        
        try {
            currentRequestId = generateId();
            ctrl = new AbortController();
            
            const res = await fetch(`${CONFIG.apiUrl || ''}/api/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    sid: sessionId,
                    request_id: currentRequestId
                }),
                signal: ctrl.signal
            });
            
            if (!res.ok || !res.body) throw new Error('stream_failed');
            
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let botMessage = null;
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                
                for (const line of lines) {
                    if (!line.trim()) continue;
                    
                    try {
                        const evt = JSON.parse(line);
                        
                        if (evt.type === 'token') {
                            if (!botMessage) {
                                hideTyping();
                                botMessage = document.createElement('div');
                                botMessage.className = 'cb-message bot';
                                botMessage._fullText = '';
                                document.getElementById('cb-messages').appendChild(botMessage);
                            }
                            // Acumular texto y mostrar directamente
                            botMessage._fullText += evt.content || '';
                            botMessage.textContent = botMessage._fullText;
                            botMessage.scrollIntoView({ behavior: 'smooth' });
                        }
                        
                        if (evt.type === 'end') {
                            hideTyping();
                            if (botMessage && evt.response) {
                                botMessage.textContent = evt.response;
                            }
                            
                            // Add escalate button if low confidence
                            if (evt.confidence && evt.confidence < 0.5) {
                                const escalateBtn = document.createElement('button');
                                escalateBtn.className = 'cb-escalate-btn';
                                escalateBtn.textContent = '🙋 Hablar con humano';
                                escalateBtn.onclick = () => escalateToHuman(message);
                                botMessage.appendChild(escalateBtn);
                            }
                            
                            if (evt.sid) {
                                sessionId = evt.sid;
                                localStorage.setItem('cb_widget_sid', sessionId);
                            }
                        }
                    } catch (e) {
                        console.error('Parse error:', e);
                    }
                }
            }
            
        } catch (err) {
            hideTyping();
            addMessage('❌ Lo siento, hubo un error. Por favor intenta nuevamente.', 'bot');
            console.error('Chat error:', err);
        }
        
        document.getElementById('cb-send-btn').disabled = false;
        
        // Sound notification if closed
        if (!isOpen && CONFIG.soundEnabled) {
            notificationSound.play().catch(() => {});
            unreadCount++;
            updateBadge();
        }
    }

    async function escalateToHuman(lastMessage) {
        try {
            const res = await fetch(`${CONFIG.apiUrl || ''}/api/escalate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: lastMessage,
                    reason: 'user_request',
                    sid: sessionId
                })
            });
            
            const data = await res.json();
            if (data.ok) {
                addMessage(data.response, 'bot');
            }
        } catch (err) {
            addMessage('❌ No se pudo enviar la solicitud. Intenta más tarde.', 'bot');
        }
    }

    function sendQuickReply(text) {
        sendMessage(text);
    }

    function clearChat() {
        document.getElementById('cb-messages').innerHTML = '';
        messageHistory = [];
        sessionId = generateId();
        localStorage.setItem('cb_widget_sid', sessionId);
        addMessage(CONFIG.greeting, 'bot');
        loadQuickReplies();
    }

    // Public API
    window.ChatbotBOWidget = {
        init: function(options = {}) {
            Object.assign(CONFIG, options);
            createStyles();
            createWidget();
            
            if (CONFIG.autoOpen) {
                setTimeout(() => toggleChat(), CONFIG.autoOpenDelay);
            }
        },
        
        toggleChat,
        sendMessage,
        sendQuickReply,
        clearChat,
        
        // Advanced methods
        open: () => { if (!isOpen) toggleChat(); },
        close: () => { if (isOpen) toggleChat(); },
        
        setApiUrl: (url) => { CONFIG.apiUrl = url; },
        
        // Event handlers
        onMessage: function(callback) {
            // TODO: Implement event system
        }
    };
})();
