# my-agent

一个基于 Python 异步架构的 AI 智能体系统，支持流式 LLM 对话、工具调用（Function Calling）、语音合成（TTS）以及 Web 聊天界面。

> 架构详解与开发指南请参阅 [docs/architecture.md](docs/architecture.md)

## 项目结构

```
my-agent/
├── src/
│   ├── main.py              # 主入口（预留）
│   ├── chat_logic.py        # 核心逻辑：AsyncLLM 与 ToolRegistry
│   ├── chat_server.py       # FastAPI SSE 服务端，会话管理与广播
│   ├── connnet_logic.py     # SSE 流式客户端（断线重连）
│   ├── genie_server.py      # Genie TTS 服务启动
│   ├── tts.py               # TTS 音频播放管线
│   ├── webui.py             # Web UI 入口
│   └── registry.py          # 工具注册中心实例化
├── tools/
│   └── bash_tool.py         # Bash 执行工具（通过 WSL2）
├── utils/
│   ├── convert2onnx.py      # Genie 模型转 ONNX 工具
│   └── genie_data_download.py # Genie 模型数据下载脚本
├── webui_resource/
│   ├── index.html           # Web 聊天界面
│   ├── script.js            # 前端交互逻辑
│   └── style.css            # 前端样式
├── docs/
│   └── architecture.md      # 架构设计与开发指南
├── requirements.txt         # 项目依赖
└── readme.md
```

## 功能特性

- **流式 LLM 对话**：基于 SSE（Server-Sent Events）协议实现实时流式文本输出
- **工具调用（Function Calling）**：支持动态注册工具，LLM 可自动调用外部工具完成复杂任务
- **广播架构**：一个 LLM 生成的输出可同时广播给多个客户端（支持多端同步监听）
- **会话管理**：自动管理会话生命周期，支持 30 分钟超时自动清理，会话历史持久化到本地 JSON
- **TTS 语音合成**：集成 Genie TTS 引擎，支持流式文本转语音，异步队列缓存机制
- **Web 聊天界面**：提供简洁的 Web UI，支持多会话管理
- **断线重连**：SSE 流式客户端支持自动重连

## 快速开始

### 环境要求

- Python 3.10+
- 如需 TTS 功能：需要 PyAudio 及 Genie TTS 模型

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

创建 `.env` 文件：

```
API_KEY=your_openai_api_key
BASE_URL=your_api_base_url
MODEL=your_model_name
```

### 下载 TTS 模型（可选）

如需使用语音合成功能，先下载 Genie 模型：

```bash
python utils/genie_data_download.py
```

### 启动服务

**1. 启动 TTS 服务**（可选）：

```bash
python src/genie_server.py
```

**2. 启动 LLM SSE 服务**：

```bash
python src/chat_server.py
```

服务默认运行在 `http://127.0.0.1:8001`

**3. 启动 Web 界面**：

```bash
python src/webui.py
```

## API 接口

### POST /str-input/{session_id}

向指定会话发送用户输入。

- **参数**：`session_id` - 会话标识，`user_input` - 用户输入的文本
- **返回**：`{"status": "started", "session_id": "..."}`

### GET /stream/{session_id}

建立 SSE 连接，订阅指定会话的流式输出。

- **参数**：`session_id` - 会话标识
- **返回**：`text/event-stream` 格式的流式响应

SSE 事件类型：

| 事件类型 | 说明 |
|---------|------|
| `start` | 开始处理用户输入 |
| `content` | 流式文本内容片段 |
| `tool_status` (start) | 开始调用工具 |
| `tool_status` (result) | 工具执行结果返回 |
| `end` | LLM 本轮响应结束 |
| `error` | 发生错误 |

## 自定义工具

在 `tools/` 目录下创建新的 Python 文件，遵循以下协议：

```python
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "工具描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数描述"}
            },
            "required": ["param1"]
        }
    }
}

async def execute(param1: str):
    # 工具实现逻辑
    return "执行结果"
```

工具会在服务启动时自动注册，无需手动配置。

## 现有工具

| 工具名称 | 描述 | 文件 |
|---------|------|------|
| `execute_bash` | 在 WSL2 Ubuntu 中执行 Bash 命令 | `tools/bash_tool.py` |

## 依赖项

- `uvicorn` / `fastapi`：Web 服务框架
- `openai`：LLM API 客户端
- `httpx`：异步 HTTP 客户端
- `aiofiles`：异步文件操作
- `python-dotenv`：环境变量管理
- `genie_tts`：TTS 语音合成引擎
- `pyaudio`：音频播放

## 技术亮点

- 全异步架构（`asyncio`），支持高并发连接
- 广播模式实现一对多流式分发，支持多端实时监听同一会话
- 动态模块加载机制，工具即插即用
- 会话断连时自动异步持久化，防止数据丢失
- SSE 客户端内置断线重连机制
- 支持 reasoning_content（思维链）透传

## 进一步阅读

- [架构设计与开发指南](docs/architecture.md)

## AI生成/需要验证的代码

AI生成：
- Tools 中的相关工具
- webui_resource 中的所有代码
