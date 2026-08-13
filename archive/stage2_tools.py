# stage2_tools.py —— 任务 A：写出你的第一个「工具」
# 工具 = 一个普通 Python 函数 + 一段写给模型看的说明（docstring）
from langchain_core.tools import tool


@tool
def get_pods(namespace: str) -> str:
    """查询指定 Kubernetes 命名空间下有哪些 Pod 及其运行状态。
    参数 namespace：命名空间名称，例如 'default' 或 'kube-system'。"""
    # 暂时返回假数据，阶段三再换成真实 kubectl
    return f"[{namespace}] pod-a(Running) pod-b(Running) pod-c(Pending)"


# 测试：验证 @tool 是否注册成功（跑 python stage2_tools.py 看输出）
if __name__ == "__main__":
    print("工具名字：", get_pods.name)
    print("模拟调用：", get_pods.invoke({"namespace": "default"}))
