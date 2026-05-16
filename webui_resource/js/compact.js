// ============================================
// 记忆压缩流程
// 依赖：state.js (currentSessionId, isCompacting, compactEventSource, compactSessionId, eventSources, connectionStatus, localSessionsData, saveLocalData)
//       message-bubble.js (appendMessageBubble, reRenderMessages)
//       chat-list.js (renderChatList)
// ============================================

// 处理压缩 SSE 事件
function handleCompactEvent(payload) {
    if (!payload || !payload.type) return;

    switch (payload.type) {
        case 'start':
            appendMessageBubble('assistant', '🔄 开始压缩记忆...');
            break;

        case 'content':
            // 压缩过程中的流式内容可选择性展示
            break;

        case 'end':
            finishCompactWithRefresh();
            break;

        case 'error':
            appendMessageBubble('error', `压缩失败: ${payload.data?.message || '未知错误'}`);
            finishCompact();
            break;
    }
}

// 步骤4：刷新主会话 + 同步前端
async function finishCompactWithRefresh() {
    try {
        // 从服务端重新拉取主会话历史
        const res = await fetch(`${BASE_URL}/get-history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId })
        });
        if (res.ok) {
            const data = await res.json();
            if (data.history) {
                localSessionsData[currentSessionId] = data.history;
                saveLocalData();
                reRenderMessages(currentSessionId);
            }
        }
        appendMessageBubble('system', '✅ 记忆压缩完成');
    } catch (e) {
        appendMessageBubble('error', `记忆压缩完成但刷新失败: ${e.message}`);
    }
    finishCompact();
}

// 清理压缩状态
function finishCompact() {
    if (compactEventSource) {
        compactEventSource.close();
        compactEventSource = null;
    }
    compactSessionId = null;
    isCompacting = false;

    // 恢复压缩按钮
    const btn = document.getElementById('compact-btn');
    if (btn) {
        btn.disabled = false;
        btn.textContent = '🧠 记忆压缩';
    }
}

// 启动压缩流程
async function startCompact() {
    if (!currentSessionId || isCompacting) return;

    // 检查是否为 main 会话
    if (!currentSessionId.startsWith('main_')) {
        alert('仅在主对话中支持记忆压缩');
        return;
    }

    isCompacting = true;
    const btn = document.getElementById('compact-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ 压缩中...';
    }

    try {
        // 步骤1：发送压缩请求
        const res = await fetch(`${BASE_URL}/cmd?cmd=compact`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId })
        });

        if (!res.ok) {
            appendMessageBubble('error', `压缩请求失败 (${res.status})`, false);
            finishCompact();
            return;
        }

        compactSessionId = currentSessionId;

        // 步骤2 & 3：连接压缩专用的 SSE 流
        compactEventSource = new EventSource(`${BASE_URL}/stream?session_id=${encodeURIComponent(currentSessionId)}&compact=true`);

        compactEventSource.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                handleCompactEvent(payload);
            } catch (e) {
                console.warn('压缩 SSE 消息解析失败:', e);
            }
        };

        compactEventSource.onerror = () => {
            appendMessageBubble('error', '压缩 SSE 连接异常', false);
            finishCompact();
        };

    } catch (e) {
        appendMessageBubble('error', `压缩流程错误: ${e.message}`, false);
        finishCompact();
    }
}