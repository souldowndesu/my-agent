const BASE_URL = 'http://127.0.0.1:8001';

// DOM 元素引用
const newChatBtn = document.getElementById('new-chat-btn');
const chatListUl = document.getElementById('chat-list');
const messagesContainer = document.getElementById('messages-container');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const currentSessionTitle = document.getElementById('current-session-title');

// 状态管理
let currentSessionId = null;
let currentEventSource = null; // 用于管理和断开 SSE 连接
let activeAssistantMessageBubble = null; // 当前正在接收数据的气泡

// 前端本地存储（用于在不同会话间切换时恢复 UI 显示）
let localSessionsData = JSON.parse(localStorage.getItem('chatSessions')) || {};

// 初始化
function init() {
    renderChatList();
    newChatBtn.addEventListener('click', createNewChat);
    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
}

// 渲染左侧会话列表
function renderChatList() {
    chatListUl.innerHTML = '';
    const sessionIds = Object.keys(localSessionsData);
    
    sessionIds.forEach(id => {
        const li = document.createElement('li');
        // 取前8个字符作为简单展示名
        li.textContent = `对话: ${id.substring(0, 8)}...`; 
        if (id === currentSessionId) li.classList.add('active');
        
        li.addEventListener('click', () => switchSession(id));
        chatListUl.appendChild(li);
    });
}

// 生成 UUID 作为 session_id
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// 新建对话
function createNewChat() {
    const newId = generateUUID();
    localSessionsData[newId] = []; // 初始化空消息数组
    saveLocalData();
    switchSession(newId);
}

// 切换对话（核心连接管理逻辑）
function switchSession(sessionId) {
    if (currentSessionId === sessionId) return;

    // 1. 彻底断开之前的 SSE 连接
    if (currentEventSource) {
        currentEventSource.close();
        console.log(`[Frontend] 已主动断开会话 ${currentSessionId} 的连接`);
        currentEventSource = null;
    }

    currentSessionId = sessionId;
    currentSessionTitle.textContent = `当前对话 ID: ${sessionId}`;
    
    // 2. 启用输入框
    messageInput.disabled = false;
    sendBtn.disabled = false;
    
    // 3. 恢复历史消息 UI 显示
    messagesContainer.innerHTML = '';
    const history = localSessionsData[sessionId] || [];
    history.forEach(msg => {
        appendMessageBubble(msg.role, msg.content);
    });
    
    renderChatList();

    // 4. 发起针对新对话的连接尝试
    connectSSE(sessionId);
}

// 建立 Server-Sent Events 连接
function connectSSE(sessionId) {
    console.log(`[Frontend] 尝试连接到会话: ${sessionId}`);
    
    currentEventSource = new EventSource(`${BASE_URL}/stream/${sessionId}`);
    
    currentEventSource.onmessage = function(event) {
        const payload = JSON.parse(event.data);
        handleServerEvent(payload);
    };

    currentEventSource.onerror = function(err) {
        console.error(`[Frontend] SSE 连接发生错误 (会话: ${sessionId})`, err);
        // EventSource 会自动尝试重连，但根据业务可选择是否在这里做强制重连逻辑
    };
}

// 处理服务端通过 SSE 推送的事件数据
function handleServerEvent(payload) {
    switch (payload.event) {
        case 'start':
            // 收到后端开始生成的信号，创建空的 Assistant 气泡
            activeAssistantMessageBubble = appendMessageBubble('assistant', '');
            break;
            
        case 'content':
            // 将数据字词追加到当前活动的气泡中
            if (activeAssistantMessageBubble) {
                activeAssistantMessageBubble.textContent += payload.data;
                scrollToBottom();
            }
            break;
            
        case 'end':
            // 生成结束，将完整内容保存至前端本地缓存
            if (activeAssistantMessageBubble) {
                saveMessageToLocal(currentSessionId, 'assistant', activeAssistantMessageBubble.textContent);
            }
            activeAssistantMessageBubble = null;
            sendBtn.disabled = false; // 重新开放发送按钮
            break;
            
        case 'error':
            appendMessageBubble('assistant', `[系统错误]: ${payload.error_msg}`);
            activeAssistantMessageBubble = null;
            sendBtn.disabled = false;
            break;
    }
}

// 发送消息
async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || !currentSessionId) return;

    // 1. 更新 UI 与本地存储
    appendMessageBubble('user', text);
    saveMessageToLocal(currentSessionId, 'user', text);
    messageInput.value = '';
    sendBtn.disabled = true; // 发送期间禁用按钮防抖

    // 2. 向后端发送 POST 请求启动推理逻辑
    // 注意：你的 FastAPI endpoint 使用 async def generate(session_id:str, user_input:str)
    // FastApi 默认会将无验证的 string 参数作为 query parameter 接收
    try {
        const response = await fetch(`${BASE_URL}/str-input/${currentSessionId}?user_input=${encodeURIComponent(text)}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (result.status !== 'started') {
            throw new Error("启动对话任务失败");
        }
    } catch (error) {
        console.error("[Frontend] 消息发送异常:", error);
        appendMessageBubble('assistant', `[网络错误]: 无法连接到生成节点。`);
        sendBtn.disabled = false;
    }
}

// 辅助方法：添加消息气泡到界面
function appendMessageBubble(role, content) {
    const div = document.createElement('div');
    div.classList.add('message-bubble');
    div.classList.add(role);
    div.textContent = content;
    messagesContainer.appendChild(div);
    scrollToBottom();
    return div;
}

// 辅助方法：滚动到底部
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// 辅助方法：持久化同步逻辑
function saveMessageToLocal(sessionId, role, content) {
    if (!localSessionsData[sessionId]) {
        localSessionsData[sessionId] = [];
    }
    localSessionsData[sessionId].push({ role, content });
    saveLocalData();
}

function saveLocalData() {
    localStorage.setItem('chatSessions', JSON.stringify(localSessionsData));
}

// 启动执行
init();