"""
时间工具
提供获取当前本地系统时间的功能。
AI 可自行根据时区偏移量换算到其他时区。
"""
from datetime import datetime


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": (
            "获取当前本地系统时间和日期。"
            "返回本地日期、时间、星期、Unix 时间戳和 UTC 偏移量。"
            "无参数，直接返回系统本地时间。"
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


async def execute():
    """获取当前本地系统时间和日期，无参数。"""
    now = datetime.now().astimezone()
    tz = now.tzinfo
    tz_name = tz.tzname(now) if tz else "Unknown"
    utc_offset = now.strftime("%z")

    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_cn[now.weekday()]

    return (
        f"📅 日期: {now.strftime('%Y-%m-%d')} ({weekday})\n"
        f"⏰ 时间: {now.strftime('%H:%M:%S')}\n"
        f"🌍 时区: {tz_name} (UTC{utc_offset})"
    )