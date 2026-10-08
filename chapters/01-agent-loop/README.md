# 第 01 章：Agent Loop —— 把 ReAct 的“想、做、看”跑成循环

![Agent Loop：模型决定、工具执行、工具结果、模型再次决定](../../assets/chapter-01-agent-loop.png)

> **一句话总结：ReAct 让模型交替“想一步、做一步、看结果”，Agent Loop 是应用里把这个节奏反复跑下去的那段循环代码。**

## 先看图

图里的循环由应用程序（Harness，负责提供工具并控制执行的代码）驱动：

1. 应用把用户任务和可用工具一起发给模型。
2. 模型返回 `tool_calls` 时，它是在提出调用请求；工具还没有运行。
3. 应用检查请求并执行工具，把结果作为 `role="tool"` 消息带上对应的 `tool_call_id`。
4. 应用把更新后的消息再次发给模型。模型可以继续请求工具，也可以返回文字。
5. 模型不再请求工具时，走出口：把文字交给用户，循环结束。

模型本身不会执行你的 Python 函数。它只负责“决定下一步”，执行和回传都是应用的事。

## 核心思想：ReAct

这个循环不是凭空设计的，背后是 2022 年的一篇论文 **ReAct**（Reasoning + Acting，推理加行动）。

### 它要解决什么问题

在 ReAct 之前，常见做法有两种，各缺一半：

| 做法 | 怎么做 | 问题 |
| --- | --- | --- |
| 只想不做（Chain-of-Thought） | 模型一步步推理，直接给答案 | 知识过时或记错时，只能“编”下去 |
| 只做不想（Act-only） | 模型直接连续调用工具 | 不说明为什么做这一步，容易跑偏，出错后也不会调整 |

ReAct 把两者交替起来：**每做一个动作前先想清楚，做完看到结果再想下一步。** 推理决定该做什么，动作的结果反过来修正推理。

### 原始格式长什么样

论文里，模型输出的是纯文本，程序从文本里解析出动作：

```text
Question: 哪年发布的 Python 3？那时距今多少年？
Thought 1: 我需要先查 Python 3 的发布年份。
Action 1: Search[Python 3]
Observation 1: Python 3.0 于 2008 年 12 月发布……
Thought 2: 发布年份是 2008，还需要知道今年是哪年。
Action 2: GetToday[]
Observation 2: 2026-10-08
Thought 3: 2026 - 2008 = 18，可以回答了。
Action 3: Finish[2008 年发布，距今 18 年]
```

`Thought`、`Action`、`Observation` 三者交替出现，直到 `Finish`。这就是 Agent Loop 的雏形。

### 今天的实现换了什么

思想没变，载体变了。现在的模型接口原生支持工具调用，不用再让模型写 `Action: Search[...]` 这种文本、再用正则去抠：

| ReAct 概念 | 本章代码里的对应物 |
| --- | --- |
| Thought：想下一步 | 模型内部的推理，或 assistant 消息里附带的文字 |
| Action：做一步 | assistant 消息里的 `tool_calls` |
| Observation：看结果 | 应用追加的 `role="tool"` 消息 |
| Finish：给出答案 | 没有 `tool_calls`、`finish_reason` 为 `stop` 的回复 |
| 把轨迹接着往下写 | `messages` 不断追加，下一轮整份发回模型 |

原生 `tool_calls` 有固定的结构：工具名和参数是分开的字段，还带 `tool_call_id` 用来对应结果。比起解析文本，它不容易出现格式漂移或误解析。本项目只使用原生 `tool_calls`，不做文本格式的解析。

### 分清“思想”和“循环”

- **ReAct 说的是模型怎么工作**：推理和行动交替进行，用观察结果修正下一步。
- **Agent Loop 说的是应用怎么配合**：发请求、执行工具、回传结果、判断何时停。

所以说“Agent Loop 基于 ReAct 思想”是对的。但要注意，不是所有 Agent 都是 ReAct：比如 Plan-and-Execute 先让模型列出完整计划，再按计划逐步执行，中间不一定每步都重新思考。ReAct 的长处是走一步看一步，适合事先不知道要几步、需要根据结果调整的任务；代价是每一步都要请求一次模型，步数多了会慢、会贵。

## 用生活例子理解

你让助理“查一下今天是几号，再算算离国庆还有几天”。

- 助理先想：“我得先知道今天的日期。”（Thought）
- 然后看一眼手机日历。（Action）
- 看到“10 月 8 日”。（Observation）
- 再想：“国庆已经过了，那就说明一下。”然后直接回答你。（Finish）

助理不会一开始就把所有步骤背下来照做，而是**每看到一个结果，再决定下一步**。Agent Loop 就是让程序替模型完成“看日历”这个动作，并把看到的结果交还给它。

## 用 DeepSeek 跑起来

本章的完整示例在 [`code.py`](./code.py)，只注册了一个无副作用的日期查询工具。先准备密钥并运行：

```bash
uv sync
cp .env.example .env
```

在 `.env` 中填写 `DEEPSEEK_API_KEY`，然后执行：

```bash
uv run python chapters/01-agent-loop/code.py
```

控制流的关键部分是：

```python
for _ in range(MAX_TURNS):
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    choice = response.choices[0]
    message = choice.message
    # Thought + Action: the model's reply, possibly with tool_calls
    messages.append(message.model_dump(exclude_none=True))

    # Finish: no tool call means the model is ready to answer
    if not message.tool_calls:
        if choice.finish_reason != "stop":
            return f"模型未正常结束：{choice.finish_reason}"
        return message.content or ""

    if choice.finish_reason != "tool_calls":
        return f"工具调用未正常结束：{choice.finish_reason}"

    # Observation: run each tool and feed the result back
    for call in message.tool_calls:
        result = run_tool(call)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": result,
        })
```

问“今天是几号？”时，`messages` 会这样一步步变长：

```text
system:    你是一个简洁的中文助手……
user:      今天是几号？
assistant: tool_calls=[get_today()]          ← Action
tool:      2026-10-08                        ← Observation
assistant: 今天是 2026 年 10 月 8 日。        ← Finish
```

`messages` 就是 ReAct 里那条“轨迹”。模型每一轮都能看到之前做过什么、看到了什么，所以能接着判断。示例按返回顺序逐个执行调用；如果改成并行，先确认这些工具互不依赖，并且并发执行不会带来副作用问题。

## 停止不代表任务已完成

这里有两种不同的停止信号：

- 没有 `tool_calls` 且 `finish_reason` 为 `stop`：这轮模型回复正常结束，程序把文字交给调用方。
- 到达 `MAX_TURNS`：程序停止继续请求，避免循环无限延长。

两者都不能单独证明用户目标已经达成。比如工具返回了错误，模型仍可能生成“已完成”。应用要验证结果，就得看可信证据，例如文件差异、测试退出码或数据库状态，而不是只信模型的自我报告。

`finish_reason` 也值得检查：DeepSeek 文档列出的结束原因包括 `length`、`content_filter`、`insufficient_system_resource` 和 `aborted`。本例只有在没有工具调用且原因为 `stop` 时才返回模型文字；有工具调用时也只有原因为 `tool_calls` 才执行。其他状态都交给调用方，避免执行可能被截断的参数。生产应用还需对 API 超时、无效工具参数和工具执行失败分别定义恢复策略。

每次继续循环都会再请求一次模型并带上消息历史，会增加延迟和 token 成本。直接回答就足够的任务不必调用工具；工具调用只是模型可选的下一步。

## 今天只记住

ReAct 是“想一步、做一步、看结果”的思路；Agent Loop 是应用里反复执行它、并负责在合适时候停下来的循环。

## 想一想

假设 Agent 已经调用工具，但第 8 轮仍未给出最终答案。你会向调用方返回什么状态？如何区分“循环被上限截停”和“任务成功完成”？

<details>
<summary>参考思路</summary>

应明确报告循环触及上限，不能伪装成成功答案；如果有部分结果，也要标出尚未验证的部分。要判断任务成功，需要按任务类型检查外部证据。若经常触顶，再检查工具是否返回过多内容、任务是否需要拆分，或循环是否缺少清晰的停止条件。

</details>

## 参考

- [ReAct: Synergizing Reasoning and Acting in Language Models（Yao et al., 2022）](https://arxiv.org/abs/2210.03629)
- [learn-claude-code：s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code/tree/main/s01_agent_loop)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling)
