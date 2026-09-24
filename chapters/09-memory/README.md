# 第 09 章：Memory——会话内记忆与跨会话记忆

![Memory：筛选并召回持久化信息](../../assets/chapter-09-memory.png)

> **一句话总结：会话内记忆让当前任务接得上，跨会话记忆让后续任务用得上过去的信息。**

**本章新增：** 一个最小的长期记忆存储，以及写入、检索和使用记忆的流程。

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

## 常见记忆框架

截至 **2026 年 9 月**，比较常见的项目横跨两类：直接提供记忆存取能力的框架，以及自带记忆机制的 Agent 框架。GitHub 星数可以粗略反映关注度，但不等于实际部署量。

| 项目 | 它主要提供什么 | 适合什么情况 |
| --- | --- | --- |
| [Mem0](https://github.com/mem0ai/mem0) | 可单独接入的记忆层，负责提取、保存和检索用户或项目记忆 | 想给现有 Agent 增加跨会话记忆 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Agent 编排框架；checkpointer 保存当前 thread，store 保存跨 thread 信息 | 已用 LangGraph，需要自己组合短期状态和长期存储 |
| [Graphiti / Zep](https://github.com/getzep/graphiti) | 保存带来源和有效时间的实体、关系与事件 | 事实关系多、状态常变化，还要追溯过去 |
| [Cognee](https://github.com/topoteretes/cognee) | 把文档、代码和对话整理成可查询的知识图谱 | 要把多个来源汇成项目或团队知识库 |
| [Hindsight](https://github.com/vectorize-io/hindsight) | 分开组织事实、经历、观察结论和心智模型，并提供 retain / recall / reflect 流程 | 希望 Agent 能从多次经验中归纳规律 |
| [Letta Code](https://github.com/letta-ai/letta-code) | 完整的持久化 Agent Harness；MemFS 用可版本管理的文件组织常驻记忆和按需材料 | 想研究 Agent 如何自行维护上下文和长期记忆 |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | Session 保存对话历史；Sandbox Agent 的 Memory 能为后续运行整理经验，仍处于 Beta | 已采用该 SDK，想先用它提供的会话和沙箱记忆能力 |

这些项目解决的问题不同，不能只按“谁的记忆最好”排成一个榜单。Mem0 更像可嵌入的记忆服务；LangGraph 给应用状态和存储的接口；Letta 把记忆做成 Agent 本身的一部分。尤其要注意：**Mem0 的实体匹配不等于完整知识图谱。** 当前开源检索依赖配置的向量库，可选重排，并用实体重合提升排序；Graphiti 才是专门维护可查询时序关系图的路线。[Mem0 开源架构说明](https://github.com/mem0ai/mem0/blob/main/docs/core-concepts/how-it-works.mdx)、[Graphiti 官方说明](https://github.com/getzep/graphiti)

## 近期系统走向

不同路线仍在演进，主要变化集中在提取、时间理解、后台整理和检索策略：

MemOS 探索把不同类型的记忆、生命周期和调度放进统一的管理层；LeanMem 研究如何根据问题选择记忆类型和检索预算。它们代表系统架构与检索策略的探索，不是和 Mem0 一样的同类 SDK。[MemOS](https://github.com/MemTensor/MemOS/blob/main/docs/en/open_source/home/memos_intro.md)、[LeanMem（2026 预印本）](https://arxiv.org/abs/2608.03463)

Mem0 的 2026 更新体现了几项变化：抽取阶段用一次模型调用添加独立事实，让新旧状态都能留下；检索融合语义、关键词和实体匹配；时间感知区分事实何时成立，并按问题调整排序。Memory Decay 还会根据记忆最近被使用的时间轻调排序，但不会删除旧记忆。后台 Dream 则能合并重复项、标记已被取代的事实，并归纳多条记录；它目前属于 Pro 和 Enterprise 计划，不是开源 SDK 默认具备的能力。[Mem0：Token-Efficient Memory Algorithm](https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm)、[Mem0：Temporal Reasoning](https://mem0.ai/blog/introducing-temporal-reasoning-in-mem0)、[Mem0：Memory Decay](https://mem0.ai/blog/introducing-memory-decay-in-mem0)、[Mem0：Dream](https://mem0.ai/blog/dream-background-memory-consolidation-for-ai-agents)

这些系统都在增加提取、召回和维护环节，但记忆是否有用，最终要看它能否帮助 Agent 更好地完成任务。2026 年的 VibeMemBench 用真实仓库任务和可执行测试评估 Coding Agent 记忆；论文报告称，现有记忆系统在多数 solver 组合中未能超过不使用记忆的基线。这提醒我们：记住一条信息和正确运用它是两件事。[VibeMemBench（2026 预印本）](https://arxiv.org/abs/2609.23570)

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

## 今天只记住

> **短期记忆维护当前任务；长期记忆筛选跨任务有用的信息，并按需召回。**

## 想一想

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
- [learn-claude-code：s09 Memory](https://github.com/shareAI-lab/learn-claude-code/tree/main/s09_memory)
