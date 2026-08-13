import os
import sys

# 让 tests/ 下的用例能 import 到项目根目录的 stage4_agent / rag
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types
import importlib

import pytest


# ---- 纯逻辑测试：不依赖真实集群、不消耗 API、不要求联网 ----

def test_rag_retrieve_hits_relevant_chunk():
    from rag import retrieve
    out = retrieve("Pod 一直 CrashLoopBackOff 怎么排查", top_k=3)
    assert "CrashLoopBackOff" in out
    assert "相关度" in out          # 说明确实命中并排序了知识片段


def test_rag_retrieve_empty_query_no_crash():
    from rag import retrieve
    out = retrieve("", top_k=1)
    assert isinstance(out, str)    # 空查询不应抛异常，应返回友好文本


def test_pod_status_detects_crashloopbackoff():
    import stage4_agent as s
    pod = types.SimpleNamespace(
        status=types.SimpleNamespace(
            container_statuses=[
                types.SimpleNamespace(
                    state=types.SimpleNamespace(
                        waiting=types.SimpleNamespace(reason="CrashLoopBackOff"),
                        terminated=None,
                    )
                )
            ],
            phase="Running",
        )
    )
    assert s._pod_status(pod) == "CrashLoopBackOff"


def test_pod_status_falls_back_to_phase():
    import stage4_agent as s
    pod = types.SimpleNamespace(
        status=types.SimpleNamespace(container_statuses=[], phase="Pending")
    )
    assert s._pod_status(pod) == "Pending"


def test_tools_count_and_names():
    import stage4_agent as s
    names = [t.name for t in s.tools]
    assert len(names) == 11
    for expected in [
        "get_pods", "get_all_pods", "query_logs", "get_node_status",
        "describe_pod", "get_events", "get_services", "get_ingress",
        "troubleshoot", "restart_service", "scale_deployment",
    ]:
        assert expected in names


def test_dangerous_tools_whitelist():
    import stage4_agent as s
    assert s.DANGEROUS_TOOLS == {"restart_service", "scale_deployment"}


def test_system_prompt_constraints():
    import stage4_agent as s
    content = s.SYSTEM_PROMPT.content
    assert "中文" in content
    assert "troubleshoot" in content
    assert "不能" in content        # 明确声明不能修改任何资源配置


def test_proxy_env_cleared_on_import():
    # 模拟残留代理（Windows 关梯子后仍可能留下 HTTP_PROXY=127.0.0.1:7890）
    os.environ["HTTP_PROXY"] = "127.0.0.1:7890"
    import stage4_agent
    importlib.reload(stage4_agent)  # 重新执行模块顶层清理逻辑
    assert "HTTP_PROXY" not in os.environ
    os.environ.pop("HTTP_PROXY", None)


def test_write_operation_returns_friendly_when_k8s_down(monkeypatch):
    import stage4_agent as s
    monkeypatch.setattr(s, "K8S_OK", False)
    result = s.tool_map["restart_service"].invoke(
        {"namespace": "default", "name": "demo"}
    )
    assert isinstance(result, str)
    assert "未连接" in result       # 断连时给出友好提示而非抛栈
