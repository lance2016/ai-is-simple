# 实战篇 01：自己做一个带界面的 Coding Agent

> **一句话总结：Coding Agent 不神秘，就是「模型循环 + 一组工具 + 一个安全的工作区」，再把每一步摆到浏览器里给你看。**

理论篇已经把 Agent 的零件拆开了。现在把它们装起来，做一个能读项目、搜代码、改文件、跑命令的 Coding Agent，并且给它一个网页界面：模型请求了什么工具、参数是什么、返回了什么、哪一步需要你点头，全都看得见。

## 先看图

![Mini Coding Agent 的工作结构](../../assets/lab-01-mini-coding-agent.png)

看图时抓住三件事：

- 你的任务进来，模型决定下一步做什么；
- 想动手就得调用 `read / write / edit / bash`，工具由程序执行，不是模型自己执行；
- 会改动工作区的那一步会停下来，等你在网页上点「允许」或「拒绝」。

这是本项目的 Python 教学实现，不是 Pi 的内部架构图。它借鉴了 Pi 的核心取舍：模型提出下一步，Harness 负责执行；工具保持少量，列目录、搜索、检查这些都交给 `bash`。

## 能做什么

只有 4 个工具：

| 工具 | 作用 | 要不要授权 |
|---|---|---|
| `read` | 读取文本文件（带行号） | 否 |
| `write` | 创建或覆盖文件 | 是 |
| `edit` | 把一段唯一的旧文本换成新文本 | 是 |
| `bash` | 列目录、搜索、查看 Git 状态、跑检查 | 看命令 |

把「列文件」「搜索文本」「跑测试」各做成一个工具当然行，但工具一多，模型要记的接口也变多。这里借鉴 Pi：通用命令收进 `bash`，只保留最稳定的三个文件接口。

### bash 什么时候自动执行

规则只有一句话：

> **单条命令 + 不含 shell 操作符（`|` `>` `<` `;` `&` 反引号 `$(`）+ 首词在只读白名单里 → 自动执行；其余一律弹窗授权。**

白名单是 `ls / pwd / cat / head / tail / wc / file / tree / grep / rg`，外加 `git status`、`git diff`、`git log`、`git branch` 这几个两词前缀。

所以 `ls -la` 直接跑，`git status` 直接跑，而 `git commit`、`rm x`、`cat a > b`、`python3 script.py` 都会停下来问你。规则简单的好处是：你一眼能看完，也就不容易被花式写法绕过去。

另外，命令里出现 `.env`、`.git/`、`.ssh`、`/etc/`、`sudo` 会被直接拦掉，连授权框都不弹。

这不是完整沙箱。`bash` 仍然以你的用户权限运行，只在你信任的工作区里玩。

## 跑起来

先在项目根目录的 `.env` 里准备好：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
# DeepSeek-V4.1-Flash 在 API 中的模型名是 deepseek-flash
DEEPSEEK_MODEL=deepseek-flash
```

然后启动：

```bash
python labs/01-mini-coding-agent/server.py
```

打开 <http://127.0.0.1:8765>，直接在输入框里说话。

默认工作区是本项目根目录。想让它只在某个目录里活动：

```bash
python labs/01-mini-coding-agent/server.py --workspace ~/some-project
```

界面上会看到四种块：

- **用户消息**：你说的话；
- **工具调用**：模型请求的工具名和完整参数（JSON）；
- **工具返回**：程序真正执行后的输出，默认展开；
- **需要授权**：会改动工作区的那一步，点「允许执行」它才继续。

网页只负责看和点。真正的路径检查、命令判断、权限判断都在 Python 里；关掉网页或者拒绝授权，模型没有别的路可以绕过去。

## 代码结构

一共两个 Python 文件，各管一件事：

```text
agent.py    Agent 内核：工具定义、工作区边界、模型循环
server.py   网页界面：HTTP 接口 + SSE 事件流 + 授权开关
web/index.html   单文件前端
```

`agent.py` 完全不知道浏览器的存在。它和界面只靠两个回调连接：

```python
CodingAgent(workspace, confirm=..., emit=...)
#   confirm(action) -> bool   需要授权时问用户
#   emit(event)     -> None   把每一步广播出去
```

想换成终端界面、换成 Slack Bot，只要换这两个回调，Agent 本身一行都不用改。

### 一个工具就是一个类

工具的三件事写在同一个类里：给模型看的说明书、要不要授权、真正干活的代码。

```python
class WriteTool(Tool):
    name = "write"
    description = "创建或整体覆盖一个文本文件。执行前会请求用户授权。"
    parameters = {"path": {"type": "string"}, "content": {"type": "string"}}
    required = ("path", "content")

    def confirm_prompt(self, workspace, path, content):
        # 返回一句话 = 这一步要授权；返回 None = 只读，直接做
        target = workspace.resolve(path)
        return f"写入文件 {workspace.label(target)}（{len(content)} 个字符）"

    def run(self, workspace, path, content):
        target = workspace.resolve(path)
        target.write_text(content, encoding="utf-8")
        return f"已写入 {workspace.label(target)}。"
```

新增一个工具，就是再写一个子类，然后加进 `TOOLS`。不用改 Agent Loop，也不用在三个地方各登记一次。

### 循环长什么样

```python
for _ in range(MAX_TURNS):
    message = self._ask_model()
    self.messages.append(message.model_dump(exclude_none=True))
    if message.content:
        self.emit({"type": "assistant_message", "content": message.content})
    if not message.tool_calls:      # 模型不要工具了，任务结束
        return
    for call in message.tool_calls:
        self._handle_tool_call(call)
```

就这么点东西。循环的出口只有一个：模型这一轮没有请求工具。

### 授权是怎么从浏览器传回来的

Agent 跑在后台线程。它调 `confirm(...)` 时，`PermissionGate` 做三件事：发一个 `permission_request` 事件到页面、阻塞等待、被 `/api/permission` 唤醒后返回 `True` 或 `False`。超过 5 分钟没人理，默认当作拒绝——宁可不做，也不要背着你动文件。

页面这边用 SSE 收事件。每条事件都有编号，所以刷新页面或者断线重连，带上上次的编号就能接着读，不丢也不重。

## 对应理论篇

| 理论篇 | 实战代码 |
|---|---|
| Agent Loop | `CodingAgent.run()` |
| Tool Use | `Tool` 基类和它的四个子类 |
| Permission | `Workspace.resolve()`、`Tool.confirm_prompt()`、`PermissionGate` |
| Hooks 思路 | `CodingAgent._execute()`，所有工具的唯一入口 |
| Context | `CodingAgent.messages` |
| Harness | `CodingAgent + Workspace + AgentSession` |

最值得注意的一点：模型从头到尾没有直接读过文件，也没有直接执行过命令。它只能提出 Tool Call，真正动手的是 `Tool.run()`，而动手之前还要过 `Workspace` 和授权这两关。

## 上下文只在内存里

这个例子没有把会话存到磁盘。点「清空上下文」或者重启服务，对话就没了，但工作区里已经改过的文件不会回滚——这两件事是分开的。

如果你想加持久化，可以在 `CodingAgent` 里把每条 message 追加写进一个 JSONL 文件，启动时再读回来。这是个不错的练手题。

## 和 Pi 的关系

这里没有复制 Pi 的代码，而是用 Python 重现它背后的几个想法：

1. 核心循环尽量简单；
2. 工具少而稳，通用能力收进 `bash`；
3. 工具通过统一接口注册和执行；
4. 加能力靠加工具，而不是改 Agent Loop。

注意区分：Pi 默认并不以权限弹窗为核心。本项目的授权确认、工作区限制是教学需要额外加的 Harness 层。

扩展阅读：

- [Pi 官方文档](https://pi.dev/docs/latest)
- [Pi Agent Harness](https://github.com/earendil-works/pi)
- [Pi Extensions](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md)

## 今天只记住

> **Coding Agent = 模型决定 + 程序执行 + 边界检查 + 你点头。**

## 想一想

如果要加一个 `delete_file` 工具，你会把授权写在哪里？如果只在 system prompt 里写「删文件前要先问用户」，而不写进程序，会有什么风险？
