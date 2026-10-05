# 第 09 章：Memory——会话内记忆与跨会话记忆

![Memory：筛选并召回持久化信息](../../assets/chapter-09-memory.png)

> **一句话总结：会话内记忆让当前任务接得上，跨会话记忆让后续任务用得上过去的信息。**

第 08 章的 Context Compact 处理当前对话太长的问题。Memory 处理的是另一件事：当前会话结束后，哪些信息值得留下，之后又如何找到它。

## 记忆常说几层？

行业没有统一的“记忆分层标准”。初学时可以先按信息能用多久、能被哪些任务访问来区分：

| 范围 | 当前上下文（工作记忆） | 当前会话（短期记忆） | 跨会话（长期记忆） |
| --- | --- | --- | --- |
| 能用多久 | 当前这次模型调用 | 同一个对话或任务线程 | 后续对话、任务或运行 |
| 典型内容 | 这一步要用的消息、文件片段和召回结果 | 对话历史、工具结果、计划和待办状态 | 用户偏好、项目规则、历史经验和决定 |
| 常见实现 | 放进模型的 context | Session、thread state、checkpoint | Store、文件、数据库、向量库或知识图谱 |

**“跨会话”通常描述记忆的作用范围，不是和“短期、长期”并列的固定第三类。** 很多框架把同一个 thread 内可恢复的状态称为短期记忆，把跨 thread 可检索的信息称为长期记忆。会话历史即使写入数据库、服务重启后仍存在，只要它仍只属于原来的 thread，在这套分类里依然是短期记忆。要看清框架里的“session”具体指什么：有的指一次聊天，有的指一次运行。

模型每次只看得到当前上下文。短期历史和长期记忆都要经过选择，才会进入当前上下文；Context Compact 整理的是当前对话历史，Memory 则管理会话之外可复用的信息。LangGraph 明确把 checkpointer 用于 thread 状态、store 用于跨 thread 数据；OpenAI Agents SDK 也把保存消息的 Session 和供后续运行使用的 Agent Memory 分开。[LangGraph：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[OpenAI Agents SDK：Sessions](https://openai.github.io/openai-agents-python/sessions/)、[OpenAI Agents SDK：Agent Memory](https://openai.github.io/openai-agents-python/sandbox/memory/)

## 长期记忆保存什么

常见内容可以按用途区分：

| 类型 | 保存内容 | Coding Agent 的例子 |
| --- | --- | --- |
| 语义记忆（semantic） | 相对稳定的事实和偏好 | 项目使用 Python；测试命令是 `uv run pytest` |
| 情景记忆（episodic） | 某次任务、故障或决定的经过 | 一次修复发现偶数长度的 `median()` 取值有误 |
| 程序性知识（procedural） | 可重复执行的方法和规范 | 审查清单、发布步骤、代码生成约定 |

本项目把程序性知识作为 Skill 单独管理，见[第 07 章 Skill Loading](../07-skill-loading/)。不同框架的分类可能不同；关键是知道一条记录保存了什么、属于谁、来自哪里、现在是否仍然有效。

## 记忆系统的基本架构

完整系统至少要处理写入、存储、召回和维护。把聊天记录直接塞进向量库，只覆盖了其中一部分。

```text
写入路径
对话、用户纠正、任务结果
        ↓
筛选：以后是否可能复用？是否允许保存？
        ↓
整理：类型、用户/项目范围、来源、时间、有效性
        ↓
去重 / 更新 / 标记过时
        ↓
持久化存储

读取路径
当前任务 → 是否需要历史信息？
        ↓
按范围检索候选记忆
        ↓
相关性、实体关系和时间排序
        ↓
选出少量证据，连同来源放回当前上下文
```

写入时要控制记忆的质量：区分事实与推测，记录来源和时间，避免把一次性要求当成长期偏好。信息发生变化时，也不应无声覆盖旧状态；要能识别新旧版本，并在问题需要时还原变化过程。

读取时先按用户、项目或团队等范围隔离，再根据当前任务检索。常见做法包括关键词检索、向量语义检索、实体关系检索，或把几种信号合并排序。最后只把有限的证据交给模型，并保留来源，方便核对。

## 先定信息边界，再选存储

不要从“我选哪个向量数据库”开始。先判断信息归谁、保留多久、怎样更新、出错后谁能删除，以及当前任务怎样找到它。

| 需求 | 更像哪类状态 | 设计时先确认 |
| --- | --- | --- |
| 接着同一条对话继续做事 | Session / checkpoint | 线程边界、持久化与恢复 |
| 以后任务可复用的用户或项目事实 | 长期 Memory | 来源、时间、冲突、隔离与删除 |
| 从大量外部文档中找有依据的片段 | RAG / 检索 | 文档更新、切分、召回、排序和引用 |
| 让模型按固定步骤执行规范 | Skill / 流程指引 | 内容可信度、版本和工具权限 |

Memory 和 RAG 可以共用关键词、向量或混合检索，但它们解决的问题不同：Memory 管理跨任务仍有用、可能变化的事实；RAG 面向一个可检索的内容集合，重点是找回相关证据。面试时要说明来源、时效和权限，而不只是说“把内容放进向量库”。

不同项目会把这些能力放在不同层：有的提供记忆抽取和召回服务，有的管理 Agent 状态，有的偏时间关系图，有的把记忆做成 Agent 的持久工作区。产品能力和版本变化很快；要比较具体框架时，先说明需求，再查它当前官方文档。扩展阅读页保留了一组入口，正文不把短期产品动态当作稳定原理。

评估也应回答“记忆是否帮任务做得更好”，而不只是“能不能复述存过的内容”。可以在同一组任务上比较有记忆和无记忆的正确率、工具调用数、耗时和 token，并检查过期信息、跨用户泄漏及删除路径。

## 在项目中怎样用记忆

Coding Agent 的记忆应当围绕具体项目组织，而不是把所有历史混成一个用户档案：

- **项目概要：** 技术栈、测试命令、目录约定等稳定信息。保持短小，启动时可以直接带入。
- **历史经验：** 已解决的故障、有效的排查路径和踩过的坑。按当前任务检索，不必每次全量注入。
- **项目决定：** 记录决定内容、原因、来源和适用范围；新决定出现时标出旧决定何时失效。
- **个人偏好：** 与项目事实分开保存，并按用户隔离，避免带进不相关的仓库或团队。

比如修复统计函数时，Agent 可以先召回“过去发现 `median()` 偶数项处理有误”，再读取当前代码确认问题仍然存在，最后运行适用的检查。记忆缩短重复探索，但代码、测试和当前用户要求仍是执行依据。

上线或扩大记忆范围前，应检查它是否真的改善了体验：用相同任务比较记忆开启和关闭时的正确率、工具调用数、耗时和 token；同时检查错记、过期、越权共享和用户删除记忆的路径。只测“能否复述旧信息”不足以证明系统有帮助。Mem0 团队提出的 DolphinBench 也把任务完成、成本和延迟放在一起评估；阅读这类厂商提出的基准时，还要结合数据集和作者背景判断结论适用范围。[DolphinBench（2026 预印本）](https://arxiv.org/abs/2609.24971)

## 用 DeepSeek 跑起来

本章的完整代码在 [`code.py`](./code.py)。它用 Markdown 文件实现一个易检查的长期记忆原型，提供 `remember` 和 `recall_memory` 两个工具。召回使用简单关键词匹配，目的是展示“显式写入、跨运行保存、按需读取”；它没有实现向量检索、关系图或自动整理。

先配置 `.env`：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

运行：

```bash
uv run python chapters/09-memory/code.py
```

输入一条跨任务有用的项目约定，退出后重新运行，再询问这条约定。完整 Coding Agent 中的会话历史和长期记忆如何配合，可继续看[实战篇 02：长期记忆](../../labs/02-memory/)。

## 情境题：记忆和当前配置冲突时怎么办？

项目把测试命令从 `pytest` 改成了 `uv run pytest`。下次任务问“测试怎么跑”时，记忆系统如何避免把旧命令当成当前事实？

<details>
<summary>参考思路（先自己想一想，再展开）</summary>

为记忆保存来源、时间和所属项目。新决定出现时，将旧记录标记为失效或被新记录取代；回答当前命令时优先召回仍有效的版本，必要时打开项目配置核对。

</details>

## 参考

- [LangGraph：Memory 概览](https://docs.langchain.com/oss/python/concepts/memory)
- [LangGraph：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph：短期记忆](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- [LangGraph：长期记忆](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [OpenAI Agents SDK：Agent Memory](https://openai.github.io/openai-agents-python/sandbox/memory/)
- [Mem0：开源架构说明](https://github.com/mem0ai/mem0/blob/main/docs/core-concepts/how-it-works.mdx)
- [Cognee：官方仓库](https://github.com/topoteretes/cognee)
- [Hindsight：官方仓库](https://github.com/vectorize-io/hindsight)
- [Letta Code：官方仓库](https://github.com/letta-ai/letta-code)
- [Mem0：Token-Efficient Memory Algorithm](https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm)
- [Mem0：Memory Decay](https://mem0.ai/blog/introducing-memory-decay-in-mem0)
- [Graphiti：时间知识图谱](https://help.getzep.com/graphiti/getting-started/welcome)
- [MemOS：Memory Operating System](https://github.com/MemTensor/MemOS/blob/main/docs/en/open_source/home/memos_intro.md)
- [LeanMem（2026 预印本）](https://arxiv.org/abs/2608.03463)
- [VibeMemBench（2026 预印本）](https://arxiv.org/abs/2609.23570)
- [DolphinBench（2026 预印本）](https://arxiv.org/abs/2609.24971)
- [Anthropic：Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [learn-claude-code：s09 Memory](https://github.com/shareAI-lab/learn-claude-code/tree/main/s09_memory)
