# AI 如此简单

> 一句话、一幅图、一小段代码，把一个 AI 概念讲明白。

这是一个面向初学者的 AI 学习笔记项目。

项目受到 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 启发，并以它的学习主线为参考，再用更少的术语、更直观的图和生活化的例子重新解释。

这里不追求一次讲完所有细节，而是希望每一章先回答一个简单问题：

> **看完这张图，我能不能用自己的话解释它？**

## 默认技术栈

为了让示例容易复现，代码默认使用：

- 模型：DeepSeek，默认值为 `deepseek-flash`；
- SDK：OpenAI Python SDK；
- API：DeepSeek 的 OpenAI 兼容接口；
- 配置：通过 `.env` 文件读取 API Key。

如果你的账号使用其他模型，只需要修改 `DEEPSEEK_MODEL`。

## 每一章怎么读

每章都尽量保持同一种节奏：

1. 先看一幅图，建立整体印象；
2. 先用一句话说结论；
3. 用几个短段落和一个生活例子展开；
4. 最后看一小段 DeepSeek + OpenAI SDK 代码。

尽量不写大段说教文字。每章只讲一个核心概念。

## 第一次运行

```bash
cd /Users/lance/Desktop/ai-is-simple
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
python chapters/01-agent-loop/code.py
```

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

图示规则见 [STYLE_GUIDE.md](./STYLE_GUIDE.md)，项目协作偏好见 [Agents.md](./Agents.md)。

## 来源

- 原项目：[shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)
- 当前起点：[s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code/tree/main/s01_agent_loop)
- DeepSeek：[OpenAI SDK 调用示例](https://api-docs.deepseek.com/api_samples/chat_python/)
- DeepSeek：[Tool Calls 官方说明](https://api-docs.deepseek.com/guides/tool_calls/)
