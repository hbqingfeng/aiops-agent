# 演示视频录制指南（本机操作）

目的：录一段「**真实故障 → 真实诊断**」的演示，作为复试 / 简历展示素材。
沙箱无法录屏，以下步骤全部在你**本机**完成，预计 15 分钟录完。

---

## 前置条件

- Docker Desktop 已启动，`kind get clusters` 能看到 `aiops`
- 已 `copy .env.example .env` 并填入真实 `DEEPSEEK_API_KEY`
- 调 DeepSeek API 若超时，先设代理（梯子端口按你实际填）：
  ```cmd
  set HTTP_PROXY=http://127.0.0.1:7890
  set HTTPS_PROXY=http://127.0.0.1:7890
  ```

---

## 录制步骤

### 1. 造一个会崩溃的 Pod（演示素材）
```cmd
cd C:\Users\21847\Desktop\aiops-agent
kubectl apply -f crash-test.yaml
```
验证它真的崩了：
```cmd
kubectl get pods
```
应看到 `crash-demo` 状态为 `CrashLoopBackOff`。

### 2. 启动网页版
```cmd
venv\Scripts\python.exe stage5_web.py
```
浏览器打开 `http://127.0.0.1:7860`。（网页版只读，不会改你集群，放心演示）

### 3. 开始录屏
推荐 **OBS Studio**（免费）或系统自带录屏（Win+G 打开 Xbox 游戏栏）。
录屏前把无关窗口关掉，只留：浏览器（左）+ 终端（右）。

### 4. 按这个顺序问（最出彩）
| 顺序 | 你输入 | Agent 会做什么 |
|---|---|---|
| ① | `default 下哪个 Pod 是 CrashLoopBackOff？` | 调 `get_pods(status="CrashLoopBackOff")`，列出崩溃 Pod |
| ② | `诊断 default 下的 crash-demo，它为什么起不来？` | 调 `troubleshoot` 聚合详情+事件+日志+知识库，输出三段式报告（根因→修复建议→kubectl 命令） |
| ③（可选） | `看看它的日志` / `节点状态正常吗？` | 调 `query_logs` / `get_node_status`，展示多轮串联 |

第 ② 步是整个演示的**高光**，建议在它输出时稍作停顿、把结论念出来。

### 5. 清理演示 Pod
```cmd
kubectl delete -f crash-test.yaml
```

---

## 录屏要点

- **别露个人信息**：关掉微信/QQ/邮件等，录屏窗口只留浏览器 + 终端。
- **控制时长**：2~3 分钟最佳，太长老师没耐心。
- **念出关键结论**：比如“它崩溃是因为启动参数写错了，知识库里 CrashLoopBackOff 第 2 条根因对得上”。
- **结尾可展示**：GitHub 仓库页面 / README 架构图，证明这是完整项目。

---

## 备选：命令行版演示

想展示「写操作需人工确认」这条安全设计，用命令行版：
```cmd
venv\Scripts\python.exe stage4_agent.py
```
问同样的问题；若问到“重启 crash-demo 的 deployment”，会要求你输入 `y` 才执行——
这能直观体现**安全层**，比网页版多一层看点。

---

## 录制完成后

- 视频存本地即可（不必进仓库，体积大且含屏幕信息）。
- 复试时直接播放，或上传到 B 站 / 腾讯视频拿个链接放进简历。
- 仓库里这份 `DEMO_GUIDE.md` 只是给你自己看的步骤，不会泄露任何隐私。
