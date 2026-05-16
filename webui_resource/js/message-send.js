// ============================================
// 消息发送与持久化
// 依赖：state.js (currentSessionId, localSessionsData, saveLocalData)
//       message-bubble.js (appendMessageBubble, reRenderMessages)
//       sse-client.js (ensureConnected)
//       ui.js (hideFollowUpHint)
// ============================================

// 禁用发送按钮
function disableSendButton() {
    const btn = document.getElementById('send-btn');
    const input = document.getElementById('message-input');
    if (btn) {
        btn.disabled = true;
        btn.style.backgroundColor = 'var(--color-primary-disabled)';
        btn.textContent = '⏳';
    }
    if (input) input.disabled = true;
}

// 启用发送按钮
function enableSendButton() {
    const btn = document.getElementById('send-btn');
    const input = document.getElementById('message-input');
    if (btn) {
        btn.disabled = false;
        btn.style.backgroundColor = 'var(--color-primary)';
        btn.textContent = '发送';
    }
    if (input) {
        input.disabled = false;
        input.focus();
    }
}

// 保存消息到 localStorage
function saveMessageToLocal(sessionId, role, content, isHtml = false) {
    if (!localSessionsData[sessionId]) {
        localSessionsData[sessionId] = [];
    }
    localSessionsData[sessionId].push({
        role: role,
        content: content,
        isHtml: isHtml,
        time: new Date().toISOString()
    });
    saveLocalData();
}

// 专门保存 assistant 消息（由 sse-client.js 在 end 事件中调用）
function saveAssistantToLocal(sessionId, content) {
    saveMessageToLocal(sessionId, 'assistant', content, false);
}

// 发送用户消息
async function sendMessage() {
    const input = document.getElementById('message-input');
    const msg = input.value.trim();
    if (!msg) return;
    if (!currentSessionId) {
        alert('暂无活动会话');
        return;
    }

    // 隐藏追问提示
    if (typeof hideFollowUpHint === 'function') {
        hideFollowUpHint();
    }

    // 1. 清空输入框并禁用
    input.value = '';
    disableSendButton();

    // 2. 展示用户气泡 + 持久化
    appendMessageBubble('user', msg);
    saveMessageToLocal(currentSessionId, 'user', msg);

    // 3. 确保 SSE 连接
    if (typeof ensureConnected === 'function') {
        ensureConnected(currentSessionId);
    }

    // 4. 发送到后端 /str-input
    try {
        const res = await fetch(`${BASE_URL}/str-input`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                content: msg
            })
        });
        if (!res.ok) {
            appendMessageBubble('error', `请求失败 (${res.status})`, false);
            enableSendButton();
        }
    } catch (e) {
        appendMessageBubble('error', `网络错误: ${e.message}`, false);
        enableSendButton();
    }
}