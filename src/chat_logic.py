from openai import AsyncOpenAI
import dotenv,os,aiofiles,json,asyncio,inspect
from typing import List,Dict,Any,Callable
import importlib.util

dotenv.load_dotenv()

class ToolRegistry:
    def __init__(self):
        self._tool_schemas:List[Dict] = []
        self._tool_callables:Dict[str,Callable] = {}
        
    def register(self, tools_path: str):    #将目录内所有符合要求的tools进行注册
        if not os.path.exists(tools_path):
            print(f"[Registry] 未查询到目录: {tools_path}")
            return
            
        for filename in os.listdir(tools_path):
            if filename.endswith(".py") and not filename.startswith("__"):  #找到所有.py并去除隐藏文件
                module_name = filename[:-3]
                file_path = os.path.join(tools_path,filename)
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name,file_path) #动态加载模块
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    if hasattr(module,"TOOL_SCHEMA") and hasattr(module,"execute"):     #有明确格式要求，要求命名"TOOL_SCHEMA""execute"
                        schema = getattr(module,"TOOL_SCHEMA")
                        func = getattr(module,"execute")
                        name = schema.get("function",{}).get("name")

                        if not name:
                            print(f"[Registry Error] {filename} 的 TOOL_SCHEMA 缺少 function.name 字段，跳过。")
                            continue
                        # 集中装配入库
                        self._tool_schemas.append(schema)
                        self._tool_callables[name] = func
                        print(f"[System] 成功扫描并装配工具: {name} (来自 {filename})", flush=True)
                    else:
                        print(f"[System Warning] {filename} 缺失 TOOL_SCHEMA 或 execute，不符合协议，已跳过。", flush=True)
                except Exception as e:  
                    print(f"[Registry Exception] 动态加载模块 {filename} 时发生崩溃: {e}", flush=True)
                    continue
    
    def get_schema(self)->List[Dict]:
        return self._tool_schemas if self._tool_schemas else None

    async def execute(self,name:str,args:dict)->Any:    #执行对应的tool并返回
        if name not in self._tool_callables:
            raise ValueError(f"Tool '{name}' is not registered in this registry.")
        func = self._tool_callables[name]
        if inspect.iscoroutinefunction(func):
            return await func(**args)
        else:
            return await asyncio.to_thread(func, **args)

class AsyncLLM:
    def __init__(self,api_key:str=None,model:str=None,base_url:str=None,registry:ToolRegistry=None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("API_KEY"),
            base_url=base_url or os.getenv("BASE_URL")
            )
        self.model = model or os.getenv("MODEL")
        
        self.history_dir = "history"
        os.makedirs(self.history_dir,exist_ok=True)
        self.messages = [{"role":"system","content":"You are a assistant,you should reply in english,and should not use emoji or special icons/characters.Use tools when necessary."}]
        
        self.registry = registry    #注册的tools  
    
    async def chat_stream(self,user_input:str=None,message:dict=None):
        if user_input:
            self.messages.append({"role":"user","content":user_input})
        elif message:
            self.messages.append(message)
        
        while True:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                stream=True,
                tools=self.registry.get_schema() if self.registry else None
            )
        
            full_reply = ""
            tool_calls_buffer = {}   #存放碎片化的tool calls
            
            async for chunk in resp:
                if not chunk.choices: 
                    continue    #去除空块
                delta = chunk.choices[0].delta
                if delta.content:
                    word = delta.content
                    full_reply += word
                    yield {"type":"content","data":word}
                
                if delta.tool_calls: #出现了工具调用的请求
                    for tc_delta in delta.tool_calls:
                        index = tc_delta.index  #对应调用tool的标签
                        if index not in tool_calls_buffer:     #确定是新调用的tool
                            tool_calls_buffer[index] = {
                                "id":tc_delta.id,
                                "name":tc_delta.function.name,
                                "args":""
                            }
                            yield {"type":"tool_start","name":tool_calls_buffer[index]["name"]}  #只在第一次出现该工具时输出
                        if tc_delta.function.arguments:
                            tool_calls_buffer[index]["args"] += tc_delta.function.arguments #逐渐拼接tool_call的内容
                            
            assistant_msg = {"role":"assistant","content":full_reply or None}
            if tool_calls_buffer: #有调用工具
                formatted_calls = []
                for tc in tool_calls_buffer.values():
                    formatted_calls.append({
                        "id":tc["id"],
                        "type":"function",
                        "function":{"name":tc["name"],"arguments":tc["args"]}
                    })
                assistant_msg["tool_calls"] = formatted_calls
                self.messages.append(assistant_msg)
                
                for tc in formatted_calls:
                    func_name = tc["function"]["name"]
                    args_str = tc["function"]["arguments"]
                    executed_well = True
                    result_str = ""
                    
                    if not self.registry:
                        result_str = "Error: ToolRegistry is missing, cannot execute tools."
                        executed_well = False
                    
                    try:
                        args = json.loads(args_str) if args_str else {} #这里有一个防御性措施，防止非法json，也许可以调用修复模型对其进行更改
                        result_data = await self.registry.execute(func_name,args)
                        result_str = str(result_data)
                    except json.JSONDecodeError:
                        result_str = "Error: Invalid JSON arguments provided."
                        executed_well = False
                    except Exception as e:
                        result_str = f"Error executing {func_name} :{str(e)}"   #将结果返回模型
                        executed_well = False

                    yield {"type":"tool_result","name": func_name,"result_status":executed_well}
                    
                    self.messages.append({
                        "role":"tool",
                        "tool_call_id":tc["id"],
                        "name":func_name,
                        "content":result_str
                    })
                continue #循环执行，直到完成完整链路
                
            else:   #没有工具调用
                self.messages.append(assistant_msg)
                break   #此时不必继续循环
                
        
    async def load_history(self,session_id:str):
        file_path = os.path.join(self.history_dir,f"{session_id}.json")
        if os.path.exists(file_path):
            async with aiofiles.open(file_path,mode='r',encoding='utf-8') as f:
                content = await f.read()
                try:
                    messages = json.loads(content)
                    self.messages = messages
                except json.JSONDecodeError:
                    print(f"{session_id}.json无法正常解码")
                    
    async def  save_history(self,session_id:str,messages:list):
        filepath = os.path.join(self.history_dir, f"{session_id}.json")
        async with aiofiles.open(filepath, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(messages, ensure_ascii=False, indent=2))

