import asyncio
import json
import httpx

async def sse_event_iter(url:str=None):
    url = url or "http://127.0.0.1:8001/stream"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET",url) as response:   #stream方式获取迭代器,此时产生连接,broadcaster产生一个queue
            async for line in response.aiter_lines():   #按行读取数据
                if line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    data_str = line[6:].strip()
                    if not data_str:
                        continue    #抛弃空数据集
                    try:
                        event_data = json.loads(data_str)   #解析json为dict数据
                        yield event_data
                    except json.JSONDecodeError:
                        print(f"[解析错误] 无法解析数据: {data_str}")
                        continue
                    