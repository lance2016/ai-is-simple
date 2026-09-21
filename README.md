# AI 如此简单

> 每天一幅图，讲清一个 AI 核心概念。

这是一个面向初学者的 AI 学习笔记项目。

项目受到 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 启发，并以它的学习主线为参考，再用更少的术语、更直观的图和生活化的例子重新解释。

这里不追求一次讲完所有细节，而是希望每一章先回答一个简单问题：

> **看完这张图，我能不能用自己的话解释它？**

## 每一章怎么读

每章都尽量保持同一种节奏：

1. 先看一幅图，建立整体印象；
2. 用一段白话解释核心概念；
3. 用一个生活例子把它落地；
4. 最后看一点点代码或伪代码，理解它是怎么实现的。

## 学习路线

| 章节 | 主题 | 先记住一句话 |
| --- | --- | --- |
| 01 | Agent Loop | 模型决定下一步，工具负责把它做出来 |
| 02 | Tool Use | 工具越清晰，模型越容易正确行动 |
| 03 | Permission | 能做什么，也要判断该不该做 |
| 04 | Hooks | 在工具前后留接口，系统才能持续扩展 |
| 05 | Planning | 没有计划的 Agent，容易走哪算哪 |
| 06 | Subagents | 大任务拆小，每个子任务拥有干净上下文 |
| 07 | Skill Loading | 用到时再加载知识，不要一开始全塞进去 |
| 08 | Context Compact | 上下文总会变满，要学会腾出空间 |
| 09 | Memory | 记住重要的，忘掉不重要的 |
| 10 | Tasks | 把大目标拆成可追踪的小任务 |
| 11 | Background Tasks | 慢操作放到后台，Agent 可以继续思考 |
| 12 | Cron | 让任务在未来自动发生 |
| 13 | Agent Teams | 一个 Agent 顾不过来，就让队友分工 |
| 14 | MCP | 把外部能力接进同一个工具池 |
| 15 | Agent Harness | 多种机制，仍然围绕同一个循环 |
| 16 | Workflow Runtime | 固定的编排形状，可以沉淀成流程 |
| 17 | Goal Loop | 目标决定循环什么时候真正结束 |

目前已完成第 01 章，后续章节会逐步补充。

## 项目边界

这是个人学习笔记，不是原项目的官方文档，也不代表原作者观点。概念、章节顺序和部分术语参考原项目；插画、文字和解释会根据初学者阅读体验重新组织。

## 来源

- 原项目：[shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)
- 当前起点：[s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code/tree/main/s01_agent_loop)

