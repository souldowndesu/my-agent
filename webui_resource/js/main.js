// ============================================
// 入口初始化
// 依赖：所有前置模块
// ============================================

document.addEventListener('DOMContentLoaded', async function() {
    // 设置 DOM 引用
    setMessagesContainer(document.getElementById('messages-container'));
    setChatListEl(document.getElementById('chat-list'));

    // 绑定滚动事件
    bindScrollListeners(document.getElementById('messages-container'));

    // 清理 localStorage 旧数据
    sanitizeLocalStorage();

    // 获取 main 会话并初始化
    const mainId = getMainSessionId();
    if (mainId) {
        await switchSession(mainId);
    }

    // ========================================
    // 绑定 UI 事件
    // ========================================

    // 新建临时对话
    document.getElementById('new-chat-btn').addEventListener('click', createTempChat);

    // 清理临时对话
    document.getElementById('clean-temp-btn').addEventListener('click', function() {
        if (confirm('确定要清理所有临时对话吗？数据不会删除，仅从侧边栏隐藏。')) {
            cleanTempChats();
        }
    });

    // 发送消息按钮
    document.getElementById('send-btn').addEventListener('click', sendMessage);

    // 回车发送
    document.getElementById('message-input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // 连接状态切换按钮
    document.getElementById('connection-toggle-btn').addEventListener('click', function() {
        const status = connectionStatus.get(currentSessionId);
        if (status === 'connected') {
            disconnectCurrentSession();
        } else {
            reconnectCurrentSession();
        }
    });

    // 记忆压缩按钮
    document.getElementById('compact-btn').addEventListener('click', function() {
        if (confirm('记忆压缩将总结当前对话历史，压缩后无法恢复。确定继续吗？')) {
            startCompact();
        }
    });

    // 页面卸载时关闭所有 SSE 连接
    window.addEventListener('beforeunload', function() {
        eventSources.forEach(es => es.close());
        eventSources.clear();
    });

    // 禁用浏览器输入框自动补全
    document.getElementById('message-input').setAttribute('autocomplete', 'off');
});