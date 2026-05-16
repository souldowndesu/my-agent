// ============================================
// 消息气泡创建与渲染
// 依赖：state.js (localSessionsData, activeAssistantMessageBubble, userManuallyScrolledUp, saveLocalData)
//       utils.js (formatTime)
// ============================================

// DOM 引用（由 main.js 设置）
let messagesContainer = null;

function setMessagesContainer(el) {
    messagesContainer = el;
}

// 添加消息气泡（结构：气泡 > 时间戳行 + 正文行）
function appendMessageBubble(role, content, isHtml = false, savedTime = null) {
    const time = savedTime || new Date().toISOString();

    const wrapper = document.createElement('div');
    wrapper.classList.add('message-bubble');
    wrapper.classList.add(role);

    // 时间戳行
    const timeDiv = document.createElement('div');
    timeDiv.classList.add('msg-time');
    timeDiv.textContent = formatTime(time);

    // 正文行
    const textDiv = document.createElement('div');
    textDiv.classList.add('msg-text');
    if (isHtml) {
        textDiv.innerHTML = content;
    } else {
        textDiv.textContent = content;
    }

    wrapper.appendChild(timeDiv);
    wrapper.appendChild(textDiv);
    messagesContainer.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

// 创建 assistant 气泡（v2：load_history 和实时 SSE start 统一入口）
function createAssistantBubble(content, time) {
    return appendMessageBubble('assistant', content, false, time);
}

// 完成 assistant 气泡的最终处理（v2：统一保存到 localStorage）
function finalizeAssistantBubble(bubble, sessionId) {
    if (!bubble || !sessionId) return;
    const textContent = bubble.querySelector('.msg-text').textContent;
    if (!localSessionsData[sessionId]) {
        localSessionsData[sessionId] = [];
    }
    localSessionsData[sessionId].push({
        role: 'assistant',
        content: textContent,
        isHtml: false,
        time: new Date().toISOString()
    });
    saveLocalData();
}

// 仅重新渲染消息容器（不清空再重建，避免闪烁；改用 diff 风格替换）
function reRenderMessages(sessionId) {
    const history = localSessionsData[sessionId] || [];
    // 仅在内容变化时才重建 DOM，避免无谓的闪烁
    const currentBubbleCount = messagesContainer.querySelectorAll('.message-bubble').length;
    if (currentBubbleCount === history.length) {
        // 数量相同，快速比对第一条和最后一条内容
        let needsUpdate = false;
        const bubbles = messagesContainer.querySelectorAll('.message-bubble');
        if (history.length > 0) {
            const firstBubble = bubbles[0];
            const firstText = firstBubble ? firstBubble.querySelector('.msg-text') : null;
            if (firstText) {
                const expectedContent = history[0].isHtml ? history[0].content : '';
                const actualContent = history[0].isHtml ? firstText.innerHTML : firstText.textContent;
                if (actualContent !== expectedContent) needsUpdate = true;
            }
            const lastBubble = bubbles[bubbles.length - 1];
            const lastText = lastBubble ? lastBubble.querySelector('.msg-text') : null;
            if (lastText && history.length > 1) {
                const lastMsg = history[history.length - 1];
                const expectedContent = lastMsg.isHtml ? lastMsg.content : '';
                const actualContent = lastMsg.isHtml ? lastText.innerHTML : lastText.textContent;
                if (actualContent !== expectedContent) needsUpdate = true;
            }
        }
        if (!needsUpdate) return;  // 无变化，不重建
    }
    // 有变化，重建
    messagesContainer.innerHTML = '';
    history.forEach(msg => {
        appendMessageBubble(msg.role, msg.content, msg.isHtml, msg.time);
    });
}

// 智能滚动到底部：仅当用户在底部附近且未手动上翻时才自动滚动
function scrollToBottom() {
    const threshold = 80; // 距离底部80px以内视为"在底部"
    const isNearBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < threshold;
    // 只有用户在底部附近且没有手动上翻时才自动滚动
    if (isNearBottom && !userManuallyScrolledUp) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

// 绑定滚动事件监听（由 main.js 在初始化时调用）
function bindScrollListeners(container) {
    // 1) wheel 事件：精准判断方向
    container.addEventListener('wheel', function(e) {
        if (e.deltaY < 0) {
            userManuallyScrolledUp = true;
        } else if (e.deltaY > 0) {
            const threshold = 10;
            const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
            if (isAtBottom) {
                userManuallyScrolledUp = false;
            }
        }
    });

    // 2) scroll 事件：捕获滚动条拖动、键盘翻页等，判断是否在底部
    container.addEventListener('scroll', function() {
        const threshold = 10;
        const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
        if (!isAtBottom) {
            userManuallyScrolledUp = true;
        } else {
            userManuallyScrolledUp = false;
        }
    });

    // 3) 触摸/拖动滚动（移动端支持）
    container.addEventListener('touchmove', function() {
        const threshold = 10;
        const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
        if (!isAtBottom) {
            userManuallyScrolledUp = true;
        } else {
            userManuallyScrolledUp = false;
        }
    });
}