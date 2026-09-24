# 第 09 章：Memory——短期状态与长期记忆

![Memory：筛选并召回持久化信息](../../assets/chapter-09-memory.png)

> **一句话总结：短期记忆维持当前任务的状态，长期记忆把跨任务仍有用的信息保存下来，并在需要时取回。**

**本章新增：** 一个最小的长期记忆存储，以及写入、检索和使用记忆的流程。

第 08 章的 Context Compact 处理当前对话太长的问题。Memory 处理的是另一件事：当前会话结束后，哪些信息值得留下，之后又如何找到它。

## 先分清短期和长期

| | 短期记忆 | 长期记忆 |
| --- | --- | --- |
| 范围 | 当前会话或任务 | 多个会话、任务或项目阶段 |
| 内容 | 消息、计划、工具结果、待办状态 | 用户偏好、项目规则、历史决定、过去的经验 |
| 常见存储 | 当前消息列表、任务状态、可恢复检查点（checkpoint） | 文件、关系数据库、向量库、知识图谱 |
| 主要问题 | 如何在上下文有限时继续当前任务 | 如何筛选、更新并找回长期有用的信息 |

会话历史即使写进数据库，仍可能只是某个 thread 的短期状态；它不自动变成可跨会话复用的长期记忆。OpenAI Agents SDK 的 Session 和 LangGraph 的 thread checkpoint 都用于保存会话状态；长期记忆则要另行设计存储范围和召回方式。[OpenAI Agents SDK：Sessions](https://openai.github.io/openai-agents-python/sessions/)、[LangGraph：Memory 概览](https://docs.langchain.com/oss/python/concepts/memory)

Context Compact 会整理当前会话的历史，保留进行中的任务所需内容。长期 Memory 则把筛选后的信息放到会话之外。两者可以配合使用，不能互相替代。

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

## 近期系统走向

截至 **2026 年 9 月**，没有一种架构在所有记忆任务上都占优。下面几种路线解决的问题不同：

| 路线 | 代表做法 | 适合关注的问题 |
| --- | --- | --- |
| 事实提取与混合检索 | Mem0 从交互中提取记忆，再结合语义、关键词和实体信号召回 | 记什么、如何避免漏召回 |
| 时间知识图谱 | Graphiti/Zep 连接实体、事件和事实，并记录事实何时生效或失效 | 关系复杂、状态会变化、需要追溯历史 |
| 记忆生命周期管理 | MemOS 把记忆视为可分层、调度和治理的资源 | 多种存储、多个 Agent、共享与审计 |
| 按问题组织证据 | LeanMem 等研究根据问题动态选择记忆类型和检索预算 | 如何用更少上下文回答不同问题 |

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
- [LangGraph：短期记忆](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- [LangGraph：长期记忆](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [Mem0：Token-Efficient Memory Algorithm](https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm)
- [Mem0：Memory Decay](https://mem0.ai/blog/introducing-memory-decay-in-mem0)
- [Graphiti：时间知识图谱](https://help.getzep.com/graphiti/getting-started/welcome)
- [MemOS：Memory Operating System](https://github.com/MemTensor/MemOS/blob/main/docs/en/open_source/home/memos_intro.md)
- [LeanMem（2026 预印本）](https://arxiv.org/abs/2608.03463)
- [VibeMemBench（2026 预印本）](https://arxiv.org/abs/2609.23570)
- [DolphinBench（2026 预印本）](https://arxiv.org/abs/2609.24971)
- [learn-claude-code：s09 Memory](https://github.com/shareAI-lab/learn-claude-code/tree/main/s09_memory)
