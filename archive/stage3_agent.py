# stage3_agent.py —— 把假工具换成真实 K8s 调用（阶段三核心）
from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage
from kubernetes import client, config

load_dotenv()

# ---- 0) 连上你本机的 K8s 集群（需要先装好 Docker + kind + kubectl 并起集群）----
try:
    config.load_kube_config()          # 读 C:\Users\你的用户\.kube\config
    v1 = client.CoreV1Api()            # 操作 Pod / Service 等核心资源的客户端
    K8S_OK = True
except Exception as e:
    v1 = None
    K8S_OK = False
    print(f"警告：未能加载 kube config（{e}）。get_pods 将返回错误提示。\n"
          f"请先安装 Docker Desktop + kind + kubectl，并运行 kind create cluster 起一个本地集群。")

# ---- 1) 真实工具：get_pods 现在查你电脑上真集群里真有的 Pod ----
@tool
def get_pods(namespace: str) -> str:
    """查询指定 Kubernetes 命名空间下有哪些 Pod 及其运行状态。
    参数 namespace：命名空间名称，例如 'default' 或 'kube-system'。"""
    if not K8S_OK:
        return "K8s 未连接：请先安装 Docker/kind/kubectl 并启动本地集群"
    pods = v1.list_namespaced_pod(namespace=namespace)
    if not pods.items:
        return f"命名空间 {namespace} 下当前没有任何 Pod"
    lines = [f"{p.metadata.name}({p.status.phase})" for p in pods.items]
    return f"[{namespace}] " + " ".join(lines)


@tool
def restart_service(name: str) -> str:
    """重启某个服务。参数 name：服务名称。"""
    return f"已向 {name} 发送重启指令（模拟，阶段五再接真实 kubectl rollout restart）"


tools = [get_pods, restart_service]
tool_map = {t.name: t for t in tools}

# ---- 2) 模型（DeepSeek，OpenAI 接口兼容）----
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
llm_with_tools = llm.bind_tools(tools)

# ---- 3) 主循环（和阶段二完全一样，只换了工具的实现）----
def run_agent(question: str) -> str:
    messages = [HumanMessage(content=question)]
    ai_msg = llm_with_tools.invoke(messages)
    if ai_msg.tool_calls:
        for call in ai_msg.tool_calls:
            name = call["name"]
            args = call["args"]
            result = tool_map[name].invoke(args)
            print(f"[调用工具] {name}({args}) -> {result}")
            messages.append(ai_msg)
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        final = llm_with_tools.invoke(messages)
        return final.content
    else:
        return ai_msg.content


if __name__ == "__main__":
    print(run_agent("kube-system 命名空间下有哪些 Pod？"))

