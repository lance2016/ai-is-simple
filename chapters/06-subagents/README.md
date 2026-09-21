# 第 06 章：Subagents —— 给任务一个独立上下文

![Subagents：主 Agent 委派给独立上下文](../../assets/chapter-06-subagents.png)

> **一句话总结：把一个聚焦的子任务交给新的 Agent 上下文，最后只把总结带回主 Agent。**

第 05 章用任务清单帮助一个 Agent 管理复杂任务。

但有些任务本身就太大：需要阅读很多文件、调查多个方向，所有中间过程都塞进同一个 `messages` 后，上下文会越来越拥挤。

这时可以把一个聚焦的小任务委派给 Subagent。

## 先看图

Subagent 的关键不是“多启动一个机器人”，而是创建一段新的对话上下文：

- 主 Agent 提出一个清晰的子任务；
- Subagent 使用自己的 `messages` 开始工作；
- Subagent 可以读取资料、调用基础工具、整理结论；
- 主 Agent 最后只收到最终总结；
- 子 Agent 的中间对话不会全部塞回主 Agent。

可以把它记成：

```text
主 Agent
   ↓ 委派 task
Subagent：新的 messages[]
   ↓ 完成并总结
主 Agent：只收到最终文本
```

## 用请人查资料理解 Subagent

你在做一个大项目，但只想知道：

> “这个项目使用了什么测试框架？”

主 Agent 不必亲自阅读所有文件。它可以交给一个 Subagent：

1. 子 Agent 自己查找相关文件；
2. 子 Agent 在自己的上下文里分析；
3. 子 Agent 返回一句有用的结论；
4. 主 Agent 继续处理更大的任务。

主 Agent 不需要看到子 Agent 每一次打开文件、尝试搜索和中间判断。

## `task` 其实也是一个工具

主 Agent 通过工具调用委派任务：

```python
TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "task",
        "description": "使用新的上下文完成一个聚焦的子任务。",
        "parameters": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
}
```

分发时，`task` 指向的不是普通文件函数，而是另一个小型 Agent Loop：

```python
def run_subagent(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    # 子 Agent 在自己的 messages 中循环
    # 完成后只 return 最终总结
```

## 隔离的是什么，没有隔离的是什么

本章先区分三个边界：

| 内容 | 主 Agent 和 Subagent 的关系 |
| --- | --- |
| 对话历史 | 不共享，各自有自己的 `messages` |
| 返回结果 | 只返回 Subagent 的最终文本 |
| 工作目录 | 本示例共享，同一个 Python 进程可以看到同一批文件 |

所以 Subagent 是“上下文隔离”，不是“进程隔离”或“文件系统隔离”。

这也意味着：如果子 Agent 修改了共享目录里的文件，主 Agent 后续仍然可能看到这些修改。

## 为什么子 Agent 不能再继续委派

本章为了保持结构简单，让 Subagent 只拥有基础工具，不把 `task` 放进它的工具列表：

```text
主 Agent：可以调用 task
Subagent：不能调用 task
```

这样只保留一层委派，读者更容易看懂“谁委派给谁”。以后要做多层 Agent，需要额外考虑深度、预算和停止条件。

## 用 DeepSeek 跑起来

本章的完整代码在 [`code.py`](./code.py)。它包含两个循环：

- 主 Agent：拥有 `task` 和基础读取工具；
- Subagent：拥有基础读取工具，但没有 `task`。

先配置 `.env`：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

运行：

```bash
python chapters/06-subagents/code.py
```

可以试试：

```text
请委派一个子任务，找出项目使用了哪些 Python 依赖，并返回简短总结。
```

观察：子 Agent 的读取过程不会变成主 Agent 的完整对话，只会以 `tool` 结果的形式返回最终总结。

## 今天只记住

> **Subagent 的价值，是用一段新的上下文完成一个聚焦任务，再把结果带回来。**

它首先解决的是上下文管理问题，不是自动让任务并行，也不是天然提供文件隔离。

## 想一想

如果主 Agent 把“检查依赖”和“总结测试框架”交给两个 Subagent，为什么它们的中间过程不会互相污染？

## 参考

- [learn-claude-code：s06 Subagent](https://github.com/shareAI-lab/learn-claude-code/tree/main/s06_subagent)
- [DeepSeek Tool Calls 官方说明](https://api-docs.deepseek.com/guides/tool_calls/)
