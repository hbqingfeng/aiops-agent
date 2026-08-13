# chat_bot.py —— 阶段一升级版：system 人设 + 多轮记忆 + 流式输出
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

# system prompt：给模型立人设、定规矩。这是 Agent "性格"的来源
SYSTEM_PROMPT = """你是一个资深 Kubernetes 运维助手。
- 用简洁的中文回答
- 涉及命令时用代码块给出
- 不确定的事明确说不知道，不要编造"""

# messages 一开始就放 system；之后每轮追加 user / assistant
messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def chat(user_input: str) -> str:
    """发一句话给模型，流式打印回答，并把双方消息记入历史（维持多轮上下文）。"""
    messages.append({"role": "user", "content": user_input})

    # stream=True：回答被切成很多小块逐块返回，不用等全部生成完
    stream = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        stream=True,
    )

    print("助手：", end="", flush=True)
    full = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""  # 这一小块新增的文字
        print(delta, end="", flush=True)
        full += delta
    print()

    messages.append({"role": "assistant", "content": full})
    return full


if __name__ == "__main__":
    print("（输入 exit 退出）")
    while True:
        u = input("你：")
        if u.strip().lower() == "exit":
            break
        chat(u)
