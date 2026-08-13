"""AI 运维助手（K8s）—— 阶段五网页界面。

基于 Gradio 为阶段四的 Agent 套一层网页聊天界面：
- 复用 stage4_agent 的全部工具 / 模型 / 安全层开关；
- 网页版默认拦截写操作（DANGEROUS_TOOLS），仅命令行版可人工确认执行；
- 通过自定义 CSS / JS 修复 AI 思考时出现的双滚动条，保留右下角 processing 计时。
"""
import gradio as gr
from langchain_core.messages import HumanMessage, ToolMessage

# 复用阶段四写好的全部能力：工具、模型、安全层开关
from stage4_agent import (
    DANGEROUS_TOOLS,
    SYSTEM_PROMPT,
    llm_with_tools,
    tool_map,
)


def web_agent(message: str, history=None) -> str:
    """Gradio 聊天接口：用户提问 -> Agent 思考/调工具 -> 返回回答 + 工具调用过程。"""
    try:
        messages = [SYSTEM_PROMPT, HumanMessage(content=message)]
        log_lines = []                      # 收集本次调用了哪些工具，方便界面展示
        max_rounds = 5                      # 防止模型无限循环

        for _ in range(max_rounds):
            ai_msg = llm_with_tools.invoke(messages)
            if not ai_msg.tool_calls:
                answer = ai_msg.content
                break

            messages.append(ai_msg)         # 把模型这次决定挂到消息链里
            for call in ai_msg.tool_calls:
                name = call["name"]
                args = call["args"]
                # 网页暴露在浏览器里，写操作默认拦截，必须走命令行版人工确认
                if name in DANGEROUS_TOOLS:
                    result = (f"⚠️ {name} 是写操作，网页版出于安全默认不执行。"
                              f"请用命令行版 stage4_agent.py 跑（含人工确认）。")
                    log_lines.append(f"[已拦截] {name}({args})")
                else:
                    result = tool_map[name].invoke(args)
                    log_lines.append(f"[调用工具] {name}({args}) -> {result}")
                messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        else:
            answer = "⚠️ 工具调用轮次过多，已强制结束。"

        # 把工具调用过程拼在回答下面，让你清楚 Agent 替你干了啥
        if log_lines:
            answer += "\n\n---\n🔧 本次工具调用：\n" + "\n".join(log_lines)
        return answer
    except Exception as e:
        return (f"❌ 执行出错：{type(e).__name__}: {e}\n\n"
                f"常见原因：\n"
                f"1. 本地 kind 集群没启动；\n"
                f"2. 问题缺少必要参数（如没写命名空间）。\n"
                f"建议重启 stage5_web.py 后再试，或先指定命名空间，例如：'kube-system 有哪些 Pod？'")


# 修复 Gradio 在 AI 思考时出现双滚动条：
# 1) 只保留 .chatbot 最外层一条纵向滚动条，内部嵌套容器滚动条视觉上隐藏
# 2) 处理中 Gradio 会在聊天里插入一个「空的思考气泡」，它把聊天撑高、多出一条滚动条。
#    用 JS 把这个空气泡藏掉（右下角 processing 计时器是独立元素，不受影响、照常显示）。
custom_css = """
.chatbot {
    overflow-y: auto !important;
    overflow-x: hidden !important;
}
.chatbot * {
    scrollbar-width: none !important;
}
.chatbot *::-webkit-scrollbar {
    display: none !important;
}
"""

custom_js = """
(function () {
  function hidePendingBubbles() {
    var cb = document.querySelector('.chatbot');
    if (!cb) return;
    var msgs = cb.querySelectorAll('.message');
    msgs.forEach(function (m) {
      var t = (m.textContent || '').replace(/\\s/g, '');
      // 空内容或只剩省略号的，就是处理中的占位气泡，藏掉
      if (t === '' || /^\\.*$/.test(t) || t === '…') {
        m.style.display = 'none';
      } else {
        m.style.display = '';   // 真正有内容时恢复显示
      }
    });
  }
  hidePendingBubbles();
  var obs = new MutationObserver(hidePendingBubbles);
  obs.observe(document.body, { childList: true, subtree: true });
  setInterval(hidePendingBubbles, 300);
})();
"""

with gr.Blocks() as demo:
    gr.ChatInterface(
        fn=web_agent,
        title="AI 运维助手（K8s）",
        description="用自然语言查询你的 Kubernetes 集群。只读操作可直接查；写操作请走命令行版。",
        show_progress="minimal",
    )

if __name__ == "__main__":
    # server_name 绑本机，share=False 不暴露公网，避免别人能操控你的集群
    # 注意：Gradio 6.0 起 css / js 必须传给 launch()，写在 Blocks() 里不生效
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False,
                css=custom_css, js=custom_js)
