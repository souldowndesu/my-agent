import asyncio,uvicorn,fastapi,time
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware #允许多端口
from contextlib import asynccontextmanager

import json,uuid
from chat_logic import AsyncLLM
import dotenv

dotenv.load_dotenv()

class SessionManager:
    def __init__(self,timeout:int=1800):
        self.active_sessions = {}
        self.timeout = timeout
    async def get_asyncllm(self,session_id:str)->AsyncLLM:
        if session_id not in self.active_sessions:
            async_llm = AsyncLLM()
            await async_llm.load_history(session_id) #首次建立连接时读取本地 json
            self.active_sessions[session_id] = {
                "llm":async_llm,
                "last_active":time.time()      #用于记录没有发生对话的时间，以便清理内存，之后也可用于llm对于时间的处理(可优化点)
            }
        else:
            self.active_sessions[session_id]["last_active"] = time.time()
        return self.active_sessions[session_id]["llm"]
    
    def update_activity(self,session_id:str):
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["last_active"] = time.time()
    
    async def save_session(self,session_id:str):
        if session_id in self.active_sessions:
            data = self.active_sessions.pop(session_id)
            # 断开连接时，将该会话内存全量写入json并使用pop清理内存
            await data["llm"].save_history(session_id,data["llm"].messages)
            print(f"会话 {session_id} 的对话内容已保存。",flush=True)
    async def save_all(self):
        for sid in list(self.active_sessions.keys()):
            await self.save_session(sid)

class StreamBroadcaster:
    def  __init__(self):
        self.clients:dict[str:list[asyncio.Queue]] = {}
        
    async def subscribe(self,session_id:str)->asyncio.Queue:
        if session_id not in self.clients:
            self.clients[session_id] = []
        queue = asyncio.Queue()
        self.clients[session_id].append(queue)
        return queue    #这个queue对象内存指向添加进去的queue对象
    
    async def unsubscribe(self,session_id:str,queue:asyncio.Queue):
        if session_id in self.clients and queue in self.clients[session_id]:
            self.clients[session_id].remove(queue)
            if not self.clients[session_id]:
                del self.clients[session_id]
    
    async def broadcast(self,session_id,message:dict):
        if session_id in self.clients:
            for queue in self.clients[session_id]:
                await queue.put(message)    #在建立联系后,所有输出内容只要进行broadcast都会同步

class ChatApp: #转发端口
    def __init__(self):
        self.app = FastAPI(lifespan=self.lifespan)  #可以使yield划分服务进行时与结束时的执行
        self.broadcaster = StreamBroadcaster()
        self.session_manager = SessionManager()
        
        self._setup_middleware()
        self._setup_routes()
        self.timeout_cleanup = True #暂时利用这个处理超过30min的任务，之后进行优化
        
    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 允许所有域名跨域（开发时最方便）
            allow_credentials=True,
            allow_methods=["*"],  # 允许所有方法 (GET, POST 等)
            allow_headers=["*"],  # 允许所有请求头
        )
    
    def _setup_routes(self):
        @self.app.post("/str-input/{session_id}") #需要将输入传输到该站点
        async def generate(session_id:str,user_input:str): 
            await self.session_manager.get_asyncllm(session_id)
            asyncio.create_task(self.llm_worker(user_input,session_id))
            return {"status":"started","session_id":session_id}

        @self.app.get("/stream/{session_id}")
        async def stream_endpoint(request:Request,session_id:str):
            print(f"[Server] {session_id} 正在建立 SSE 连接...", flush=True)
            queue = await self.broadcaster.subscribe(session_id)   #每次接受请求，都会运行这个函数，订阅并开启event_generator
            await self.session_manager.get_asyncllm(session_id) #在input执行前就尝试加载好llm端口，降低延迟
            
            async def event_generator():    #定义一个函数,用于输出迭代器
                try:
                    while True:
                        if await request.is_disconnected(): #只有主动断连,才会停止订阅
                            print(f"[Server] {session_id} 检测到正常断开(is_disconnected)",flush=True)
                            break
                        message = await queue.get()
                        yield f"data: {json.dumps(message,ensure_ascii=False)}\n\n"
                except asyncio.CancelledError:
                    print(f"[Server] {session_id} 连接被强制中断 (CancelledError)",flush=True) # 检查点
                    raise
                finally:
                    print(f"[Server] {session_id} 进入 Finally，启动后台独立清理任务...",flush=True)
                    async def safe_cleanup():   #设置独立的异步任务，防止因为cancelled导致保存过程被跳过
                        try:
                            await self.broadcaster.unsubscribe(session_id,queue)
                            await self.session_manager.save_session(session_id)
                            print(f"[Server] {session_id} 清理与保存任务彻底完成。",flush=True) # 检查点
                        except Exception as e:
                            print(f"[Server Error] {session_id} 清理时发生致命错误: {e}",flush=True)
                    
                    asyncio.create_task(safe_cleanup())
                    
            return StreamingResponse(event_generator(),media_type="text/event-stream")  #会不断返回实例化的event_generator,即对应得迭代器      
        
    @asynccontextmanager
    async def lifespan(self, app: FastAPI):#yield前会执行一次，断开服务后会执行之后的
        stop_cleanup = asyncio.Event()
        async def cleanup_loop():
            while not stop_cleanup.is_set():
                await asyncio.sleep(60)
                if self.timeout_cleanup:
                    now = time.time()
                    expired = []
                    for sid,d in self.session_manager.active_sessions.items():
                        if now - d["last_active"] > self.session_manager.timeout:
                            expired.append(sid)
                    for sid in expired:
                        await self.session_manager.save_session(sid)
        
        cleanup_task = asyncio.create_task(cleanup_loop())
        yield  # 服务运行中
        # 接收到关闭信号，执行全量保存(可以看作asynccontextmanager环境的特殊写法)
        stop_cleanup.set()
        cleanup_task.cancel()
        await self.session_manager.save_all()

    async def llm_worker(self,user_input:str,session_id:str):
        try:
            llm = await self.session_manager.get_asyncllm(session_id)   #获取对应的llm，更新一下时间记录
            await self.broadcaster.broadcast(session_id,{
                "event":"start",
                "session_id":session_id,
                "prompt":user_input
                })
            self.session_manager.update_activity(session_id) 
            async for res_word in llm.chat_stream(user_input=user_input):
                await self.broadcaster.broadcast(session_id,{
                    "event":"content",
                    "data":res_word
                })
            await self.broadcaster.broadcast(session_id,{
                "event":"end",
            })
        except Exception as e:
            await self.broadcaster.broadcast(session_id,{
                "event": "error",
                "error_msg": str(e)
            })


chat_app = ChatApp()        
if __name__ == "__main__":
    uvicorn.run("chat_server:chat_app.app",host="127.0.0.1",port=8001,reload=True,reload_excludes=["history/*", "histroy/*", "*.json"])