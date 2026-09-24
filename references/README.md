# 扩展阅读：学完一章，接下来读什么？

这里不收集所有 Agent 资源，只挑能接着本教程往下学的资料。**必读**看核心原理，**推荐**配合对应章节阅读，**深入**留给准备做更完整系统时参考。

## 核心必读

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling) | 必读 | 看完整工具往返：定义工具 → 模型提出调用 → 应用执行 → 回传工具结果 → 模型继续生成。 | [00 · Chat Completion](../chapters/00-chat-completion/)、[01 · Agent Loop](../chapters/01-agent-loop/)、[02 · Tool Use](../chapters/02-tool-use/) |
| [OpenAI Conversation State](https://developers.openai.com/api/docs/guides/conversation-state) | 必读 | 理解多轮消息历史、conversation state 和 context window 的关系，以及对话状态如何延续。 | [00 · Chat Completion](../chapters/00-chat-completion/)、[08 · Context Compact](../chapters/08-context-compact/)、[09 · Memory](../chapters/09-memory/) |
| [OpenAI Compaction](https://developers.openai.com/api/docs/guides/compaction) | 推荐 | 了解 API 提供的对话压缩方式，并和本项目自己筛选、摘要旧消息的 [Context Compact](../chapters/08-context-compact/) 对照。 | [08 · Context Compact](../chapters/08-context-compact/) |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) · [Agent Orchestration](https://openai.github.io/openai-agents-python/multi_agent/) · [Sessions](https://openai.github.io/openai-agents-python/sessions/) · [Guardrails](https://openai.github.io/openai-agents-python/guardrails/) | 推荐 | 对照成熟 runtime 如何管理 loop、tools、handoffs、sessions 和 guardrails；其中 Agents as Tools 把子 Agent 当工具调用，Handoffs 则把控制权交给另一个 Agent。 | [01 · Agent Loop](../chapters/01-agent-loop/)、[06 · Subagents](../chapters/06-subagents/)、[13 · Agent Teams](../chapters/13-agent-teams/)、[15 · Agent Harness](../chapters/15-integrated-harness/) |
| [Anthropic：Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) | 必读 | 读懂固定代码路径的 workflow 和由模型决定下一步的 agent 有什么区别；从简单方案开始，确认有必要再增加复杂度。文中的工具生态较旧，重点看架构原则。 | [01 · Agent Loop](../chapters/01-agent-loop/)、[05 · Planning](../chapters/05-planning/)、[06 · Subagents](../chapters/06-subagents/)、[15 · Agent Harness](../chapters/15-integrated-harness/)、[16 · Workflow Runtime](../chapters/16-workflow-runtime/) |
| [Anthropic：Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | 推荐 | 用“每一步该把什么信息交给模型”串起本教程的 Skills、Subagents、Compact 和 Memory；原文重点讲上下文预算、压缩、笔记和子 Agent。 | [06 · Subagents](../chapters/06-subagents/)、[07 · Skills](../chapters/07-skill-loading/)、[08 · Context Compact](../chapters/08-context-compact/)、[09 · Memory](../chapters/09-memory/) |

## 可观测性：先理解 Trace，再看 Phoenix

按这个顺序读：OpenTelemetry Trace / Span 基础 → OpenInference → Phoenix。Trace（一次完整请求的执行路径）和 Span（其中的一步操作）是通用 tracing 概念，不是 Phoenix 私有概念。完成前两项后，再用 Phoenix 查看本教程里的 Agent 运行记录。

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [OpenTelemetry：Traces](https://opentelemetry.io/docs/concepts/signals/traces/) | 必读 | 先理解 Trace 如何由有关联的 Span 组成，以及怎样表示一次请求经过的多个操作。 | [实战篇 06 · Agent 可观测性](../labs/06-observability/) |
| [OpenInference 规范](https://github.com/Arize-ai/openinference) | 推荐 | 在通用 Span 上补充模型调用、工具、检索等 AI 应用字段；规范基于 OpenTelemetry，也能配合其他兼容后端使用。 | [实战篇 06 · Agent 可观测性](../labs/06-observability/) |
| [Phoenix 文档](https://arize.com/docs/phoenix/) · [Tracing 原理](https://arize.com/docs/phoenix/learn/tracing/how-tracing-works) | 推荐 | 把 Trace 和 Span 展示出来，沿调用顺序检查模型请求、工具结果和耗时。 | [实战篇 06 · Agent 可观测性](../labs/06-observability/) |

## Evaluation：从一次 Trace 到回归评估

推荐按这个过程迭代：先看 Trace 找到失败步骤，再把失败案例整理成 Dataset，编写 Evaluator / Grader，最后对每次改动重复跑评估，检查是否引入回归。

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [OpenAI：Evaluate Agent Workflows](https://developers.openai.com/api/docs/guides/agent-evals) | 必读 | 从 Trace 调试开始，再用 grader 给运行结果打分，并把案例转成可重复执行的 Dataset 和 eval run。 | [实战篇 06 · Agent 可观测性](../labs/06-observability/)、[实战篇 08 · Agent 效果评估](../labs/08-evaluation/)、[17 · Goal Loop](../chapters/17-goal-loop/) |
| [Anthropic：Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | 推荐 | 学习如何定义任务、记录 Trace、组合多个 Grader，并同时检查最终结果和执行过程。 | [实战篇 08 · Agent 效果评估](../labs/08-evaluation/)、[17 · Goal Loop](../chapters/17-goal-loop/) |

## Workflow Runtime：深入阅读 Temporal

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [Temporal 官方文档](https://docs.temporal.io/) · [理解 Temporal](https://docs.temporal.io/evaluate/understanding-temporal) | 深入 | 了解 Durable Execution 如何保存工作流历史，在进程或机器故障后恢复状态并从记录处继续。本项目第 16 章用本地 `Journal`、`run_id` 和 `resume` 教学演示这个方向；Temporal 是面向长时间运行任务的工业级方案，初学阶段不需要引入。 | [16 · Workflow Runtime](../chapters/16-workflow-runtime/) |

## 其他项目与规范

### 教程与成熟 Harness

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | 推荐 | 对照另一套从 Agent Loop 到 Harness 机制的教程。当前主线是根目录 `s01`～`s17`；`docs/` 和 `agents/` 里保留旧版，章节编号不要混用。 | [01 · Agent Loop](../chapters/01-agent-loop/)、[09 · Memory](../chapters/09-memory/)、[15 · Agent Harness](../chapters/15-integrated-harness/) |
| [Pi](https://github.com/earendil-works/pi) · [官方文档](https://pi.dev/) · [安全说明](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/security.md) | 深入 | 看 TypeScript / Node.js Harness 如何扩展 Extension、Session 和 Skills。Pi 默认不会在每次工具调用前请求确认；项目资源的信任确认也不限制工具访问路径，本项目额外实现的工作区限制和授权确认属于自己的 Harness 设计。 | [15 · Agent Harness](../chapters/15-integrated-harness/)、[实战篇 09 · Skill Loading](../labs/09-skill-loading/) |

### 工具协议与 Skills

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [Model Context Protocol 规范](https://modelcontextprotocol.io/specification/2026-07-28) | 推荐 | 查 MCP Client、Server、Tools、Resources 和协议消息的定义。 | [14 · MCP](../chapters/14-mcp-plugin/)、[实战篇 04 · MCP 工具接入](../labs/04-mcp/) |
| [Agent Skills 规范](https://agentskills.io/specification) | 推荐 | 查看 `SKILL.md` 格式，以及怎样把指令和配套脚本、参考资料打包成可按需加载的 Skill。 | [07 · Skills](../chapters/07-skill-loading/)、[实战篇 09 · Skill Loading](../labs/09-skill-loading/) |
| [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) | 推荐 | 对照本项目使用的 OpenAI 兼容接口，了解如何声明工具、接收 tool call 并回传执行结果。 | [02 · Tool Use](../chapters/02-tool-use/)、[实战篇 01 · Coding Agent 搭建](../labs/01-mini-coding-agent/) |

### Memory 系统

记忆项目很多，先沿着“保存什么、存在哪里、何时取回、怎样更新”比较即可。短期／长期通常按作用范围区分；事实、经历、操作规则则是按记忆内容区分，具体命名会因框架而异。

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [Mem0](https://github.com/mem0ai/mem0) · [文档](https://docs.mem0.ai/) | 推荐 | 看怎样从对话提取可复用信息，并为已有 Agent 提供记忆搜索。 | [09 · Memory](../chapters/09-memory/)、[实战篇 02 · 长期记忆](../labs/02-memory/) |
| [Graphiti / Zep](https://github.com/getzep/graphiti) · [文档](https://help.getzep.com/graphiti/) | 深入 | 看怎样把带来源和有效时间的实体关系组织成图，适合研究事实随时间变化的场景。 | [09 · Memory](../chapters/09-memory/) |
| [Letta Code](https://github.com/letta-ai/letta-code) · [文档](https://docs.letta.com/) | 深入 | 看持久化 Agent 如何通过可版本管理的文件维护常驻上下文和按需材料。 | [09 · Memory](../chapters/09-memory/)、[15 · Agent Harness](../chapters/15-integrated-harness/) |
| [LangGraph Memory](https://docs.langchain.com/oss/python/concepts/memory) · [LangMem](https://github.com/langchain-ai/langmem) | 深入 | LangGraph 适合理解 thread 内短期状态和跨 thread 长期存储；LangMem 展示怎样提取、更新和整理这些记忆。 | [09 · Memory](../chapters/09-memory/) |

<details>
<summary>更多 Memory 项目与评测</summary>

| 资料 | 推荐程度 | 适合看什么 | 对应章节 |
| --- | --- | --- | --- |
| [Cognee](https://github.com/topoteretes/cognee) · [文档](https://docs.cognee.ai/) | 深入 | 看怎样把文档、代码和对话整理成可查询的知识图谱。 | [09 · Memory](../chapters/09-memory/) |
| [Hindsight](https://github.com/vectorize-io/hindsight) · [文档](https://hindsight.vectorize.io/) | 深入 | 看事实、经历和观察结论如何分别保存、检索并归纳。 | [09 · Memory](../chapters/09-memory/) |
| [MemOS](https://github.com/MemTensor/MemOS) | 深入 | 看更大规模的记忆类型、存储和生命周期管理思路。 | [09 · Memory](../chapters/09-memory/) |
| [OpenAI Agents SDK Sessions](https://openai.github.io/openai-agents-python/sessions/) · [Agent Memory](https://openai.github.io/openai-agents-python/sandbox/memory/) | 深入 | 对照持久化对话历史与跨运行复用的 Agent Memory；后者目前是 Beta 能力。 | [00 · Chat Completion](../chapters/00-chat-completion/)、[09 · Memory](../chapters/09-memory/) |
| [LongMemEval](https://arxiv.org/abs/2410.10813) | 深入 | 看长对话和多会话记忆如何评测信息召回、知识更新与时间推理。 | [09 · Memory](../chapters/09-memory/) |
| [VibeMemBench（2026 预印本）](https://arxiv.org/abs/2609.23570) | 深入 | 用真实代码仓库任务检查记忆能否帮助 Coding Agent 修复代码。 | [09 · Memory](../chapters/09-memory/)、[实战篇 08 · Agent 效果评估](../labs/08-evaluation/) |
| [DolphinBench（2026 预印本）](https://arxiv.org/abs/2609.24971) · [项目页](https://dolphinbench.ai/) | 深入 | 以任务完成为中心比较记忆效果，并同时报告成本和延迟；由 Mem0 团队发布，阅读时请一并看评测设置。 | [09 · Memory](../chapters/09-memory/) |

</details>

## 推荐阅读路线

**模型请求 → Tool Calling → Agent Loop → Agent Harness → Context Engineering → Observability → Evaluation → Production / Durable Runtime**

依次对应：[00 · Chat Completion](../chapters/00-chat-completion/) → [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling) → [01 · Agent Loop](../chapters/01-agent-loop/) → [15 · Agent Harness](../chapters/15-integrated-harness/) → [Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) → [OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/) → [OpenInference](https://github.com/Arize-ai/openinference) → [Phoenix](https://arize.com/docs/phoenix/) → [OpenAI Evaluation](https://developers.openai.com/api/docs/guides/agent-evals) → [Temporal](https://docs.temporal.io/) / [16 · Workflow Runtime](../chapters/16-workflow-runtime/)。
