# 扩展阅读：Agent 项目与参考资料

这里收集值得继续看的 Agent 项目、记忆系统、协议和评测资料。它们是选读材料，不需要全部学完；每项都说明适合看什么，以及和本项目的关系。

## 先看两个参考项目

| 项目 | 适合看什么 | 和本项目的关系 |
| --- | --- | --- |
| [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | 从 Agent Loop 开始，逐步加入工具、权限、Hooks、Memory、MCP 等 Harness 机制。当前主线是仓库根目录的 `s01`～`s17`；`docs/` 和 `agents/` 里还保留旧版，章节编号不要混用。 | 本项目的机制安排受到它启发，但重新组织了讲解、插图和代码，不是它的官方文档或逐章翻译。可以对照[第 01 章 Agent Loop](../chapters/01-agent-loop/)和[第 09 章 Memory](../chapters/09-memory/)。 |
| [Pi](https://github.com/earendil-works/pi) · [官方文档](https://pi.dev/) · [安全说明](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/security.md) | 一个可扩展的 TypeScript/Node.js Agent Harness。可看 Extension、Session、上下文压缩和 Skills 如何在真实 Coding Agent 中配合。 | Pi 默认不会在每次工具调用前请求确认；工具以启动它的系统用户权限运行。首次载入部分项目资源时可能出现项目信任确认，但这不会限制工具能访问的路径。本项目额外实现的工作区限制和授权确认，属于本项目的 Harness 设计。 |

## 继续研究记忆系统

这些项目处理的范围不同：有的是可接入的记忆层，有的是 Agent 框架，有的主要解决知识图谱或经验归纳。

记忆没有公认的固定“几层”。常见的拆法有两个维度：按作用范围分为当前对话中的短期记忆和跨对话的长期记忆；按保存内容分为事实、经历和操作规则。“跨会话”通常是长期记忆的作用范围，不是和短期、长期并列的第三类。下面的项目也不是同一类产品，适合按想解决的问题来选。

比较架构时，可以沿着这条流程看：从哪里获取信息、怎样挑出值得保存的内容、存在哪里、按什么范围隔离、何时检索并交给模型，以及怎样更新或删除过时内容。最后还要看记忆是否真的改善了任务结果。

| 项目 | 架构重点 | 适合继续看的问题 |
| --- | --- | --- |
| [Mem0](https://github.com/mem0ai/mem0) · [文档](https://docs.mem0.ai/) | 为现有 Agent 提供记忆提取、保存和搜索。 | 怎样从交互中筛选事实，怎样组合语义、关键词和实体信号检索。开源版的实体匹配不等于完整的可遍历知识图谱。 |
| [Graphiti / Zep](https://github.com/getzep/graphiti) · [文档](https://help.getzep.com/graphiti/) | 记录实体、关系、事件、来源和事实有效时间，构建时序知识图谱。 | 当用户、项目状态或事实会变化时，怎样回答“现在是什么”和“以前是什么”。 |
| [Letta Code](https://github.com/letta-ai/letta-code) · [文档](https://docs.letta.com/) | 持久化 Agent Harness；MemFS 用可版本管理的文件保存常驻信息和按需材料。 | 怎样让 Agent 在多次运行中检查、整理并维护自身上下文。它是完整 Agent 环境，规模比本项目的记忆示例大得多。 |
| [Cognee](https://github.com/topoteretes/cognee) · [文档](https://docs.cognee.ai/) | 把文档、代码和对话整理成可查询的知识图谱。 | 怎样把多个来源汇成项目或团队知识，而不只保存用户对话。 |
| [Hindsight](https://github.com/vectorize-io/hindsight) · [文档](https://hindsight.vectorize.io/) | 将事实、经历、观察结论和心智模型分开组织，并提供 retain、recall、reflect 流程。 | 怎样从多次经历中归纳更稳定的结论。它提出的基准成绩也应结合作者和评测设置来看。 |
| [LangGraph Memory](https://docs.langchain.com/oss/python/concepts/memory) | Agent 框架提供的基础能力：thread checkpoint 管当前会话状态，Store 管跨 thread 数据。 | 怎样区分短期会话状态与跨会话的长期记忆，以及怎样按用户或项目划分范围。 |
| [LangMem](https://github.com/langchain-ai/langmem) | 可接入 LangGraph Store 的记忆管理工具，支持对话信息提取、记忆更新和后台整理。 | 已使用 LangGraph，希望把提取和整理逻辑接到现有 Store 上。 |
| [MemOS](https://github.com/MemTensor/MemOS) | 把不同记忆类型、存储和生命周期纳入统一管理层。 | 了解更大规模的记忆管理与调度思路；它和单一记忆 SDK 不是同一类产品。 |
| [OpenAI Agents SDK Sessions](https://openai.github.io/openai-agents-python/sessions/) · [Agent Memory](https://openai.github.io/openai-agents-python/sandbox/memory/) | Session 保存对话历史；Sandbox Agent Memory 为后续运行提取和整理经验，目前仍是 Beta 能力。 | 对照“持久化会话”与“跨运行复用的记忆”有什么区别。 |

第一次接触记忆系统，可以先读[第 09 章](../chapters/09-memory/)，再跑[实战篇 02](../labs/02-memory/)。这个实战用 Markdown 文件演示常驻项目规则和按需读取的历史经验；它没有实现向量检索、知识图谱或后台自动整理。之后按需要选一个框架深入即可。

## 协议与工程工具

| 资料 | 适合看什么 | 对应内容 |
| --- | --- | --- |
| [Model Context Protocol 规范](https://modelcontextprotocol.io/specification/2026-07-28) | MCP Client、Server、Tools、Resources 和协议消息的定义。 | [第 14 章 MCP](../chapters/14-mcp-plugin/)和[实战篇 04](../labs/04-mcp/)。 |
| [Arize Phoenix 文档](https://arize.com/docs/phoenix/) · [Tracing 原理](https://arize.com/docs/phoenix/learn/tracing/how-tracing-works) | 用 OpenTelemetry / OpenInference 收集和查看模型、工具及检索过程的 Trace。 | [实战篇 06：Agent 可观测性](../labs/06-observability/)。 |
| [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) | OpenAI 兼容接口如何声明工具、接收模型返回的 tool call，并把工具结果送回模型。 | [第 02 章 Tool Use](../chapters/02-tool-use/)和[实战篇 01](../labs/01-mini-coding-agent/)。 |
| [Agent Skills 规范](https://agentskills.io/specification) | `SKILL.md` 的格式，以及如何把说明、脚本和参考资料打包成可按需加载的 Skill。 | [第 07 章 Skills](../chapters/07-skill-loading/)和[实战篇 09：代码审查](../labs/09-skill-loading/)。 |

## 记忆与 Agent 评测

记忆评测不能只看模型能不能复述旧信息，还要看取回的信息是否帮助它完成后续任务。

- [LongMemEval](https://arxiv.org/abs/2410.10813)：关注长对话、多会话记忆、知识更新和时间推理。
- [VibeMemBench（2026 预印本）](https://arxiv.org/abs/2609.23570)：用真实代码仓库任务和可执行测试，检查记忆是否帮助 Coding Agent 修好代码。
- [DolphinBench（2026 预印本）](https://arxiv.org/abs/2609.24971) · [项目页](https://dolphinbench.ai/)：以任务完成为中心，同时报告效果、成本和延迟；由 Mem0 团队发布，阅读结果时应一并看它的评测设置和发布方。

## 按目标选择阅读路线

- **从零搭一个 Agent：** `learn-claude-code` 的 s01～s04 → 本项目理论篇 00～03 → [实战篇 01](../labs/01-mini-coding-agent/)。
- **看成熟 Harness 怎么扩展：** Pi 的 Extension、Session 和 Skills → [第 15 章 Agent Harness](../chapters/15-integrated-harness/) → 按需挑选实战。
- **研究跨会话记忆：** [第 09 章](../chapters/09-memory/) → [实战篇 02](../labs/02-memory/) → LangGraph Memory 的短期／长期划分 → Mem0；需要时间关系图时再看 Graphiti，需要研究持久化 Agent 时再看 Letta。
- **判断记忆有没有实际价值：** 先做记忆开启／关闭的对照任务，再看 VibeMemBench 和 DolphinBench 的评测设计。

## 阅读边界

本页优先列原始项目、官方文档和论文。项目名称相同不代表架构相同，官方基准分数也不等于在所有任务上都更好。引用某个项目只表示它值得对照学习，不表示本项目已经采用或完整复现了它的设计。
