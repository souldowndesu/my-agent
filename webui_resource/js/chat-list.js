// ============================================
// 侧边栏会话列表渲染与 CRUD
// 依赖：state.js (localSessionsData, hiddenTempIds, saveLocalData)
//       utils.js (formatTime, getSessionType, generateSessionId)
//       session-switch.js (switchSession)
// ============================================

// DOM 引用（由 main.js 设置）
let chatListEl = null;

function setChatListEl(el) {
    chatListEl = el;
}

// 渲染侧边栏会话列表（main 在前，temp 按照首条消息时间倒序）
function renderChatList() {
    if (!chatListEl) return;
    chatListEl.innerHTML = '';

    const mainSessions = [];
    const tempSessions = [];

    Object.keys(localSessionsData).forEach(sid => {
        const type = getSessionType(sid);
        if (type === 'main') {
            mainSessions.push(sid);
        } else if (type === 'temp') {
            // 跳过已隐藏的
            if (!hiddenTempIds.has(sid)) {
                tempSessions.push(sid);
            }
        }
        // compact 不显示在侧边栏
    });

    // main 放在最前
    mainSessions.sort((a, b) => b.localeCompare(a));  // 稳定排序
    tempSessions.sort((a, b) => {
        const numA = parseInt(a.replace('temp-', ''), 10);
        const numB = parseInt(b.replace('temp-', ''), 10);
        return numB - numA;  // 按编号倒序（大编号在前）
    });

    const allIds = [...mainSessions, ...tempSessions];
    allIds.forEach(sid => {
        const li = document.createElement('li');
        li.classList.add('chat-item');
        if (sid === currentSessionId) li.classList.add('active');
        const type = getSessionType(sid);
        const prefix = type === 'main' ? '🔷 主对话' : '💬 临时对话';
        const msgs = localSessionsData[sid] || [];
        // 取第一条 user 消息作为预览标题
        const firstUser = msgs.find(m => m.role === 'user');
        const preview = firstUser ? firstUser.content.substring(0, 20) : '空对话';
        const time = msgs.length > 0 ? formatTime(msgs[0].time) : '';
        li.title = sid;
        li.innerHTML = `<span class="chat-title">${prefix}</span><span class="chat-preview">${preview}</span><span class="chat-time">${time}</span>`;
        li.addEventListener('click', () => switchSession(sid));
        chatListEl.appendChild(li);
    });
}

// 新建临时会话
function createTempChat() {
    const newId = generateSessionId('temp');
    localSessionsData[newId] = [];
    saveLocalData();
    renderChatList();
    switchSession(newId);
}

// 清理临时会话（隐藏，不删除数据）
function cleanTempChats() {
    Object.keys(localSessionsData).forEach(sid => {
        if (getSessionType(sid) === 'temp') {
            hiddenTempIds.add(sid);
        }
    });
    localStorage.setItem('hiddenTempIds', JSON.stringify([...hiddenTempIds]));
    renderChatList();
    // 如果当前会话是被隐藏的 temp，切换到 main
    if (hiddenTempIds.has(currentSessionId)) {
        switchSession(getMainSessionId());
    }
}