// ============================================
// 会话切换逻辑
// 依赖：state.js (currentSessionId, localSessionsData, eventSources, connectionStatus, saveLocalData)
//       utils.js (getMainSessionId)
//       message-bubble.js (reRenderMessages, appendMessageBubble)
//       chat-list.js (renderChatList)
//       sse-client.js (ensureConnected)
//       ui.js (updateCompactButton)
// ============================================

// 从服务端拉取最新历史，覆盖 localStorage 缓存
async function syncAndRenderHistory(sessionId) {
    try {
        const result = await fetch(`${BASE_URL}/get-history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        if (result.ok) {
            const data = await result.json();
            if (data.history) {
                localSessionsData[sessionId] = data.history;
                saveLocalData();
                reRenderMessages(sessionId);
            }
        }
    } catch (e) {
        // 静默失败，使用本地缓存
        reRenderMessages(sessionId);
    }
}

// 核心切换逻辑
async function switchSession(sessionId) {
    if (currentSessionId === sessionId) return;

    // 1. 清理当前 UI 状态
    activeAssistantMessageBubble = null;
    activeToolBubbles = {};

    // 2. 更新当前会话
    currentSessionId = sessionId;

    // 3. 同步服务端历史
    await syncAndRenderHistory(sessionId);

    // 4. 刷新后端 LLM 上下文
    try {
        await fetch(`${BASE_URL}/cmd?cmd=refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
    } catch (_) { /* 忽略 */ }

    // 5. 更新会话标题
    document.getElementById('current-session-title').textContent =
        sessionId.startsWith('main_') ? '🔷 主对话' : '💬 临时对话 ' + sessionId.replace('temp-', '');

    // 6. 渲染侧边栏
    renderChatList();

    // 7. 更新压缩按钮状态
    if (typeof updateCompactButton === 'function') {
        updateCompactButton();
    }

    // 8. 确保 SSE 连接
    if (typeof ensureConnected === 'function') {
        ensureConnected(sessionId);
    }
}