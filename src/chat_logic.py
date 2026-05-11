from openai import AsyncOpenAI
import dotenv,os,aiofiles,json
dotenv.load_dotenv()

class AsyncLLM:
    def __init__(self,api_key:str=None,model:str=None,base_url:str=None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("API_KEY"),
            base_url=base_url or os.getenv("BASE_URL")
            )
        self.model = model or os.getenv("MODEL")
        
        self.history_dir = "history"
        os.makedirs(self.history_dir,exist_ok=True)
        self.messages = [{"role":"system","content":"You are a assistant,you should reply in english,and should not use emoji or special icons/characters"}]
        
    async def chat_stream(self,user_input:str,message:dict=None):
        if not message:
            self.messages.append({"role":"user","content":user_input})
        else:
            self.messages.append(message)
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            stream=True
        )
        
        full_reply = ""
        async for chunk in resp:
            if chunk.choices[0].delta.content:
                word = chunk.choices[0].delta.content
                full_reply += word
                yield word
                
        self.messages.append({"role":"assistant","content":full_reply})
        
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

