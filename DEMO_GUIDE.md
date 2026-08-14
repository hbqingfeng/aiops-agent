# 演示视频录制备忘

这是给项目录制「真实故障 → 真实诊断」演示时的步骤备忘，用于复试 / 简历展示。预计 10~15 分钟完成。

---

## 前置条件

- Docker Desktop 已启动，`kind get clusters` 能看到 `aiops`
- 已 `copy .env.example .env` 并填入真实 `DEEPSEEK_API_KEY`
- 若 DeepSeek API 超时，先设置代理（端口按实际情况填）：
  ```cmd
  set HTTP_PROXY=http://127.0.0.1:7890
  set HTTPS_PROXY=http://127.0.0.1:7890
  ```

---

## 录制步骤

### 1. 造一个会崩溃的 Pod

```cmd
cd C:\Users\21847\Desktop\aiops-agent
kubectl apply -f crash-test.yaml
```

验证状态：

```cmd
kubectl get pods
```

应看到 `crash-demo` 状态为 `CrashLoopBackOff`。

### 2. 启动网页版

```cmd
venv\Scripts\python.exe stage5_web.py
```

浏览器打开 `http://127.0.0.1:7860`。网页版只读，不会修改集群配置。

### 3. 录屏

推荐 OBS Studio，也可用 Win + G 的系统录屏。录前把无关窗口关掉，只留浏览器和终端。

### 4. 按这个顺序提问

| 顺序 | 提问 | 预期行为 |
|------|------|----------|
| ① | `default 下哪个 Pod 是 CrashLoopBackOff？` | 调用 `get_pods`，列出崩溃 Pod |
| ② | `诊断 default 下的 crash-demo，它为什么起不来？` | 调用 `troubleshoot`，聚合详情 + 事件 + 日志 + 知识库，输出根因、修复建议、kubectl 命令 |
| ③（可选） | `看看它的日志` / `节点状态正常吗？` | 调用 `query_logs` / `get_node_status`，展示多轮串联 |

第 ② 步是演示重点，输出结论时可稍作停顿并口述一遍。

### 5. 清理

```cmd
kubectl delete -f crash-test.yaml
```

---

## 录屏要点

- 关掉微信、QQ、邮件等，窗口只留浏览器和终端。
- 时长控制在 2~3 分钟。
- 口述关键结论，例如：崩溃原因是启动参数错误，知识库中 CrashLoopBackOff 的根因判断与此一致。
- 结尾可展示 GitHub 仓库和 README 架构图，说明这是完整项目。

---

## 命令行版备选

若想展示「写操作需人工确认」的安全设计，可用命令行版：

```cmd
venv\Scripts\python.exe stage4_agent.py
```

问同样的问题；若涉及重启 deployment，会要求输入 `y` 才执行。

---

## 录制完成后

- 视频存本地即可，不进仓库。
- 复试时直接播放，或上传到 B 站 / 腾讯视频，把链接放进简历。
