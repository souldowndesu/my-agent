import os

os.environ["GENIE_DATA_DIR"] = r"D:\Data\VS_code\AI-workplace\my-agent\Genie\GenieData"

import genie_tts as genie
genie.start_server(host="127.0.0.1",port=8000,workers=1)