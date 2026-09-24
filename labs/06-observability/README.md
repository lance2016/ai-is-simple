# 实战篇 06：看见 Agent 的运行轨迹

![Agent 的一次运行如何形成 Trace](../../assets/lab-06-observability.png)

> **一句话总结：一条 Trace 把一次任务串起来，每个 Span 都记录其中一步发生了什么、花了多久。**

**本实战新增：** Phoenix 的 OpenTelemetry 接入，以及一个轻量事件桥，把模型请求和工具执行放进同一条轨迹；Agent Loop 不变。

## 先看图

- 外层 `Trace` 代表用户交给 Agent 的一次任务。
- `LLM`、工具和结果是这次任务里的步骤，也就是 `Span`。
- 时间线能看出每一步的先后、耗时和错误位置。
- 本实战用 Phoenix 浏览这些记录；网页仍负责展示实时过程和授权。

## 用生活例子理解

把一次 Agent 任务想成一张维修工单。工单是 Trace；接单、检查、换零件是 Span。只看最后的“已修好”不知道中间发生了什么，时间线能帮你找到耗时或出错的步骤。

## 用 Docker 启动 Phoenix

项目提供独立的 Compose 配置：Phoenix 保存轨迹到 Postgres，数据库数据放在 Docker volume 里。Postgres 只在 Compose 内部开放；Phoenix 页面和接收轨迹的端口只绑定本机。这个练习不需要 Redis。

在项目根目录运行：

```bash
docker compose -f labs/06-observability/compose.yaml up -d
```

检查容器状态：

```bash
docker compose -f labs/06-observability/compose.yaml ps
```

首次启动会运行数据库迁移，需要等 Phoenix 状态变为 `healthy`。迁移期间页面可能暂时返回 502；可查看 `docker compose -f labs/06-observability/compose.yaml logs -f phoenix`，等日志显示服务已启动后再刷新。

打开 <http://127.0.0.1:6006>。想停止 Phoenix：

```bash
docker compose -f labs/06-observability/compose.yaml down
```

`down` 会保留轨迹数据；如需从头练习，在 compose 命令后加 `-v` 会删除这个练习的数据库 volume 和其中的轨迹。

默认页面端口是 `6006`，接收 gRPC 轨迹的端口是 `4317`。如果本机端口被占用，可以改端口启动：

```bash
PHOENIX_UI_PORT=16007 PHOENIX_GRPC_PORT=14317 docker compose -f labs/06-observability/compose.yaml up -d
```

换了页面端口后，启动 Agent 时也要把收集地址设成相同端口：

```bash
PHOENIX_COLLECTOR_ENDPOINT=http://127.0.0.1:16007 uv run --group observability python labs/01-mini-coding-agent/server.py --lab 06
```

Compose 的本地数据库密码默认是练习用的 `phoenix-local-only`。如果通过 `PHOENIX_DB_PASSWORD` 覆盖，只使用 URL 安全的字母和数字。

## 跑起来

先在项目根目录的 `.env` 里准备 DeepSeek 配置，格式与 Lab 01 相同。运行时加上 `observability` 依赖组，uv 会按锁文件准备 Phoenix 相关依赖：

```bash
uv sync --group observability
```

启动 Agent：

```bash
uv run --group observability python labs/01-mini-coding-agent/server.py --lab 06
```

打开 <http://127.0.0.1:8765>，页面会切到 `demo/` 工作区并显示示例任务。先试只读问题；再试修复问题，授权后会看到模型请求、工具执行和验证命令各自形成的 Span。

也可以试第三个示例。它会请求运行一条只抛出异常的 Python 命令；页面会弹出授权请求，允许后可在 Phoenix 里找到标记为错误的工具 Span。

## 在 Phoenix 里看什么

![Phoenix 项目列表中的 Lab 06 项目](./screenshots/phoenix-project-list.jpg)

*项目概览：找到 `ai-is-simple-lab-06`，这里能看到 Trace 数量和延迟统计；具体数值会随练习变化。*

1. 打开 `ai-is-simple-lab-06` 项目，选择刚产生的 Trace。
2. 展开 `agent.run`：它记录用户任务，并覆盖整次 Agent 运行。
3. 展开 `agent.model_turn`：里面的 OpenAI SDK 自动追踪会显示模型请求；`agent.tool` 会显示工具参数、返回值和结果状态。
4. 比较时间线，看看等待模型、工具执行或授权分别花了多久。故意失败的示例可以用来定位错误发生在哪一步。

![Phoenix 中展开的 Trace 树和模型 Span 详情](./screenshots/phoenix-span-detail.jpg)

*实战页面示例：左侧 Trace 树串起 Agent、模型和工具步骤；右侧显示当前选中模型 Span 的输出。每次运行产生的内容和耗时会不同。*

## Trace 是怎样记录到 Phoenix 的

数据经过三步：先在创建 OpenAI 客户端前安装自动追踪；每次用户请求创建一个父 Trace；再把 Agent 已有的模型和工具事件变成子 Span。OpenTelemetry SDK 会把这些 Span 发到本机运行的 Phoenix。

~~~text
OpenAI SDK 请求 ──自动追踪──┐
                            ├─ agent.run Trace ── OTLP ──> Phoenix
Agent 的 tool_call/result ──事件桥──┘
~~~

### 1. 注册 OpenAI SDK 自动追踪

Lab 扩展加载时先调用注册函数。因为它发生在 Agent 客户端创建之前，后续通过 OpenAI Python SDK 发出的请求才能被自动捕获。DeepSeek 提供 OpenAI 兼容接口，因此可以复用这个集成。

扩展入口先启用 Phoenix，再创建扩展实例：

~~~python
def create(workspace: Workspace) -> Extension:
    enable_phoenix()
    return ObservabilityExtension()
~~~

~~~python
import os
from phoenix.otel import register

os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006")
provider = register(
    project_name="ai-is-simple-lab-06",
    auto_instrument=True,
    batch=False,
)
tracer = provider.get_tracer("ai-is-simple.lab06")
~~~

完整代码在 labs/01-mini-coding-agent/observability.py 的 enable_phoenix()。接收地址由 PHOENIX_COLLECTOR_ENDPOINT 指定；Docker Compose 将 Phoenix 的接收端口发布到本机。项目名决定 Trace 出现在哪个 Phoenix 项目中。

### 2. 给一次用户请求创建父 Trace

SDK 自动追踪只能看到模型请求，不能知道一整次 Agent 任务从哪里开始、何时结束。网页后端在现有 Agent 调用外包一层上下文：

~~~python
with self.observer.agent_run(prompt):
    self.agent.run(prompt)
~~~

agent_run() 内部使用 start_as_current_span("agent.run")。当前 Span 会成为父节点，所以其中发生的模型调用能自动挂到这条 Trace 下。这里不改 Agent Loop，也不改变网页事件流。

### 3. 把自定义工具事件补成 Span

本项目的 read / write / edit / bash 不是 OpenAI SDK 工具，自动追踪看不到它们的实际执行。Agent 已经会发出 tool_call 和 tool_result 事件，Lab 06 直接观察这两类事件：

~~~python
if event_type == "tool_call":
    call_id = str(event.get("call_id", ""))
    attributes = {
        "openinference.span.kind": "TOOL",
        "tool.name": str(event.get("name", "unknown")),
        "input.value": _bounded(event.get("arguments", {})),
        "input.mime_type": "application/json",
    }
    self._tool_contexts[call_id] = self._start_span("agent.tool", attributes)
elif event_type == "tool_result":
    context_and_span = self._tool_contexts.pop(str(event.get("call_id", "")), None)
    if context_and_span is None:
        return
    context, span = context_and_span
    result = str(event.get("content", ""))
    span.set_attribute("output.value", _bounded(result))
    self._safe_close(context)
~~~

实际实现还会截断过长内容、标记错误和权限拒绝，并在任务结束时关闭未完成的 Span。它只观察事件，不参与路径限制或授权判断。完整逻辑见同一个文件的 PhoenixTraceObserver.on_event()。

### 4. 在 Phoenix 中核对字段

打开刚产生的 Trace，检查：

- agent.run 的输入是用户任务，输出是 Agent 最终回复。
- agent.model_turn 表示一次模型回合；OpenAI SDK 集成会在它下面记录模型请求。
- agent.tool 的 tool.name、input.value、output.value 分别说明工具名称、参数和结果。
- Span 的时间线能看出模型等待、工具执行和网页授权等待各占了多久。

本实战会把模型提示词、模型回复、工具参数和工具返回值发到本机 Phoenix。工具内容超过 8000 个字符时会截断。示例默认使用单独的 demo/ 工作区；查看真实项目轨迹前，先确认这些内容适合发送到你的本机 Phoenix 数据库。模型请求仍会发送到配置的 DeepSeek API。

## 今天只记住

> **Trace 看一整次任务，Span 看任务里的单一步骤。**

## 想一想

如果 Phoenix 里有模型请求，却没有 `agent.tool`，你会先检查自动追踪注册顺序，还是 `tool_call / tool_result` 事件？为什么？

<details>
<summary>参考思路（先自己想一想，再展开）</summary>

先看 Phoenix 有没有模型 Span。如果也没有，先检查收集地址和 OpenAI 自动追踪是否已在创建客户端前注册；如果模型 Span 正常，再检查 Agent 事件桥有没有拿到工具调用和结果。这样能先分清是 SDK 接入问题，还是 Harness 事件没有串起来。

</details>

## Phoenix 官方资料

- [Docker 部署](https://arize.com/docs/phoenix/self-hosting/deployment-options/docker)
- [OpenAI Python SDK 追踪](https://arize.com/docs/phoenix/integrations/llm-providers/openai/openai-tracing)
