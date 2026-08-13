# stage2_agent.py —— 让模型真正调用工具（阶段二核心）
from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage

load_dotenv()

# ---- 1) 两个工具（先返回假数据，阶段三再换成真实 kubectl）----
@tool
def get_pods(namespace: str) -> str:
    """查询指定 Kubernetes 命名空间下有哪些 Pod 及其运行状态。
    参数 namespace：命名空间名称，例如 'default' 或 'kube-system'。"""
    return f"[{namespace}] pod-a(Running) pod-b(Running) pod-c(Pending)"


@tool
def restart_service(name: str) -> str:
    """重启某个服务。参数 name：服务名称。"""
    return f"已向 {name} 发送重启指令（模拟）"


tools = [get_pods, restart_service]
tool_map = {t.name: t for t in tools}   # 用名字快速找到对应工具


# ---- 2) 创建模型，指向 DeepSeek（OpenAI 接口兼容）----
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# 把工具“绑”给模型：模型从此知道有这两个工具可用、各自干嘛
llm_with_tools = llm.bind_tools(tools)


# ---- 3) 主循环：发问题 → 模型可能决定调工具 → 执行 → 结果喂回 → 拿最终回答 ----
def run_agent(question: str) -> str:
    messages = [HumanMessage(content=question)]
    ai_msg = llm_with_tools.invoke(messages)

    # 模型决定调工具时，ai_msg.tool_calls 不为空
    if ai_msg.tool_calls:
        for call in ai_msg.tool_calls:
            name = call["name"]          # 工具名，如 "get_pods"
            args = call["args"]          # 参数 dict，如 {"namespace": "default"}
            result = tool_map[name].invoke(args)   # 真正执行工具函数
            print(f"[调用工具] {name}({args}) -> {result}")
            # 把工具结果作为 ToolMessage 追加回对话，让模型据此组织回答
            messages.append(ai_msg)
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        # 再问一次模型，让它用工具返回的数据写出最终自然语言回答
        final = llm_with_tools.invoke(messages)
        return final.content
    else:
        return ai_msg.content


if __name__ == "__main__":
    # 试试这句（模型应该会去调 get_pods）
    print(run_agent("default 命名空间下有哪些 Pod？"))
