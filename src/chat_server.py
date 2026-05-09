import asyncio,uvicorn,fastapi
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware #允许多端口
import json,uuid
from chat_logic import AsyncLLM
import dotenv

dotenv.load_dotenv()

class StreamBroadcaster:
    def  __init__(self):
        self.clients: list[asyncio.Queue] = []
        
    async def subscribe(self)->asyncio.Queue:
        queue = asyncio.Queue()
        self.clients.append(queue)
        return queue    #这个queue对象内存指向添加进去的queue对象
    
    async def unsubscribe(self,queue:asyncio.Queue):
        if queue in self.clients:
            self.clients.remove(queue)
    
    async def broadcast(self,message:str):
        for queue in self.clients:
            await queue.put(message)    #在建立联系后,所有输出内容只要进行broadcast都会同步

broadcaster = StreamBroadcaster()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名跨域（开发时最方便）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法 (GET, POST 等)
    allow_headers=["*"],  # 允许所有请求头
)
llm = AsyncLLM()
   
async def llm_worker(user_input:str,task_id:id):
    try:
        await broadcaster.broadcast({
            "event": "start",
            "task_id": task_id,
            "prompt": user_input
            })
        async for res_word in llm.chat_stream(user_input=user_input):
            await broadcaster.broadcast({
                "event": "content",
                "task_id": task_id,
                "data": res_word
            })
        await broadcaster.broadcast({
            "event": "end",
            "task_id": task_id
        })
    except Exception as e:
        await broadcaster.broadcast({
            "event": "error",
            "task_id": task_id,
            "error_msg": str(e)
        })

@app.post("/str-input") #需要将输入传输到该站点
async def generate(user_input:str): 
    task_id = str(uuid.uuid4())
    asyncio.create_task(llm_worker(user_input,task_id))
    return {"status": "started", "task_id": task_id, "message": "生成已触发并开始广播"}

@app.get("/stream")
async def stream_endpoint(request:Request):
    queue = await broadcaster.subscribe()   #每次接受请求，都会运行这个函数，订阅并开启event_generator
    
    async def event_generator():    #定义一个函数,用于输出迭代器
        try:
            while True:
                if await request.is_disconnected(): #只有主动断连,才会停止订阅
                    break
                message = await queue.get()
                yield f"data: {json.dumps(message,ensure_ascii=False)}\n\n"
        finally:
            await broadcaster.unsubscribe(queue)
    
    return StreamingResponse(event_generator(),media_type="text/event-stream")  #会不断返回实例化的event_generator,即对应得迭代器        
        
if __name__ == "__main__":
    uvicorn.run(app,host="127.0.0.1",port=8001)