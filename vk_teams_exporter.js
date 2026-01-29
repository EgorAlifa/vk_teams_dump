/**
 * VK Teams Chat Exporter
 *
 * Использование:
 * 1. Открой нужный чат в VK Teams (веб-версия)
 * 2. Открой DevTools (F12) -> Console
 * 3. Скопируй и вставь этот скрипт
 * 4. Запусти: await exportChat()
 *
 * Опции:
 * - exportChat() - экспорт текущего чата
 * - exportChat({ format: 'html' }) - экспорт в HTML
 * - exportChat({ maxMessages: 1000 }) - ограничить количество
 */

(function() {
    'use strict';

    const CONFIG = {
        messagesPerRequest: 50,
        delayBetweenRequests: 300, // мс, чтобы не забанили
        maxMessages: Infinity,
        format: 'json' // 'json' или 'html'
    };

    // Получаем текущий chat ID из URL или состояния приложения
    function getCurrentChatId() {
        // Попробуем из URL
        const urlMatch = window.location.hash.match(/[?&]chatId=([^&]+)/);
        if (urlMatch) return urlMatch[1];

        // Попробуем из URL path
        const pathMatch = window.location.pathname.match(/\/([^\/]+)$/);
        if (pathMatch && pathMatch[1].includes('@')) return pathMatch[1];

        // Попробуем найти в Redux store или глобальном состоянии
        if (window.__REDUX_DEVTOOLS_EXTENSION__) {
            console.log('Попробуй найти chatId в Redux DevTools');
        }

        // Попробуем из активного элемента в DOM
        const activeChat = document.querySelector('[data-chat-id]');
        if (activeChat) return activeChat.dataset.chatId;

        // Последний вариант - спросить пользователя
        return prompt('Не удалось определить ID чата автоматически.\nВведи ID чата (можно найти в Network tab при загрузке чата):');
    }

    // Получаем aimsid для авторизации запросов
    function getAimsid() {
        // Ищем в cookies
        const cookies = document.cookie.split(';').reduce((acc, c) => {
            const [key, val] = c.trim().split('=');
            acc[key] = val;
            return acc;
        }, {});

        if (cookies.aimsid) return cookies.aimsid;

        // Ищем в localStorage
        const stored = localStorage.getItem('aimsid');
        if (stored) return stored;

        // Ищем в sessionStorage
        const session = sessionStorage.getItem('aimsid');
        if (session) return session;

        return null;
    }

    // Базовый URL API
    function getApiBase() {
        return window.location.origin + '/api/v139/rapi';
    }

    // Запрос истории чата
    async function fetchHistory(sn, fromMsgId = null, count = CONFIG.messagesPerRequest) {
        const params = new URLSearchParams({
            sn: sn,
            count: count,
            patchVersion: '1',
            lang: 'ru'
        });

        if (fromMsgId) {
            params.append('fromMsgId', fromMsgId);
        }

        const aimsid = getAimsid();
        if (aimsid) {
            params.append('aimsid', aimsid);
        }

        const url = `${getApiBase()}/getHistory?${params}`;

        const response = await fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: {
                'Accept': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return response.json();
    }

    // Получаем информацию о чате
    async function fetchChatInfo(sn) {
        const params = new URLSearchParams({
            sn: sn,
            lang: 'ru'
        });

        const aimsid = getAimsid();
        if (aimsid) {
            params.append('aimsid', aimsid);
        }

        try {
            const url = `${getApiBase()}/getChatInfo?${params}`;
            const response = await fetch(url, {
                method: 'GET',
                credentials: 'include'
            });
            return response.json();
        } catch (e) {
            return null;
        }
    }

    // Основная функция экспорта
    async function exportChat(options = {}) {
        const config = { ...CONFIG, ...options };

        console.log('🚀 VK Teams Exporter запущен');

        const chatId = options.chatId || getCurrentChatId();
        if (!chatId) {
            console.error('❌ Не удалось определить ID чата');
            return null;
        }

        console.log(`📱 Экспорт чата: ${chatId}`);

        // Получаем инфо о чате
        const chatInfo = await fetchChatInfo(chatId);
        console.log('📋 Информация о чате:', chatInfo);

        const allMessages = [];
        let fromMsgId = null;
        let hasMore = true;
        let requestCount = 0;

        while (hasMore && allMessages.length < config.maxMessages) {
            requestCount++;
            console.log(`📥 Запрос #${requestCount}, загружено сообщений: ${allMessages.length}`);

            try {
                const data = await fetchHistory(chatId, fromMsgId, config.messagesPerRequest);

                if (!data.results || !data.results.messages) {
                    console.log('⚠️ Нет данных в ответе:', data);
                    break;
                }

                const messages = data.results.messages;

                if (messages.length === 0) {
                    hasMore = false;
                    console.log('✅ Достигнуто начало истории');
                    break;
                }

                allMessages.push(...messages);

                // Находим самый старый msgId для следующего запроса
                const oldestMsg = messages[messages.length - 1];
                fromMsgId = oldestMsg.msgId;

                // Проверяем, есть ли ещё сообщения
                if (messages.length < config.messagesPerRequest) {
                    hasMore = false;
                    console.log('✅ Загружены все сообщения');
                }

                // Пауза между запросами
                await new Promise(r => setTimeout(r, config.delayBetweenRequests));

            } catch (error) {
                console.error('❌ Ошибка при загрузке:', error);
                break;
            }
        }

        // Сортируем по времени (старые первые)
        allMessages.sort((a, b) => a.time - b.time);

        console.log(`\n✅ Экспорт завершён!`);
        console.log(`📊 Всего сообщений: ${allMessages.length}`);

        const exportData = {
            exportDate: new Date().toISOString(),
            chatId: chatId,
            chatInfo: chatInfo?.results || null,
            totalMessages: allMessages.length,
            messages: allMessages
        };

        // Сохраняем файл
        if (config.format === 'html') {
            downloadAsHtml(exportData);
        } else {
            downloadAsJson(exportData);
        }

        return exportData;
    }

    // Скачивание JSON
    function downloadAsJson(data) {
        const json = JSON.stringify(data, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const chatName = data.chatInfo?.name || data.chatId;
        const safeName = chatName.replace(/[^a-zA-Zа-яА-Я0-9]/g, '_');
        const filename = `vkteams_${safeName}_${new Date().toISOString().slice(0,10)}.json`;

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();

        URL.revokeObjectURL(url);
        console.log(`💾 Сохранено: ${filename}`);
    }

    // Скачивание HTML
    function downloadAsHtml(data) {
        const chatName = data.chatInfo?.name || data.chatId;

        const html = `<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Чат: ${escapeHtml(chatName)}</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 { color: #333; border-bottom: 2px solid #0077ff; padding-bottom: 10px; }
        .meta { color: #666; margin-bottom: 20px; font-size: 14px; }
        .message {
            background: white;
            padding: 12px 16px;
            margin: 8px 0;
            border-radius: 12px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        .message.outgoing {
            background: #e3f2fd;
            margin-left: 40px;
        }
        .sender {
            font-weight: 600;
            color: #0077ff;
            margin-bottom: 4px;
        }
        .time {
            font-size: 11px;
            color: #999;
            float: right;
        }
        .text {
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.4;
        }
        .file {
            background: #f0f0f0;
            padding: 8px 12px;
            border-radius: 8px;
            margin-top: 8px;
            font-size: 13px;
        }
        .file a { color: #0077ff; text-decoration: none; }
        .file a:hover { text-decoration: underline; }
        .sticker { max-width: 150px; }
        .reply {
            border-left: 3px solid #0077ff;
            padding-left: 10px;
            margin-bottom: 8px;
            font-size: 13px;
            color: #666;
        }
        .search {
            position: sticky;
            top: 0;
            background: #f5f5f5;
            padding: 10px 0;
            margin-bottom: 10px;
        }
        .search input {
            width: 100%;
            padding: 10px 15px;
            border: 1px solid #ddd;
            border-radius: 20px;
            font-size: 14px;
        }
        .hidden { display: none; }
    </style>
</head>
<body>
    <h1>💬 ${escapeHtml(chatName)}</h1>
    <div class="meta">
        <p>📅 Экспорт: ${data.exportDate}</p>
        <p>📊 Сообщений: ${data.totalMessages}</p>
    </div>

    <div class="search">
        <input type="text" id="searchInput" placeholder="🔍 Поиск по сообщениям..." oninput="filterMessages(this.value)">
    </div>

    <div id="messages">
        ${data.messages.map(msg => renderMessage(msg)).join('\n')}
    </div>

    <script>
        function filterMessages(query) {
            const q = query.toLowerCase();
            document.querySelectorAll('.message').forEach(el => {
                const text = el.textContent.toLowerCase();
                el.classList.toggle('hidden', q && !text.includes(q));
            });
        }
    </script>
</body>
</html>`;

        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);

        const safeName = chatName.replace(/[^a-zA-Zа-яА-Я0-9]/g, '_');
        const filename = `vkteams_${safeName}_${new Date().toISOString().slice(0,10)}.html`;

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();

        URL.revokeObjectURL(url);
        console.log(`💾 Сохранено: ${filename}`);
    }

    function escapeHtml(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatTime(timestamp) {
        const date = new Date(timestamp * 1000);
        return date.toLocaleString('ru-RU', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function renderMessage(msg) {
        const isOutgoing = msg.outgoing === true;
        const sender = msg.chat?.sender || msg.senderNick || msg.sender || 'Unknown';
        const text = msg.text || '';
        const time = formatTime(msg.time);

        let content = escapeHtml(text);

        // Обработка файлов
        let filesHtml = '';
        if (msg.parts) {
            msg.parts.forEach(part => {
                if (part.type === 'file' && part.payload) {
                    const p = part.payload;
                    filesHtml += `<div class="file">📎 <a href="${escapeHtml(p.url)}" target="_blank">${escapeHtml(p.filename || 'файл')}</a> (${formatSize(p.size)})</div>`;
                }
                if (part.type === 'sticker' && part.payload) {
                    filesHtml += `<div class="sticker"><img src="${escapeHtml(part.payload.url)}" alt="sticker"></div>`;
                }
            });
        }

        // Обработка reply
        let replyHtml = '';
        if (msg.quotes && msg.quotes.length > 0) {
            const quote = msg.quotes[0];
            replyHtml = `<div class="reply">↩️ ${escapeHtml(quote.senderNick || quote.sender)}: ${escapeHtml((quote.text || '').substring(0, 100))}...</div>`;
        }

        return `<div class="message ${isOutgoing ? 'outgoing' : ''}">
            <span class="time">${time}</span>
            <div class="sender">${escapeHtml(sender)}</div>
            ${replyHtml}
            <div class="text">${content}</div>
            ${filesHtml}
        </div>`;
    }

    function formatSize(bytes) {
        if (!bytes) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    // Экспортируем глобально
    window.exportChat = exportChat;
    window.VKTeamsExporter = {
        exportChat,
        fetchHistory,
        fetchChatInfo,
        getCurrentChatId,
        CONFIG
    };

    console.log(`
╔══════════════════════════════════════════════════════════╗
║          VK Teams Chat Exporter загружен!                ║
╠══════════════════════════════════════════════════════════╣
║  Команды:                                                ║
║  • await exportChat()         - экспорт в JSON           ║
║  • await exportChat({format:'html'}) - экспорт в HTML    ║
║  • await exportChat({maxMessages:500}) - лимит сообщений ║
║  • await exportChat({chatId:'id@chat'}) - конкретный чат ║
╚══════════════════════════════════════════════════════════╝
    `);

})();
