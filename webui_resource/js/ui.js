// ============================================
// UI 辅助函数（提示、按钮状态）
// 依赖：state.js (currentSessionId)
// ============================================

// 显示"可以继续追问"提示
function showFollowUpHint() {
    const hint = document.getElementById('follow-up-hint');
    if (hint) {
        hint.style.display = 'block';
    }
}

// 隐藏追问提示
function hideFollowUpHint() {
    const hint = document.getElementById('follow-up-hint');
    if (hint) {
        hint.style.display = 'none';
    }
}

// 更新压缩按钮状态（仅在 main 会话可见）
function updateCompactButton() {
    const btn = document.getElementById('compact-btn');
    if (!btn) return;
    // 只在 main 会话显示压缩按钮
    if (currentSessionId && currentSessionId.startsWith('main_')) {
        btn.style.display = 'inline-block';
    } else {
        btn.style.display = 'none';
    }
}