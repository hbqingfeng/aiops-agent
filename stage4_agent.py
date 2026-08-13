"""AI 运维助手（K8s）—— 阶段四核心模块。

封装真实的 Kubernetes 运维工具集，并提供安全层（写操作白名单 + 人工确认）。
工具覆盖：Pod 查询 / 日志 / 详情 / 事件、节点状态、Service / Ingress 网络、
Deployment 扩缩容与重启，以及综合诊断工具 troubleshoot（聚合多源数据 + RAG 知识库增强）。

模型：DeepSeek（OpenAI 兼容接口）。
"""
import ast
import os
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from kubernetes import client, config
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

# 清除可能残留的本地代理环境变量（常见于 Windows 上梯子关闭后仍留下 HTTP_PROXY=127.0.0.1:7890）
# 这些残留代理会导致 OpenAI/DeepSeek 客户端报 APIConnectionError；若你确实需要代理访问 API，可手动修改此处
for _proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_proxy_key, None)

# --- 1. 连接本机 K8s 集群 ---
try:
    config.load_kube_config()           # 读 C:\Users\你的用户\.kube\config
    v1 = client.CoreV1Api()             # 操作 Pod / Service / Node 的客户端
    apps_v1 = client.AppsV1Api()        # 操作 Deployment 的客户端
    net_v1 = client.NetworkingV1Api()   # 操作 Ingress 的客户端（网络入口）
    K8S_OK = True
except Exception as e:
    v1 = None
    apps_v1 = None
    net_v1 = None
    K8S_OK = False
    print(f"警告：未能加载 kube config（{e}）。请先启动本地 kind 集群。")

# --- 2. 安全层：写操作白名单 ---
DANGEROUS_TOOLS = {"restart_service", "scale_deployment"}

# --- 3. 系统提示词（System Prompt）---
SYSTEM_PROMPT = SystemMessage(content="""你是 Kubernetes 运维助手，必须用中文回答用户问题。
规则：
1. 当用户询问 Pod、日志、节点状态、重启服务时，必须调用对应工具获取实时数据，禁止凭训练记忆编造。
2. 需要查日志时，先确认 Pod 名称和命名空间，然后直接调用 query_logs，不要在回复里只说"我要查日志"却不调用。
3. 如果一次工具结果不足以回答，继续调用其他工具，直到能给出准确结论。
4. 你实际可调用的工具只有：get_pods / get_all_pods / query_logs / get_node_status / restart_service / describe_pod / get_events / scale_deployment / get_services / get_ingress / troubleshoot。你**不能**修改 Deployment、Pod、Service、Ingress 或任何资源配置；用户要求"修复配置"时，你只能给出修改建议，由用户手动执行。
5. restart_service 和 scale_deployment 是写操作，只能在命令行版 stage4_agent.py 执行且需要用户输入 y 确认；网页版不会执行任何写操作，也不要在网页版诱导用户确认写操作。
6. 当用户问"为什么起不来/排查/诊断/怎么回事/怎么修复"等诊断类问题时，必须先调用 troubleshoot 收集该 Pod 的多源数据（详情+事件+日志），再输出三段式报告：①根因分析 ②修复建议 ③可选执行命令（涉及写操作的只给 kubectl 命令，绝不自动执行）。
7. 回答要简洁，给出关键状态和结论即可。""")

# --- 4. 只读工具 ---
def _pod_status(p) -> str:
    """返回 Pod 更细的状态：优先取容器等待/终止的原因（如 CrashLoopBackOff），否则取 phase。"""
    for c in (p.status.container_statuses or []):
        if c.state.waiting and c.state.waiting.reason:
            return c.state.waiting.reason
        if c.state.terminated and c.state.terminated.reason:
            return c.state.terminated.reason
    return p.status.phase or "Unknown"


@tool
def get_pods(namespace: str = "default", status: str = "") -> str:
    """查询指定 Kubernetes 命名空间下有哪些 Pod 及其运行状态。
    参数 namespace：命名空间名称，例如 'default' 或 'kube-system'，默认 'default'。
    参数 status：只筛选包含该关键词的 Pod 状态（如 'Running'、'CrashLoopBackOff'、'Pending'），留空显示全部。"""
    if not K8S_OK:
        return "K8s 未连接：请先安装 Docker/kind/kubectl 并启动本地集群"
    pods = v1.list_namespaced_pod(namespace=namespace)
    items = pods.items
    if status:
        items = [p for p in items if status.lower() in _pod_status(p).lower()]
    if not items:
        return f"命名空间 {namespace} 下没有匹配的 Pod"
    lines = [f"{p.metadata.name}({_pod_status(p)})" for p in items]
    return f"[{namespace}] " + " ".join(lines)


@tool
def query_logs(namespace: str, pod_name: str) -> str:
    """查询指定 Pod 的最近日志，用于排查应用报错。
    参数 namespace：命名空间名称；参数 pod_name：Pod 名称（可先用 get_pods 查到）。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)   # 顺便读 Pod 状态
    logs = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace)
    # k8s 客户端可能返回 bytes，也可能把 bytes 包成带 b' 前缀的字符串，统一还原成干净文本
    if isinstance(logs, bytes):
        logs = logs.decode("utf-8", errors="replace")
    elif isinstance(logs, str) and logs.startswith("b'"):
        try:
            logs = ast.literal_eval(logs).decode("utf-8", errors="replace")
        except Exception:
            pass
    status = _pod_status(pod)
    text = f"[{namespace}/{pod_name}] 状态：{status}\n最近日志：\n{logs[-2000:]}"   # 截断最后 2000 字符
    hints = _explain_k8s_errors(logs + "\n" + status)   # 同时扫描日志文本与 Pod 状态原因
    if hints:
        text += "\n\n🔍 日志/状态中检测到可能的故障（中文速查）：\n" + "\n".join(hints)
    return text


@tool
def get_node_status() -> str:
    """查看集群所有节点的健康状态与是否就绪，用于判断节点是否正常。无需参数。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    nodes = v1.list_node()
    if not nodes.items:
        return "集群中没有任何节点"
    lines = []
    for n in nodes.items:
        ready = "Ready" if any(c.type == "Ready" and c.status == "True"
                               for c in n.status.conditions) else "NotReady"
        lines.append(f"{n.metadata.name}({ready})")
    return "节点状态：" + " ".join(lines)


# --- 5. 写操作工具（受安全层保护）---
@tool
def restart_service(name: str, namespace: str = "default") -> str:
    """重启指定命名空间下的某个 Deployment，触发滚动重启以生效新配置或恢复异常。
    参数 name：Deployment 名称；参数 namespace：命名空间，默认 'default'。
    注意：这是写操作，执行前会要求人工确认。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    # 给 Deployment 的 pod template 打一个 restartedAt 注解，K8s 会据此触发滚动重启
    patch = {"spec": {"template": {"metadata": {
        "annotations": {"kubectl.kubernetes.io/restartedAt": datetime.now(timezone.utc).isoformat()}
    }}}}
    apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
    return f"已触发 deployment/{name}（命名空间 {namespace}）滚动重启"


# --- 6. K8s 常见错误中文速查表 ---
ERROR_HINTS = {
    "CrashLoopBackOff": "容器反复崩溃重启：通常是应用启动报错、退出码非 0、或依赖服务连不上。看日志末尾的应用报错。",
    "ImagePullBackOff": "镜像拉取失败：镜像名写错、仓库需登录、或本地没有该镜像。检查 Pod 的 image 字段与镜像仓库权限。",
    "ErrImagePull": "镜像拉取出错（同上）：先确认镜像地址与拉取密钥。",
    "OOMKilled": "容器内存超限被系统杀掉：调大 memory limit，或排查应用内存泄漏。",
    "FailedScheduling": "调度失败：没有满足条件的节点（资源不足、污点/亲和性不匹配、PVC 未绑定等）。",
    "Pending": "Pod 一直 Pending：多半是调度失败或缺少依赖资源，结合上面原因定位。",
    "Back-off restarting": "容器在退避重试：应用持续崩溃，K8s 等待一会儿再重启。",
    "connection refused": "连接被拒绝：目标服务地址/端口不对，或对方还没起来。",
    "timeout": "超时：网络不通或依赖服务响应太慢。",
    "permission denied": "权限拒绝：多为文件权限或 SecurityContext 配置问题。",
    "Error": "日志中出现 Error：可能有业务异常，结合上下文定位。",
}


def _explain_k8s_errors(log_text: str) -> list:
    """扫描日志文本，返回命中的 K8s 常见错误中文解释。"""
    return [f"- {kw}：{msg}" for kw, msg in ERROR_HINTS.items() if kw in log_text]


@tool
def get_all_pods() -> str:
    """查看集群中所有命名空间下的全部 Pod 及其状态，用于全集群巡检。无需参数。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    pods = v1.list_pod_for_all_namespaces()
    if not pods.items:
        return "集群中没有任何 Pod"
    by_ns = defaultdict(list)
    for p in pods.items:
        by_ns[p.metadata.namespace].append(f"{p.metadata.name}({_pod_status(p)})")
    lines = [f"[{ns}] " + " ".join(ps) for ns, ps in by_ns.items()]
    return "全集群 Pod：\n" + "\n".join(lines)


@tool
def describe_pod(namespace: str, pod_name: str) -> str:
    """查看某个 Pod 的详细配置与运行状态（镜像、节点、IP、重启次数、资源规格等），用于深入排查。
    参数 namespace：命名空间；参数 pod_name：Pod 名称。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    p = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
    cs = (p.status.container_statuses or [None])[0]
    c = (p.spec.containers or [None])[0]
    img = c.image if c else "?"
    cmd = " ".join(c.command or []) if c and c.command else "（默认入口）"
    node = p.spec.node_name or "?"
    ip = p.status.pod_ip or "?"
    restarts = cs.restart_count if cs else 0
    reason = _pod_status(p)
    res = ""
    if c and c.resources:
        req = c.resources.requests or {}
        lim = c.resources.limits or {}
        if req or lim:
            res = f"  资源：requests={req} limits={lim}\n"
    return (f"[{namespace}/{pod_name}]\n"
            f"  状态：{reason}  重启次数：{restarts}\n"
            f"  节点：{node}  PodIP：{ip}\n"
            f"  镜像：{img}\n"
            f"  启动命令：{cmd}\n"
            f"  创建时间：{p.metadata.creation_timestamp}\n"
            f"{res}")


@tool
def get_events(namespace: str = "default", reason: str = "") -> str:
    """查看指定命名空间中最近的事件（Events），用于排查 Pod 调度失败、镜像拉取失败、反复重启等根因。
    参数 namespace：命名空间，默认 'default'；参数 reason：按 reason 关键词过滤（如 'Failed''Pull''BackOff'），留空显示全部。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    evs = v1.list_namespaced_event(namespace=namespace)
    if not evs.items:
        return f"命名空间 {namespace} 下最近没有事件"
    items = sorted(evs.items, key=lambda e: e.last_timestamp or e.event_time or "", reverse=True)[:20]
    lines = []
    for e in items:
        if reason and reason.lower() not in (e.reason or "").lower():
            continue
        lines.append(f"[{e.type}] {e.reason} | {e.involved_object.kind}/{e.involved_object.name}: {e.message}")
    if not lines:
        return f"命名空间 {namespace} 下没有匹配 reason='{reason}' 的事件"
    return f"[{namespace}] 最近事件（最多 20 条）：\n" + "\n".join(lines)


@tool
def scale_deployment(name: str, replicas: int, namespace: str = "default") -> str:
    """调整指定 Deployment 的副本数（扩缩容）。
    参数 name：Deployment 名称；参数 replicas：目标副本数（如 2、3）；参数 namespace：命名空间，默认 'default'。
    注意：这是写操作，执行前会要求人工确认。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body={"spec": {"replicas": replicas}})
    return f"已将 deployment/{name}（命名空间 {namespace}）副本数调整为 {replicas}"


@tool
def get_services(namespace: str = "default") -> str:
    """查看指定命名空间下的所有 Service 及其暴露方式：类型(ClusterIP/NodePort/LoadBalancer)、ClusterIP、端口、以及选择器(关联哪些 Pod)。
    参数 namespace：命名空间，默认 'default'。用于排查服务发现、流量入口、端口映射问题。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    svc = v1.list_namespaced_service(namespace=namespace)
    if not svc.items:
        return f"命名空间 {namespace} 下没有任何 Service"
    lines = []
    for s in svc.items:
        ports = ",".join(f"{p.port}/{p.protocol}" for p in (s.spec.ports or []))
        sel = s.spec.selector or {}
        sel_txt = " ".join(f"{k}={v}" for k, v in sel.items()) if sel else "（无选择器）"
        lines.append(f"{s.metadata.name}[{s.spec.type}] ClusterIP={s.spec.cluster_ip} 端口=[{ports}] 选择器={{{sel_txt}}}")
    return f"[{namespace}] Service 列表：\n" + "\n".join(lines)


@tool
def get_ingress(namespace: str = "default") -> str:
    """查看指定命名空间下的 Ingress 路由规则：域名(host)、路径(path)、以及转发到哪个 Service:端口。
    参数 namespace：命名空间，默认 'default'。用于排查外部 HTTP/HTTPS 流量如何进入集群、域名路由是否正确。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    ing = net_v1.list_namespaced_ingress(namespace=namespace)
    if not ing.items:
        return f"命名空间 {namespace} 下没有任何 Ingress"
    lines = []
    for i in ing.items:
        for r in (i.spec.rules or []):
            host = r.host or "*"
            for p in (r.http.paths if r.http else []):
                svc = p.backend.service if p.backend else None
                target = f"{svc.name}:{svc.port.number if svc and svc.port else '?'}" if svc else "?"
                lines.append(f"{i.metadata.name} host={host} path={p.path} -> {target}")
    return f"[{namespace}] Ingress 路由规则：\n" + "\n".join(lines)


@tool
def troubleshoot(namespace: str = "default", pod_name: str = "") -> str:
    """综合诊断工具：自动收集目标 Pod（或整个命名空间异常 Pod）的多源排查数据，聚合为一份摘要，供进一步根因分析。
    参数 namespace：命名空间，默认 'default'；参数 pod_name：Pod 名称，留空则诊断该命名空间下所有非 Running 的 Pod。
    内部会聚合：Pod 详情(describe_pod) + 命名空间事件(get_events) + 该 Pod 日志(query_logs)。这是只读聚合，不涉及任何写操作。"""
    if not K8S_OK:
        return "K8s 未连接：请先启动本地集群"
    # 1) 确定要诊断的 Pod 列表
    if pod_name:
        targets = [pod_name]
    else:
        pods = v1.list_namespaced_pod(namespace=namespace)
        targets = [p.metadata.name for p in pods.items if _pod_status(p) != "Running"]
        if not targets:
            return f"命名空间 {namespace} 下没有处于异常状态（非 Running）的 Pod，无需诊断"
    # 2) 逐个聚合三源数据
    #    事件拉取只需一次：get_events 返回的是整个命名空间的事件流（不按 Pod 过滤），
    #    放在循环外拉取并复用，避免多个异常 Pod 时重复请求同一份全量事件。
    try:
        evs = get_events.invoke({"namespace": namespace})
    except Exception as e:
        evs = f"（无法获取事件：{e}）"
    sections = []
    for name in targets:
        try:
            desc = describe_pod.invoke({"namespace": namespace, "pod_name": name})
        except Exception as e:
            desc = f"（无法获取详情：{e}）"
        try:
            logs = query_logs.invoke({"namespace": namespace, "pod_name": name})
        except Exception as e:
            logs = f"（无法获取日志：{e}）"
        sections.append(f"===== Pod: {name} =====\n{desc}\n\n{evs}\n\n{logs}")
    summary = (f"[诊断摘要] 命名空间 {namespace}，共 {len(targets)} 个诊断目标："
               + "\n\n".join(sections))
    # 3) RAG 增强：检索知识库中与故障相关的权威排障片段，辅助根因定位
    #    延迟 import + 异常兜底：向量库未就绪/模型下载失败时自动跳过，不影响其他工具
    try:
        from rag import retrieve
        rag_hits = retrieve(" ".join(targets) + " 故障根因 排障方法", top_k=3)
        summary += "\n\n===== 知识库参考（RAG）=====\n" + rag_hits
    except Exception as e:
        summary += f"\n\n（RAG 检索暂不可用，已跳过：{e}）"
    return summary


tools = [get_pods, query_logs, get_node_status, restart_service, get_all_pods,
         describe_pod, get_events, scale_deployment, get_services, get_ingress, troubleshoot]
tool_map = {t.name: t for t in tools}

# --- 7. 大语言模型（DeepSeek，OpenAI 兼容接口）---
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
llm_with_tools = llm.bind_tools(tools)

# --- 8. 命令行主循环（多轮工具调用 + 写操作人工确认）---
def run_agent(question: str, max_rounds: int = 5) -> str:
    messages = [SYSTEM_PROMPT, HumanMessage(content=question)]
    for _ in range(max_rounds):
        ai_msg = llm_with_tools.invoke(messages)
        if not ai_msg.tool_calls:
            return ai_msg.content

        messages.append(ai_msg)   # 把模型这次决定挂到消息链里
        for call in ai_msg.tool_calls:
            name = call["name"]
            args = call["args"]
            # 安全层：写操作需人工确认
            if name in DANGEROUS_TOOLS:
                print(f"\n⚠️ 危险操作预警：模型请求执行 {name}({args})")
                confirm = input("这是写操作，确认执行吗？（输入 y 确认，其他键取消）：").strip().lower()
                if confirm != "y":
                    result = f"已取消：用户未确认 {name} 操作"
                    print(f"[已拦截] {result}")
                    messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
                    continue
            # 正常执行工具
            result = tool_map[name].invoke(args)
            print(f"[调用工具] {name}({args}) -> {result}")
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
    return "⚠️ 工具调用轮次过多，已强制结束。请简化问题或检查 Agent 是否陷入循环。"


if __name__ == "__main__":
    # 演示 1：只读查询（默认执行，无需确认）
    print(run_agent("kube-system 命名空间下有哪些 Pod？"))
    # 演示 2：危险操作（取消下一行注释可测试「人工确认」拦截）
    # print(run_agent("请重启 default 命名空间下的 nginx 这个 Deployment"))
