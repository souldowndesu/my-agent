// ============================================
// 通用工具函数
// 依赖：state.js (localSessionsData, saveLocalData)
// ============================================

// 格式化时间戳为本地可读时间
function formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// 生成带前缀的 session_id（temp 使用递增编号 temp-1, temp-2 ...）
function generateSessionId(type) {
    if (type === 'temp') {
        const nextNum = (parseInt(localStorage.getItem('tempCounter')) || 0) + 1;
        localStorage.setItem('tempCounter', nextNum);
        return `temp-${nextNum}`;
    }
    // compact 仍用随机后缀（不在侧边栏显示，无影响）
    if (type === 'compact') {
        const chars = '0123456789abcdefghijklmnopqrstuvwxyz';
        let shortId = '';
        for (let i = 0; i < 6; i++) {
            shortId += chars[Math.floor(Math.random() * chars.length)];
        }
        return `compact_${shortId}`;
    }
    // main 保持原有随机逻辑
    const chars = '0123456789abcdefghijklmnopqrstuvwxyz';
    let shortId = '';
    for (let i = 0; i < 6; i++) {
        shortId += chars[Math.floor(Math.random() * chars.length)];
    }
    return `main_${shortId}`;
}

// 获取 main 会话 ID（始终用固定的 main_ 前缀，若不存在则创建）
function getMainSessionId() {
    const mainKey = Object.keys(localSessionsData).find(k => k.startsWith('main_'));
    if (mainKey) return mainKey;
    const newMainId = generateSessionId('main');
    localSessionsData[newMainId] = [];
    saveLocalData();
    return newMainId;
}

// 从 sessionId 解析出 session_type（兼容 temp-N 新格式和 main_xxx / compact_xxx 旧格式）
function getSessionType(sessionId) {
    if (sessionId.startsWith('temp-')) return 'temp';
    if (sessionId.includes('_')) return sessionId.split('_')[0];
    return 'chat';
}