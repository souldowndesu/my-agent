// ============================================
// SSE 连接池与服务端事件处理
// 依赖：state.js (currentSessionId, eventSources, connectionStatus, activeAssistantMessageBubble, activeToolBubbles, saveLocalData)
//       message-bubble.js (createAssistantBubble, finalizeAssistantBubble, appendMessageBubble)
// ============================================

// 更新连接按钮 UI
function updateConnectionButton() {
    const btn = document.getElementById('connection-toggle-btn');
    if (!btn) return;
    const status = connectionStatus.get(currentSessionId) || 'disconnected';
    if (status === 'connected') {
        btn.textContent = '🔗 已连接';
        btn.style.backgroundColor = 'var(--color-connected-bg)';
        btn.style.color = 'var(--color-connected-text)';
        btn.style.borderColor = 'var(--color-connected-border)';
    } else {
        btn.textContent = '🔌 未连接';
        btn.style.backgroundColor = 'var(--color-disconnected-bg)';
        btn.style.color = 'var(--color-disconnected-text)';
        btn.style.borderColor = 'var(--color-disconnected-border)';
    }
}

// 获取指定会话的连接状态
function getSessionConnectionStatus(sessionId) {
    return connectionStatus.get(sessionId) || 'disconnected';
}

// 分发服务端 SSE 事件
function handleServerEvent(payload, sessionId) {
    if (!payload || !payload.type) return;

    // 只处理当前活动会话的事件
    if (sessionId !== currentSessionId) return;

    switch (payload.type) {
        case 'start':
            // v2：统一使用 createAssistantBubble 创建 assistant 气泡
            activeAssistantMessageBubble = createAssistantBubble('', payload.data?.time || null);
            break;

        case 'content':
            if (payload.data?.content) {
                if (activeAssistantMessageBubble) {
                    // 追加到当前 assistant 气泡
                    const textEl = activeAssistantMessageBubble.querySelector('.msg-text');
                    if (textEl) {
                        textEl.textContent += payload.data.content;
                    }
                } else {
                    // v2：tool 之后 activeBubble 为 null，自动创建新气泡实现分离
                    activeAssistantMessageBubble = createAssistantBubble(payload.data.content, null);
                }
                if (typeof scrollToBottom === 'function') scrollToBottom();
            }
            break;

        case 'tool_status':
            {
                const toolName = payload.data?.tool_name || 'unknown';
                const status = payload.data?.status || '';

                if (status === 'start') {
                    // v2：tool 开始前，先完成当前 assistant 气泡并归档
                    if (activeAssistantMessageBubble) {
                        finalizeAssistantBubble(activeAssistantMessageBubble, sessionId);
                        activeAssistantMessageBubble = null;
                    }

                    // 创建 tool 气泡
                    const toolBubble = document.createElement('div');
                    toolBubble.classList.add('message-bubble');
                    toolBubble.classList.add('tool');
                    toolBubble.innerHTML = `
                        <details open>
                            <summary>⚙️ 工具 ${toolName} 执行中...</summary>
                            <div class="tool-section-label">📥 输入参数</div>
                            <pre class="tool-output tool-input">${payload.data?.input || '获取中...'}</pre>
                            <div class="tool-section-label">📤 输出结果</div>
                            <pre class="tool-output">等待返回...</pre>
                        </details>
                    `;
                    const container = document.getElementById('messages-container');
                    if (container) {
                        container.appendChild(toolBubble);
                    }
                    activeToolBubbles[toolName] = toolBubble;
                    if (typeof scrollToBottom === 'function') scrollToBottom();

                } else if (status === 'result') {
                    // 更新 tool 气泡的结果
                    const existingBubble = activeToolBubbles[toolName];
                    if (existingBubble) {
                        existingBubble.querySelector('summary').innerHTML =
                            `⚙️ 工具 ${toolName} 执行完毕 ✅`;
                        const outputPre = existingBubble.querySelector('.tool-output:not(.tool-input)');
                        if (outputPre) {
                            outputPre.textContent = payload.data?.result || '(无返回)';
                        }
                        // 更新输入参数
                        const inputPre = existingBubble.querySelector('.tool-output.tool-input');
                        if (inputPre && payload.data?.input) {
                            inputPre.textContent = payload.data.input;
                        }
                    } else {
                        // 直接创建完成的 tool 气泡（向后兼容）
                        const toolBubble = document.createElement('div');
                        toolBubble.classList.add('message-bubble');
                        toolBubble.classList.add('tool');
                        toolBubble.innerHTML = `
                            <details open>
                                <summary>⚙️ 工具 ${toolName} 执行完毕 ✅</summary>
                                <div class="tool-section-label">📥 输入参数</div>
                                <pre class="tool-output tool-input">${payload.data?.input || ''}</pre>
                                <div class="tool-section-label">📤 输出结果</div>
                                <pre class="tool-output">${payload.data?.result || ''}</pre>
                            </details>
                        `;
                        const container = document.getElementById('messages-container');
                        if (container) {
                            container.appendChild(toolBubble);
                        }
                        if (typeof scrollToBottom === 'function') scrollToBottom();
                    }
                }
            }
            break;

        case 'end':
            // v2：结束当前 assistant 气泡并保存
            if (activeAssistantMessageBubble) {
                finalizeAssistantBubble(activeAssistantMessageBubble, sessionId);
                activeAssistantMessageBubble = null;
            }
            // 恢复发送按钮
            if (typeof enableSendButton === 'function') {
                enableSendButton();
            }
            // 显示追问提示
            if (typeof showFollowUpHint === 'function') {
                showFollowUpHint();
            }
            break;

        case 'error':
            {
                const errMsg = payload.data?.message || '未知错误';
                appendMessageBubble('error', errMsg, false);
                activeAssistantMessageBubble = null;
                if (typeof enableSendButton === 'function') {
                    enableSendButton();
                }
            }
            break;
    }
}

// 建立 SSE 连接并注册到连接池
function connectSSE(sessionId) {
    if (!sessionId) return;

    // 如果已有连接且状态正常，跳过
    const existingSrc = eventSources.get(sessionId);
    if (existingSrc && existingSrc.readyState !== EventSource.CLOSED) {
        connectionStatus.set(sessionId, 'connected');
        updateConnectionButton();
        return;
    }

    // 关闭旧连接
    if (existingSrc) {
        existingSrc.close();
        eventSources.delete(sessionId);
    }

    try {
        const es = new EventSource(`${BASE_URL}/stream?session_id=${encodeURIComponent(sessionId)}`);

        es.onopen = () => {
            connectionStatus.set(sessionId, 'connected');
            if (sessionId === currentSessionId) updateConnectionButton();
        };

        es.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                handleServerEvent(payload, sessionId);
            } catch (e) {
                console.warn('SSE 消息解析失败:', e);
            }
        };

        es.onerror = () => {
            connectionStatus.set(sessionId, 'disconnected');
            if (sessionId === currentSessionId) updateConnectionButton();
            // 自动重连由 EventSource 内置机制处理
        };

        eventSources.set(sessionId, es);
    } catch (e) {
        console.warn('SSE 连接创建失败:', e);
        connectionStatus.set(sessionId, 'disconnected');
        if (sessionId === currentSessionId) updateConnectionButton();
    }
}

// 确保会话已连接（复用或新建）
function ensureConnected(sessionId) {
    if (!sessionId) return;
    const status = connectionStatus.get(sessionId);
    if (status === 'connected') {
        updateConnectionButton();
        return;
    }
    connectSSE(sessionId);
}

// 手动断开当前会话 SSE
function disconnectCurrentSession() {
    if (!currentSessionId) return;
    const es = eventSources.get(currentSessionId);
    if (es) {
        es.close();
        eventSources.delete(currentSessionId);
    }
    connectionStatus.set(currentSessionId, 'disconnected');
    updateConnectionButton();
}

// 手动重连当前会话 SSE
function reconnectCurrentSession() {
    if (!currentSessionId) return;
    disconnectCurrentSession();
    connectSSE(currentSessionId);
}