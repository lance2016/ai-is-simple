# 实战篇 03：让子 Agent 查代码并汇总

> **一句话总结：`task` 工具背后是另一个 `CodingAgent`，它用自己的上下文把活干完，只把一段总结交回来。**

**本实战新增：** 一个 `task` 工具，大约 70 行（含注释）。子 Agent 直接复用 `CodingAgent`，没有另写一个循环。

对应理论篇：[第 06 章 Subagents](../../chapters/06-subagents/)。

## 先看结构

```text
主 Agent
   ↓ 调用 task(prompt)
子 Agent：新的 CodingAgent，新的 messages
   ├─ read / 只读 bash：可以
   ├─ write / edit / 其他命令：授权回调永远返回 False，一律拒绝
   └─ task：没有挂扩展，手里根本没有这个工具
   ↓ 最后一段话
主 Agent：只收到总结，外加一句“子 Agent 调用了 N 次工具”
```

## 三个限制是怎么做到的

| 限制 | 做法 | 为什么这样做 |
| --- | --- | --- |
| 只能读 | `confirm=lambda action: False` | 需要授权的动作都会被拒绝。只读限制直接复用 Lab 01 的授权层，不用另写一套规则 |
| 不能再委派 | 创建时不挂 `subagent` 扩展 | 工具池里没有 `task`，模型想调也调不了 |
| 过程不进主上下文 | 子 Agent 的 `emit` 只收集，不转发给网页 | 主 Agent 的 `messages` 里只多出一条 `task` 结果 |

注意：子 Agent 和主 Agent 共用同一个工作区。这是上下文隔离，不是文件隔离。

## 用生活例子理解

你让实习生去档案室查“哪几份合同提到了违约金”。他在档案室里翻了一下午，回来只给你一张纸：三份合同，分别在第几页。

你不需要知道他翻了哪些柜子，只需要结论和出处。

## 跑起来

```bash
uv run python labs/01-mini-coding-agent/server.py --lab 03
```

会自动挂上 `subagent` 扩展，工作区是项目根目录。页面上会显示下面这几个示例，点一下就能填进输入框。

试试一个需要翻很多文件的问题：

```text
请交给子 Agent 调查：chapters 目录下哪几章的 code.py 用到了 threading 模块？交回章节名列表。
```

实测结果：子 Agent 在自己的上下文里查完了所有章节，交回了章节名、行号和依据；主 Agent 的 `messages` 里只有 5 条消息（system、user、task 调用、task 结果、最终回答）。

再试一个小问题，比如“pyproject.toml 里有哪些依赖”。模型应该直接用 `read`，不走子 Agent。工具说明里写了“读一两个文件就能回答的事，不要用它”。

## 代价

- **慢**：子 Agent 至少要多跑一轮完整的模型循环，主 Agent 在这期间一直等着；
- **会丢细节**：主 Agent 只看得到总结，总结里漏了的东西就真的看不到了；
- **停不下来**：你在网页上点「停止」，只会在 `task` 返回之后生效。子 Agent 最多跑 `MAX_TURNS` 轮。这和一条正在运行的 `bash` 命令不会被打断是一个道理。

## 今天只记住

> **子 Agent 买的是一个干净的主上下文，付出的是时间和细节。**

## 想一想

子 Agent 的授权回调现在永远返回 `False`。如果想让它也能改文件，最简单的改法是什么？这样改有什么风险？

<details>
<summary>参考思路（先自己想一想，再展开）</summary>

最简单的改法是把主 Agent 的 `confirm` 传给子 Agent，这样子 Agent 要改文件时，你同样会看到授权弹窗。

风险是：你在弹窗里看到的只是一个孤零零的动作，看不到子 Agent 前面读了什么、为什么要改，比主 Agent 的请求更难判断。另外，子 Agent 改过的文件，主 Agent 只能从总结里知道，如果总结没写，主 Agent 就会基于过期的认识继续工作。

</details>
