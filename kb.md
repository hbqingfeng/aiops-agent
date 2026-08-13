# Kubernetes 常见故障排障知识库

本知识库用于运维 Agent 的 RAG 检索增强：当用户请求诊断 Pod 故障时，Agent 会先检索这里最相关的权威片段，再结合集群实时数据给出根因分析与修复建议。

## CrashLoopBackOff

CrashLoopBackOff 表示容器启动后很快退出（退出码非 0），Kubernetes 反复重启它，并采用指数退避等待。常见根因：
1. 应用启动报错：如缺少依赖、配置项错误、端口被占用。看容器日志末尾的应用报错。
2. 启动命令/参数错误：传入了应用不认识的命令行参数，进程直接报错退出。
3. 依赖服务连不上：如数据库、缓存未就绪，应用启动阶段连接失败退出。
4. 探针（livenessProbe）配置过严：应用还没起来就被杀掉重启。
排查步骤：先 `kubectl logs <pod>` 看应用报错；再 `kubectl describe pod <pod>` 看启动命令与退出码；最后结合 Events 判断。修复通常是修正镜像启动参数、配置或依赖。

## ImagePullBackOff / ErrImagePull

镜像拉取失败，Pod 无法启动。常见根因：
1. 镜像名或 tag 写错（拼写错误、tag 不存在）。
2. 私有仓库未配置拉取密钥（imagePullSecrets）。
3. 节点无法访问镜像仓库（网络不通、仓库地址错误、仓库需登录）。
4. 镜像过大拉取超时。
排查：`kubectl describe pod` 的 Events 会显示 FailedToPullImage 及具体原因。修复：修正 image 字段、配置 imagePullSecrets、确认节点网络可达仓库。

## OOMKilled

容器被系统因内存超限杀死（退出码 137）。根因：容器实际使用内存超过了设置的 memory limit。排查：`kubectl describe pod` 的 Last State 会显示 OOMKilled 及 reason。修复：
1. 调大 memory limit（resources.limits.memory）。
2. 排查应用内存泄漏。
注意：若未设 limit，容器可能吃掉节点全部内存影响其他负载；务必设置合理的 requests/limits。

## FailedScheduling

Pod 调度失败，一直 Pending，没有节点能容纳它。常见原因：
1. 资源不足：节点剩余 CPU/内存不满足 Pod 的 requests。
2. 污点（Taint）/亲和性（Affinity）：节点有污点但 Pod 没有对应容忍，或亲和性规则过严。
3. PVC 未绑定：Pod 依赖的持久卷声明处于 Pending。
4. nodeSelector 不匹配任何节点。
排查：`kubectl describe pod` 的 Events 会写清为何不可调度。修复：调整 requests、加容忍、修正亲和性或扩容节点。

## Pod 一直处于 Pending

Pod 已被 API 接受但没调度到节点。最常见就是 FailedScheduling（资源/污点/亲和性）。其他原因：
1. 等待被抢占（preemption）或优先级问题。
2. 控制面组件异常。
优先看 Events 中的调度失败原因，按 FailedScheduling 处理。

## Back-off restarting failed container (BackOff)

这是 Events 中的一条警告，含义是容器反复崩溃后 Kubernetes 在退避等待，随后再次重启。它通常是 CrashLoopBackOff 的前兆或直接表现。根因与 CrashLoopBackOff 一致：应用持续崩溃退出。结合日志定位应用报错。

## 资源 requests 与 limits 配置建议

resources.requests 是调度依据（节点需有足够空闲资源才允许调度），resources.limits 是运行上限（CPU 可 throttling，内存超了会被 OOMKilled）。建议：
1. 为每个容器都设置 requests 和 limits，避免资源争抢与节点雪崩。
2. requests 贴近真实均值，limits 留一定余量。
3. 内存 limit 务必设置，防止单容器拖垮节点。

## 滚动重启（Rolling Restart）

修改了 Deployment 配置后，可用滚动重启让新配置生效，且不中断服务：
`kubectl rollout restart deployment/<name> -n <ns>`
原理是给 Pod 模板打一个 restartedAt 注解，触发逐 Pod 替换。若需紧急回滚到上一版本：
`kubectl rollout undo deployment/<name> -n <ns>`

## 探针（Probe）配置

livenessProbe 失败会重启容器；readinessProbe 失败会把 Pod 从 Service 端点摘掉（不接流量）但不重启；startupProbe 用于启动慢的应用，避免被 liveness 误杀。探针过严（initialDelaySeconds 太短、阈值太低）会造成应用还没就绪就被反复重启，表现为 CrashLoopBackOff。配置探针应预留足够启动时间。

## 查看日志与事件

`kubectl logs <pod>` 看容器标准输出；`kubectl logs <pod> -p` 看上一个已退出容器的日志（对排查崩溃尤其重要）。`kubectl describe pod <pod>` 查看详情与 Events。Events 是排障金矿：镜像拉取失败、调度失败、重启退避等根因都在其中。
