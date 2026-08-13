# first_call.py —— 阶段一完整版：用 Python 打通 DeepSeek API
import os
from openai import OpenAI
from dotenv import load_dotenv

# 1) 读 Key：load_dotenv() 把同目录下的 .env 文件加载进环境变量
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")   # 读环境变量（名字要和 .env 里等号左边一致）
if not api_key:
    raise SystemExit("没找到 DEEPSEEK_API_KEY，请先填 .env")

# 2) 建客户端：DeepSeek 兼容 OpenAI 接口，所以复用 OpenAI 库，只改 base_url
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

# 3) 发请求：messages 是对话列表，每条是 {role, content}
response = client.chat.completions.create(
    model="deepseek-chat",   # 模型名：最便宜的对话模型
    messages=[
        {"role": "user", "content": "用一句话解释什么是 Kubernetes"}
    ],
)

# 4) 取回答：response.choices[0].message.content 才是真正的文字
answer = response.choices[0].message.content
print(answer)
