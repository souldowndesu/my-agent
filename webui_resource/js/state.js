// ============================================
// 全局状态管理 + localStorage 持久化
// 依赖：config.js (BASE_URL)
// ============================================

// 当前激活的会话 ID
let currentSessionId = null;

// SSE 连接池：每个 session 独立的 EventSource，切换会话不断开旧连接
const eventSources = new Map();  // Map<sessionId, EventSource>

// 连接状态跟踪：connected / disconnected
const connectionStatus = new Map();  // Map<sessionId, 'connected'|'disconnected'>

// 当前正在流式输出的 assistant 气泡 DOM 元素
let activeAssistantMessageBubble = null;

// 工具调用气泡引用，key 为工具名
let activeToolBubbles = {};

// 用户手动上翻标记（用于阻止自动滚动）
let userManuallyScrolledUp = false;

// 压缩状态
let isCompacting = false;
let compactEventSource = null;
let compactSessionId = null;

// 前端本地存储
let localSessionsData = JSON.parse(localStorage.getItem('chatSessions')) || {};

// 已隐藏的临时会话 ID 集合（数据不删除，仅从侧边栏隐藏）
let hiddenTempIds = new Set(JSON.parse(localStorage.getItem('hiddenTempIds')) || []);

// 持久化到 localStorage
function saveLocalData() {
    localStorage.setItem('chatSessions', JSON.stringify(localSessionsData));
}

// 清理 localStorage 中无效/旧格式的会话条目（只保留 main_* 和 temp-N 格式）
function sanitizeLocalStorage() {
    const validKeys = {};
    let maxTempNum = 0;
    Object.keys(localSessionsData).forEach(key => {
        if (key.startsWith('main_')) {
            // 只保留第一个 main_ 会话
            if (!Object.keys(validKeys).some(k => k.startsWith('main_'))) {
                validKeys[key] = localSessionsData[key];
            }
        } else if (/^temp-\d+$/.test(key)) {
            // 保留有效 temp-N 格式（跳过 temp-0）
            const num = parseInt(key.replace('temp-', ''), 10);
            if (num > 0) {
                validKeys[key] = localSessionsData[key];
                if (num > maxTempNum) maxTempNum = num;
            }
        }
        // 丢弃所有其他格式（compact_、chat_、temp_xxx 旧格式、temp-0）
    });
    if (maxTempNum > 0) {
        localStorage.setItem('tempCounter', String(maxTempNum));
    } else {
        // 清除无效计数器，确保下次从 1 开始
        localStorage.removeItem('tempCounter');
    }
    localSessionsData = validKeys;
    saveLocalData();
    // 清理隐藏列表中的无效条目
    const validHiddenSet = new Set();
    hiddenTempIds.forEach(id => {
        if (/^temp-[1-9]\d*$/.test(id)) validHiddenSet.add(id);
    });
    hiddenTempIds = validHiddenSet;
    localStorage.setItem('hiddenTempIds', JSON.stringify([...hiddenTempIds]));
}