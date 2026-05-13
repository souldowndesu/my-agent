"""
UBAA 智慧北航 API 工具
通过 UBAA Server Relay 访问北航校园服务，支持博雅课程、签到、考试查询等功能。
路由路径与上游 Kotlin 路由文件保持一致。
"""
import httpx
import json
import os
import asyncio
from typing import Optional, Dict, Any

import dotenv

# ---- 配置 ----
API_ENDPOINT = os.getenv("UBAA_API_ENDPOINT", "https://ubaa.mofrp.top:2021")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".ubaa_tokens.json")

# 从环境变量加载凭据（不暴露给 LLM）
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
UBAA_USERNAME = os.getenv("UBAA_USERNAME")
UBAA_PASSWORD = os.getenv("UBAA_PASSWORD")

# 全局 HTTP 客户端（复用连接）
_client: Optional[httpx.AsyncClient] = None
_tokens: Optional[Dict[str, Any]] = None
_lock = asyncio.Lock()

# ---- 工具 Schema ----
_DESC_MAIN = (
    "通过 UBAA 网关访问北航校园服务 API。登录由系统自动处理，无需手动调用 login。\n"
    "支持以下操作：\n"
    "  博雅课程: bykc_profile, bykc_courses, bykc_chosen, bykc_detail, bykc_select, bykc_deselect, bykc_sign, bykc_statistics\n"
    "  课堂签到: signin_today, signin_do\n"
    "  课表: schedule_today, schedule_terms, schedule_weeks, schedule_week\n"
    "  考试/成绩: exam_list, grade_list（需要 term_code 参数）\n"
    "  空间管理: classroom\n"
    "  作业查询(SPOC): spoc_assignments, spoc_detail\n"
    "  作业查询(Judge): judge_assignments, judge_detail\n"
    "  场馆预约: cgyy_sites, cgyy_orders\n"
    "  教学评价: evaluation_list, evaluation_submit\n"
    "  公告/用户: announcement, status\n"
    "  认证: login, logout"
)

_DESC_PARAMS = (
    "各操作所需的额外参数：\n"
    '  bykc_courses: {"page": 1, "size": 20, "all": false}\n'
    '  bykc_detail: {"course_id": 123}\n'
    '  bykc_select / bykc_deselect / bykc_sign: {"course_id": 123}\n'
    '  bykc_sign: 额外支持 {"sign_type": 1(签到)/2(签退), "lat": 0, "lng": 0}\n'
    '  signin_do: {"course_id": "排课ID字符串"}\n'
    "  schedule_today: 无参数  获取今日课程\n"
    "  schedule_terms: 无参数  获取可用学期列表\n"
    '  schedule_weeks: {"term_code": "..."}  获取指定学期教学周\n'
    '  schedule_week: {"term_code": "...", "week": 1}  获取指定周课表\n'
    '  exam_list / grade_list: {"term_code": "..."}  学期代码（先通过 schedule_terms 获取）\n'
    '  classroom: {"xqid": 1, "date": "2026-05-13"}  (xqid: 1=学院路, 2=沙河)\n'
    "  spoc_assignments: 无参数  获取 SPOC 作业列表\n"
    '  spoc_detail: {"assignment_id": "..."}  获取 SPOC 作业详情\n'
    '  judge_assignments: {"include_expired": false}  获取希冀作业列表\n'
    '  judge_detail: {"course_id": "...", "assignment_id": "..."}\n'
    '  cgyy_orders: {"page": 0, "size": 20}\n'
    '  evaluation_submit: {"courses": [...]}  待评教课程列表'
)

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ubaa_api",
        "description": _DESC_MAIN,
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "要执行的操作",
                    "enum": [
                        "login", "status", "logout",
                        "bykc_profile", "bykc_courses", "bykc_chosen", "bykc_detail",
                        "bykc_select", "bykc_deselect", "bykc_sign", "bykc_statistics",
                        "signin_today", "signin_do",
                        "schedule_today", "schedule_terms", "schedule_weeks", "schedule_week",
                        "exam_list", "grade_list",
                        "classroom",
                        "spoc_assignments", "spoc_detail",
                        "judge_assignments", "judge_detail",
                        "cgyy_sites", "cgyy_orders",
                        "evaluation_list", "evaluation_submit",
                        "announcement"
                    ]
                },
                "params": {
                    "type": "object",
                    "description": _DESC_PARAMS,
                }
            },
            "required": ["action"]
        }
    }
}

# ---- Token 持久化 ----
def _load_tokens() -> Optional[Dict[str, Any]]:
    """从文件加载已保存的 Token"""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_tokens(data: Dict[str, Any]):
    """保存 Token 到文件"""
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _clear_tokens():
    """清除保存的 Token"""
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
    except Exception:
        pass


# ---- HTTP 客户端管理 ----
async def _get_client() -> httpx.AsyncClient:
    """获取或创建共享 HTTP 客户端"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=API_ENDPOINT,
            timeout=30.0,
            follow_redirects=True,
            verify=False  # 自签证书环境
        )
    return _client


async def _ensure_auth() -> Optional[Dict[str, str]]:
    """确保已加载 Token，返回认证头；若未登录返回 None"""
    global _tokens
    async with _lock:
        if _tokens is None:
            _tokens = _load_tokens()
        if _tokens and _tokens.get("accessToken"):
            return {"Authorization": f"Bearer {_tokens['accessToken']}"}
    return None


# ---- 核心 HTTP 请求 ----
async def _api_get(path: str, auth_required: bool = True) -> Dict[str, Any]:
    """发送 GET 请求到 UBAA API"""
    client = await _get_client()
    headers = {}
    if auth_required:
        auth_headers = await _ensure_auth()
        if not auth_headers:
            return {"error": "未登录，请先执行 login 操作"}
        headers.update(auth_headers)
    try:
        resp = await client.get(path, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except Exception as e:
        return {"error": str(e)}


async def _api_post(path: str, body: Dict = None, auth_required: bool = True) -> Dict[str, Any]:
    """发送 POST 请求到 UBAA API"""
    client = await _get_client()
    headers = {}
    if auth_required:
        auth_headers = await _ensure_auth()
        if not auth_headers:
            return {"error": "未登录，请先执行 login 操作"}
        headers.update(auth_headers)
    try:
        resp = await client.post(path, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except Exception as e:
        return {"error": str(e)}


async def _api_delete(path: str, auth_required: bool = True) -> Dict[str, Any]:
    """发送 DELETE 请求到 UBAA API"""
    client = await _get_client()
    headers = {}
    if auth_required:
        auth_headers = await _ensure_auth()
        if not auth_headers:
            return {"error": "未登录，请先执行 login 操作"}
        headers.update(auth_headers)
    try:
        resp = await client.delete(path, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except Exception as e:
        return {"error": str(e)}


# ---- 业务操作 ----
async def _login(username: str, password: str) -> Dict[str, Any]:
    """登录并保存 Token"""
    global _tokens
    async with _lock:
        _tokens = None
    client = await _get_client()
    try:
        resp = await client.post("/api/v1/auth/login", json={
            "username": username,
            "password": password
        })
        if resp.status_code != 200:
            return {"error": f"登录失败 HTTP {resp.status_code}", "detail": resp.text[:500]}
        data = resp.json()
        async with _lock:
            _tokens = {
                "accessToken": data.get("accessToken"),
                "refreshToken": data.get("refreshToken"),
                "accessTokenExpiresAt": data.get("accessTokenExpiresAt"),
                "refreshTokenExpiresAt": data.get("refreshTokenExpiresAt"),
            }
            _save_tokens(_tokens)
        return {"success": True, "message": "登录成功", "token_info": {k: v for k, v in _tokens.items() if "Token" in k}}
    except Exception as e:
        return {"error": f"登录请求失败: {str(e)}"}


async def _logout() -> Dict[str, Any]:
    """退出登录"""
    global _tokens, _client
    try:
        auth_headers = await _ensure_auth()
        if auth_headers:
            client = await _get_client()
            await client.post("/api/v1/auth/logout", headers=auth_headers)
    except Exception:
        pass
    async with _lock:
        _tokens = None
        _clear_tokens()
        if _client:
            await _client.aclose()
            _client = None
    return {"success": True, "message": "已退出登录"}


# ---- 自动登录 ----
async def _auto_login() -> bool:
    """自动从环境变量登录（对 LLM 透明），返回是否登录成功"""
    global _tokens
    # 先检查是否已有有效 Token
    tokens = await _ensure_auth()
    if tokens:
        return True
    # 检查凭据是否配置
    if not UBAA_USERNAME or not UBAA_PASSWORD:
        return False
    # 尝试登录
    result = await _login(UBAA_USERNAME, UBAA_PASSWORD)
    return result.get("success", False)


# ---- 主执行入口 ----
async def execute(action: str, params: dict = None):
    """
    执行 UBAA API 操作

    登录凭据从环境变量 UBAA_USERNAME / UBAA_PASSWORD 读取，不暴露给 LLM。
    首次调用任意需要认证的操作时，自动完成登录。
    """
    action = action.lower().strip()
    if params is None:
        params = {}

    # ========== 认证操作 ==========
    if action == "login":
        if not UBAA_USERNAME or not UBAA_PASSWORD:
            return {"error": "未配置 UBAA_USERNAME / UBAA_PASSWORD 环境变量，请在项目根目录 .env 文件中设置"}
        return await _login(UBAA_USERNAME, UBAA_PASSWORD)

    if action == "status":
        tokens = await _ensure_auth()
        if tokens:
            # 尝试获取用户信息来验证 Token 有效性
            result = await _api_get("/api/v1/user/info")
            if "error" not in result:
                return {"logged_in": True, "user_info": result}
            return {"logged_in": False, "reason": "Token 已过期或无效，请重新登录"}
        return {"logged_in": False, "message": "未登录"}

    if action == "logout":
        return await _logout()

    if action == "announcement":
        return await _api_get("/api/v1/app/announcement", auth_required=False)

    # ========== 以下操作需要认证：自动登录 ==========
    if not await _auto_login():
        return {"error": "未配置 UBAA_USERNAME / UBAA_PASSWORD 环境变量，请在项目根目录 .env 文件中设置后重试"}

    # ========== 博雅课程 (BYKC) ==========
    if action == "bykc_profile":
        return await _api_get("/api/v1/bykc/profile")

    if action == "bykc_courses":
        query_parts = []
        for k in ("page", "size"):
            if k in params:
                query_parts.append(f"{k}={params[k]}")
        if params.get("all"):
            query_parts.append("all=true")
        qs = "&".join(query_parts)
        path = "/api/v1/bykc/courses"
        if qs:
            path += f"?{qs}"
        return await _api_get(path)

    if action == "bykc_chosen":
        return await _api_get("/api/v1/bykc/courses/chosen")

    if action == "bykc_detail":
        course_id = params.get("course_id")
        if not course_id:
            return {"error": "bykc_detail 需要 params.course_id"}
        return await _api_get(f"/api/v1/bykc/courses/{course_id}")

    if action == "bykc_select":
        course_id = params.get("course_id")
        if not course_id:
            return {"error": "bykc_select 需要 params.course_id"}
        return await _api_post(f"/api/v1/bykc/courses/{course_id}/select")

    if action == "bykc_deselect":
        course_id = params.get("course_id")
        if not course_id:
            return {"error": "bykc_deselect 需要 params.course_id"}
        return await _api_delete(f"/api/v1/bykc/courses/{course_id}/select")

    if action == "bykc_sign":
        course_id = params.get("course_id")
        if not course_id:
            return {"error": "bykc_sign 需要 params.course_id"}
        body = {
            "signType": params.get("sign_type", 1),
            "lat": params.get("lat", 0),
            "lng": params.get("lng", 0),
        }
        return await _api_post(f"/api/v1/bykc/courses/{course_id}/sign", body=body)

    if action == "bykc_statistics":
        return await _api_get("/api/v1/bykc/statistics")

    # ========== 课堂签到 (Signin) ==========
    if action == "signin_today":
        return await _api_get("/api/v1/signin/today")

    if action == "signin_do":
        course_id = params.get("course_id")
        if not course_id:
            return {"error": "signin_do 需要 params.course_id（排课ID）"}
        return await _api_post(f"/api/v1/signin/do?courseId={course_id}")

    # ========== 课程表 (Schedule) - 4 个独立端点 ==========
    if action == "schedule_today":
        return await _api_get("/api/v1/schedule/today")

    if action == "schedule_terms":
        return await _api_get("/api/v1/schedule/terms")

    if action == "schedule_weeks":
        term_code = params.get("term_code")
        if not term_code:
            return {"error": "schedule_weeks 需要 params.term_code（学期代码，可先通过 schedule_terms 获取）"}
        return await _api_get(f"/api/v1/schedule/weeks?termCode={term_code}")

    if action == "schedule_week":
        term_code = params.get("term_code")
        week = params.get("week")
        if not term_code or week is None:
            return {"error": "schedule_week 需要 params.term_code 和 params.week"}
        return await _api_get(f"/api/v1/schedule/week?termCode={term_code}&week={week}")

    # ========== 考试 / 成绩 (需要 termCode 参数) ==========
    if action == "exam_list":
        term_code = params.get("term_code")
        if not term_code:
            return {"error": "exam_list 需要 params.term_code（学期代码，可先通过 schedule_terms 获取）"}
        return await _api_get(f"/api/v1/exam/list?termCode={term_code}")

    if action == "grade_list":
        term_code = params.get("term_code")
        if not term_code:
            return {"error": "grade_list 需要 params.term_code（学期代码，可先通过 schedule_terms 获取）"}
        return await _api_get(f"/api/v1/grade/list?termCode={term_code}")

    # ========== 空闲教室 ==========
    if action == "classroom":
        xqid = params.get("xqid", 1)
        date = params.get("date", "")
        if not date:
            return {"error": "classroom 需要 params.date（格式 yyyy-MM-dd）"}
        return await _api_get(f"/api/v1/classroom/query?xqid={xqid}&date={date}")

    # ========== SPOC 作业 (SPOC) ==========
    if action == "spoc_assignments":
        return await _api_get("/api/v1/spoc/assignments")

    if action == "spoc_detail":
        assignment_id = params.get("assignment_id")
        if not assignment_id:
            return {"error": "spoc_detail 需要 params.assignment_id"}
        return await _api_get(f"/api/v1/spoc/assignments/{assignment_id}")

    # ========== 希冀作业 (Judge) ==========
    if action == "judge_assignments":
        qs_parts = []
        if params.get("include_expired"):
            qs_parts.append("includeExpired=true")
        skip_ids = params.get("skip_course_ids")
        if skip_ids:
            if isinstance(skip_ids, list):
                for sid in skip_ids:
                    qs_parts.append(f"skipCourseId={sid}")
            else:
                qs_parts.append(f"skipCourseId={skip_ids}")
        qs = "&".join(qs_parts)
        path = "/api/v1/judge/assignments"
        if qs:
            path += f"?{qs}"
        return await _api_get(path)

    if action == "judge_detail":
        course_id = params.get("course_id")
        assignment_id = params.get("assignment_id")
        if not course_id or not assignment_id:
            return {"error": "judge_detail 需要 params.course_id 和 params.assignment_id"}
        return await _api_get(f"/api/v1/judge/courses/{course_id}/assignments/{assignment_id}")

    # ========== 场馆预约 (CGYY) ==========
    if action == "cgyy_sites":
        return await _api_get("/api/v1/cgyy/sites")

    if action == "cgyy_orders":
        page = params.get("page", 0)
        size = params.get("size", 20)
        return await _api_get(f"/api/v1/cgyy/orders?page={page}&size={size}")

    # ========== 教学评价 (Evaluation) ==========
    if action == "evaluation_list":
        return await _api_get("/api/v1/evaluation/list")

    if action == "evaluation_submit":
        courses = params.get("courses")
        if not courses:
            return {"error": "evaluation_submit 需要 params.courses（待评教课程列表）"}
        return await _api_post("/api/v1/evaluation/submit", body=courses)

    return {"error": f"未知操作: {action}"}