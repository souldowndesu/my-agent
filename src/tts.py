from pyaudio import PyAudio
import pyaudio,httpx,re
import asyncio
from connnet_logic import sse_event_iter

class AudioPlayer:
    def __init__(self,sample_rate=32000,cable_output=False,vdevice_name="Voicemeeter AUX Input"):
        self.p = PyAudio()
        
        tgt_vdevice = None
        if cable_output:
            for i in range(self.p.get_device_count()):
                dev_info = self.p.get_device_info_by_index(i)
                if vdevice_name in dev_info["name"]:
                    tgt_vdevice = i
                    break
            if tgt_vdevice is None:
                print("无对应虚拟声卡")
        
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            rate=sample_rate,
            channels=1,
            output=True,
            output_device_index=tgt_vdevice
        )
        self.residue = b""
        print("声卡准备就绪")
        
    def write(self,chunk):
        data = self.residue + chunk
        if len(data)%2!=0:
            valid_data = data[:-1]
            self.residue = data[-1:]
        else:
            valid_data = data
            self.residue = b""
        if valid_data:      #鲁棒性加强
            try:    
                self.stream.write(valid_data)
            except Exception as e:
                print(f"[error]:{e}")    
    def close(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

async def init_genie_async(chara_name, onnx_dir, ref_audio_pth, ref_text, lang="zh", base_url=None):
    base_url =base_url or "http://127.0.0.1:8000"
        
    load_payload = {
        "character_name":chara_name,  
        "onnx_model_dir":onnx_dir,
        "language":lang,
    }
    ref_payload = {
        "character_name":chara_name,
        "audio_path":ref_audio_pth,
        "audio_text":ref_text,
        "language":lang
    }

    #使用 httpx 进行异步网络请求
    async with httpx.AsyncClient() as client:
        resp1 = await client.post(f"{base_url}/load_character", json=load_payload)
        resp1.raise_for_status()
        print("模型加载完毕")
        
        resp2 = await client.post(f"{base_url}/set_reference_audio", json=ref_payload)
        resp2.raise_for_status()
        print("参考加载完毕")
        
class GenieWorker:
    def __init__(self, player, base_url=None):
        self.text_queue = asyncio.Queue()  #使用队列缓存,防止阻塞text内容的输出
        self.audio_queue = asyncio.Queue()  #防止播放阻塞生成
        self.player = player
        self.base_url = base_url or "http://127.0.0.1:8000"
        
        #维持一个长连接客户端,获取生成的音频
        self.client = httpx.AsyncClient(timeout=None)
        
        self.req_task = None
        self.play_task = None

    async def start(self):
        #启动,由于async需要,需要异步def
        self.req_task = asyncio.create_task(self._request_worker()) #创建两个while True程序,每次达到安排的时候都进行操作
        self.play_task = asyncio.create_task(self._play_worker())
        
    async def _request_worker(self):      
        while True:
            task = await self.text_queue.get()
            if task is None:    #收到结束信号,级联通知播放协程结束
                await self.audio_queue.put(None)
                self.text_queue.task_done()
                break
            
            sentence,name = task
            tts_payload = {
                "character_name":name,
                "text":sentence,
                "split_sentence":True,
            }

            try:  #异步流式读取
                async with self.client.stream("POST", f"{self.base_url}/tts", json=tts_payload) as response:
                    response.raise_for_status()

                    async for chunk in response.aiter_bytes(chunk_size=1024):
                        if chunk:
                            await self.audio_queue.put(chunk)
            except Exception as e:
                print(f"[error]:{e}")            
            finally:
                self.text_queue.task_done()
        
    async def _play_worker(self):
        while True:
            chunk = await self.audio_queue.get()
            if chunk is None:
                self.audio_queue.task_done()
                break
            
            await asyncio.to_thread(self.player.write, chunk)   #将palyer放入异步池,防止播放引起的阻塞(播放过程无法异步)
            self.audio_queue.task_done()
        
    async def wait_finish(self):  #确保队列为空时才结束
        await self.text_queue.join()
        await self.audio_queue.join()
    
    async def speak(self, sentence, chara_name):  #加入到text队列，线程立即处理并交由player播放，相当于整条pipline的起始
        await self.text_queue.put((sentence, chara_name))
    
    async def close(self): 
        print("退出线程")
        await self.text_queue.put(None)     #对于thread来说为终止符
        if self.req_task:
            await self.req_task
        if self.play_task:
            await self.play_task
        await self.client.aclose()
 
async def deal_event(event_iter,tts_worker:GenieWorker):
    #将单词积累为完整句子
    buffer = ""
    punctuation = re.compile(r"[，。！？、,.!?\n]")
    
    print("[Agent]已准备好接收事件...")
    async for event in event_iter:
        event_type = event.get("event")
        if event_type == "start":
            buffer = ""
            print("[Agent]收到 Start 信号，大模型开始思考...")
        elif event_type == "content":
            word = event.get("data","")
            buffer += word
            if punctuation.search(word): #找到对应的标点符号
                if buffer.strip():
                    await tts_worker.speak(buffer.strip(), chara_name='37')
                buffer = ""
        elif event_type == "end":
            if buffer.strip():
                await tts_worker.speak(buffer.strip(), chara_name='37') #将可能的断句输入
                buffer = ""
       
async def main():
    onnx_path = r"D:\Data\VS_code\AI-workplace\my-agent\Genie\CharacterModels\v2ProPlus\thirtyseven\tts_models"
    ref_audio_path = r"D:\Data\VS_code\AI-workplace\my-agent\Genie\CharacterModels\v2ProPlus\thirtyseven\prompt_wav\En_play_hero3066_fightingvoc_19.wav"
    ref_text = "And now, I belong to this set."
    
    event_iter = sse_event_iter()   #会保持挂起,不会中断,因为总有可能会有新的数据到来
    await init_genie_async(chara_name="37",onnx_dir=onnx_path,ref_audio_pth=ref_audio_path,ref_text=ref_text,lang="en")
    player = AudioPlayer()
    tts_worker = GenieWorker(player)
    await tts_worker.start()
    try:
        await deal_event(event_iter,tts_worker)
    except Exception as e:
        print(f"error:{e}")
    finally:
        await tts_worker.close()
        player.close()

if __name__ == "__main__":
    asyncio.run(main())
        