# 实战篇 04：接入 MCP，让 Agent 读写笔记

> **一句话总结：MCP 只规定了“工具在哪、叫什么、怎么调”；接进来之后，远程工具和本地工具走同一个执行入口、同一套授权。**

**本实战新增：** 一个手写的 MCP Server（约 120 行）和一个把远程工具注册进工具池的扩展（约 140 行），都含注释。不依赖任何 MCP SDK。

对应理论篇：[第 14 章 MCP Plugin](../../chapters/14-mcp-plugin/)、[第 03 章 Permission](../../chapters/03-permission/)。

## 先看结构

```text
启动 Agent
   ↓
拉起子进程 notes_server.py，用 stdin / stdout 通信
   ↓
initialize                    握手：协议版本、双方信息
notifications/initialized     通知 Server：可以开始了
tools/list                    问它有哪些工具
   ↓
每个远程工具包成一个 McpTool：notes__list_notes、notes__read_note、notes__add_note
   ↓
和 read / write / edit / bash 放进同一个工具池
   ↓
模型调用 notes__add_note → 同一个 _execute → 同一个授权弹窗 → tools/call
```

## 和第 14 章有什么不同

第 14 章的两个 Server 是同一个 Python 进程里的字典，用来讲清“先发现、再调用”的概念。

这里是真协议：

- Server 是一个**独立进程**；
- 双方用 **JSON-RPC 2.0** 通信，一行一条消息；
- 工具的参数结构来自 Server 给的 **JSON Schema**，客户端不再自己拼。

任何按 MCP stdio 协议实现的 Server，理论上都能用 `SERVERS` 里的一行配置接进来。本实战只和自带的 `notes_server.py` 一起测过；接别人的 Server 时，可能要处理这里省略的部分，比如分页（`nextCursor`）、图片等非文字结果、请求超时。

## 三处边界

**1. 命名空间。** 远程工具名加上服务名前缀，比如 `notes__read_note`。两个 Server 都有 `search` 时，也不会互相覆盖。用双下划线是因为函数名里不能用点号。

**2. 授权。** Server 可以在 `annotations.readOnlyHint` 里声明“我是只读的”。但这是它**自己说的**，所以要不要相信，由客户端决定：

```python
SERVERS = {
    "notes": {"command": [...], "trust_read_only_hint": True},  # 自己写的，信
}
```

来路不明的 Server 应该设成 `False`，这样它的每个工具都会弹窗确认。

**3. Server 自己也要守边界。** `notes_server.py` 会检查笔记名，只允许字母、数字、中文、下划线和横线。模型传进 `../../etc/passwd`，Server 会直接报错，不会去读那个文件。客户端的授权和 Server 的校验是两道独立的检查，谁都不能指望对方。

## 用生活例子理解

公司请了一家外包的档案管理公司。对方给了你一份服务清单（`tools/list`），上面写着“查档案”“存档案”。

清单是对方写的，但哪些事要你签字才能做，由你们公司自己的规定决定，不看对方怎么写。

## 跑起来

```bash
uv run python labs/01-mini-coding-agent/server.py --lab 04
```

会自动挂上 `mcp` 扩展，并启动笔记 Server。页面上会显示下面这几个示例，点一下就能填进输入框。

试试：

```text
列出我的笔记，读一下 agent-loop，再新建一篇叫 test 的笔记，内容写 hello
```

实测结果：`notes__list_notes` 和 `notes__read_note` 直接执行；`notes__add_note` 停下来等你授权，弹窗里会显示完整参数。

Server 的 stderr 没有被接管，它打的日志会直接出现在终端里。stdout 只能放协议消息，这是 stdio 传输的规矩。

> 新建的笔记会写进 `labs/04-mcp/notes/`。

## 今天只记住

> **MCP 解决“怎么接”，Harness 决定“让不让做”。**

## 想一想

如果一个 Server 在 `tools/list` 里把 `delete_all_notes` 标成了 `readOnlyHint: True`，而你的配置是 `trust_read_only_hint: True`，会发生什么？

<details>
<summary>参考思路（先自己想一想，再展开）</summary>

它会被当成只读工具，不弹窗就直接执行，笔记全没了。

所以 `trust_read_only_hint` 只能给自己能审查代码的 Server 打开。更稳妥的做法是：即使信任 Server，也在客户端按工具名再加一道规则，比如名字里带 `delete` 的工具一律需要确认。声明只是参考，决定权要留在自己手里。

</details>
