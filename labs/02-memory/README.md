# 实战篇 02：长期记忆

> **一句话总结：跨任务留下少量稳定规则；具体经验先看目录，相关时再读全文。**

**本实战新增：** 常驻的项目记忆和按需读取的经验记录。复用现有 `read / write / edit`，不增加新工具。

主要对应理论篇：[第 09 章 Memory](../../chapters/09-memory/)。页面里的 `code-review` Skill 只用来对比第 07 章的按需加载，不是记忆的一种。

## 先看结构

```text
新对话开始
   ├─ .agent/MEMORY.md             → 少量稳定项目规则，每次带入
   ├─ .agent/memories/*.md         → 只带简介目录，需要时再读一条全文
   └─ .agent/skills/*/SKILL.md     → 只带技能目录，任务相关时再读操作说明

用户明确说“记住”
   └─ write / edit → 先请求授权 → 新记录从下一次对话开始进入目录
```

## 记忆、对话历史和 Skill 的区别

| 内容 | 保存什么 | 什么时候读取 |
| --- | --- | --- |
| 当前对话 | 这次任务的消息和进度 | 当前会话持续使用；太长时由上下文管理处理 |
| 常驻记忆 | 稳定的项目事实和规则 | 每次新对话都带入，所以要短 |
| 经验记录 | 某次故障、决定和解决过程 | 先看简介，相关时再读全文 |
| Skill | 人整理的操作步骤和检查清单 | 任务符合简介时再读全文 |

记忆里还可以区分不同内容：**事实**（项目默认设置）、**经历**（某次问题如何解决）、**操作方法**（固定流程）。本实战把前两种放进 Memory；第三种由单独维护的 Skill 承载。不同 Agent 框架的分类和存储方式并不完全相同。

## 跑起来

```bash
uv run python labs/01-mini-coding-agent/server.py --lab 02
```

页面会切到本实战的 demo 工作区。按顺序试试：

1. 问“`stats.py` 里 `median` 的偶数长度问题，以前是怎么记下来的？”观察 Agent 是否先读经验目录，再打开对应记录，并核对当前代码。
2. 说“审查一下 `stats.py`”。这次任务适合 `code-review` Skill，观察 Agent 是否读取操作说明。Skill 记录的是审查方法，经验记录的是过去发生过什么。
3. 说“记住：统计函数收到空列表时，要给出清楚的错误。”授权修改后，点“新对话”，再问空列表的处理约定。新规则会从常驻记忆中带入。

记忆文件会写入 `demo/.agent/`。想重新练习，可恢复 `labs/02-memory/demo` 下的示例文件。

## 代码里值得看的两处

**常驻记忆和经验目录分开。** `MEMORY.md` 放每次任务都可能用到的少量项目规则；经验记录只把 `name / type / description` 放进系统提示。模型判断记录相关时，再用现有 `read` 打开全文。

**写入仍然经过授权。** 用户明确要求记住后，Agent 用 `write` 或 `edit` 修改文件，页面会弹出授权请求。记忆只在下一次新对话加载，避免同一轮请求中的系统提示突然变化。

## 这个小实验的边界

- 经验目录只提供简介，由模型挑选要读的文件；没有向量数据库，也不适合成千上万条记录。
- 记忆可能过期或写错。使用过去经验前要核对当前代码，当前用户要求始终优先。
- 项目规则每次都占用上下文；只把稳定、常用的内容放进 `MEMORY.md`。

## 今天只记住

> **记忆不是聊天记录：常用规则少量常驻，具体经验按需召回。**

## 想一想

如果旧记录说 `median()` 已经修好，但当前文件里还是旧代码，Agent 应该相信哪一个？

<details>
<summary>参考思路（先自己想一想，再展开）</summary>

应重新读取当前文件。经验记录能提示要检查什么，但代码才反映现在的状态；如果两者不一致，应修正或标记旧记录。

</details>

## 参考

- [LangGraph：Memory 概览](https://docs.langchain.com/oss/python/concepts/memory)
- [LangGraph：长期记忆的存储与召回](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [OpenAI Agents SDK：Sessions 对话历史](https://openai.github.io/openai-agents-python/sessions/)
- [Anthropic：Claude Code Memory](https://docs.anthropic.com/zh-CN/docs/claude-code/memory)
