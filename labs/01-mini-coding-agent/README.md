# 实战篇 01：自己做一个 Coding Agent

> **一句话总结：Coding Agent 不神秘，就是“模型循环 + 一组工具 + 一个安全的工作区”。**

理论篇已经把 Agent 的零件拆开了。现在把它们重新装起来，做一个可以读取项目、搜索代码、修改文件并运行检查的简易 Coding Agent。

## 先看图

![Mini Coding Agent 的工作结构](../../assets/lab-01-mini-coding-agent.png)

看图时只抓住三件事：

- 用户先提出任务；
- DeepSeek 决定下一步，调用 `read / write / edit / bash`；
- 工具结果回到循环，权限确认和会话记录由程序负责。

这张图展示的是本项目的 Python 教学实现，不是 Pi 的内部架构图。它借鉴了 Pi 的核心取舍：模型提出下一步，Harness 负责执行；工具保持少量，列目录、搜索和检查等动作交给 `bash`。Pi 的完整实现使用 TypeScript/Node.js，本实战则用 Python + DeepSeek 把同一类最小循环跑通。

## 能做什么？

本例只提供 4 个核心工具：

| 工具 | 作用 | 是否需要确认 |
|---|---|---|
| `read` | 读取文本 | 否 |
| `write` | 创建或覆盖文件 | 是 |
| `edit` | 精确替换一段文本 | 是 |
| `bash` | 列文件、搜索、查看状态、运行检查 | 视命令而定 |

把“列文件”“搜索文本”“运行测试”分别做成工具当然可以，但工具一多，模型要记的接口也会变多。这里借鉴 Pi：把通用命令收进 `bash`，只保留最稳定的文件读写接口。

程序会阻止访问 `.env`、`.git`、`.venv` 和会话目录；只读 Bash 命令可以自动执行，写入、运行代码和不确定命令，如果不是交互式终端，会默认拒绝。图中的“权限确认 + 会话记录”是本项目额外加入的安全层，不代表 Pi 默认会弹出权限确认框。

这不是完整的安全沙箱。`bash` 仍然是在当前用户权限下运行，所以只应该在自己信任的工作区中实验。

## 跑起来

在项目根目录执行：

```bash
python labs/01-mini-coding-agent/agent.py
```

也可以直接传入一条任务：

```bash
python labs/01-mini-coding-agent/agent.py \
  "用 bash 列出 labs 目录，读取其中的 README，然后总结这个 Agent 有哪些工具"
```

开始前，确保 `.env` 中有：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

## 代码怎么对应理论篇？

| 理论篇 | 实战代码 |
|---|---|
| Agent Loop | `CodingAgent.run()` |
| Tool Use | 4 个工具定义、`TOOLS` 和 `SafeTools.dispatch()` |
| Permission | `SafeTools._target()`、`_confirm()` |
| Hooks 思路 | `dispatch()` 作为统一工具入口 |
| Context | `self.messages` |
| Memory / Session | `SessionStore` 的 JSONL 文件 |
| Harness | `CodingAgent + SafeTools + SessionStore` |

最值得注意的是：模型并没有直接读文件，也没有直接执行命令。模型只能提出 Tool Call，真正的操作必须经过 `SafeTools`。`bash` 是能力出口，但不是权限出口；权限仍然由程序决定。

## 会话记录

默认会把消息保存到：

```text
.coding-agent-sessions/session-YYYYMMDD-HHMMSS.jsonl
```

继续旧会话：

```bash
python labs/01-mini-coding-agent/agent.py \
  --session .coding-agent-sessions/你的会话文件.jsonl
```

这体现了一个简单但重要的区别：**上下文在内存里运行，会话记录在磁盘上保存。**

## 和 Pi 的关系

这里没有复制 Pi 的代码，而是用 Python 重现它背后的几个重要理念：

1. 核心循环尽量简单；
2. 工具通过统一接口注册和执行；
3. 能力通过扩展增加，而不是重写 Agent Loop；
4. 会话和工具边界由 Harness 管理；本项目另外加了适合教学的权限确认。

扩展阅读：

- [Pi 官方文档](https://pi.dev/docs/latest)
- [Pi Agent Harness](https://github.com/earendil-works/pi)
- [Pi Extensions](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md)
- [Pi Skills](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)
- [Pi SDK / RPC / JSON 模式](https://pi.dev/docs/latest)

Pi 的下一步实战可以是：把一个新的专业能力做成 TypeScript Extension，再增加 `/learn 15` 命令，让它变成“AI 如此简单学习助手”。

## 今天只记住

> **Coding Agent = 模型决定 + 工具执行 + 权限边界 + 会话状态。**

## 想一想

如果要增加一个 `delete_file` 工具，你会把确认放在哪里？如果把确认写进 system prompt，而不是写进程序，会有什么风险？
