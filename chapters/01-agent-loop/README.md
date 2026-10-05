# 第 01 章：Agent Loop

![Agent Loop：模型决定、工具执行、工具结果、模型再次决定](../../assets/chapter-01-agent-loop.png)

> **Agent Loop 让应用根据模型每轮的返回，决定执行工具、继续请求，还是把回答交还给用户。**

## 一次工具往返里发生什么

图里的循环由应用程序（Harness，负责提供工具并控制执行的代码）驱动：

1. 应用把用户任务和可用工具一起发给模型。
2. 模型返回 `tool_calls` 时，它是在提出调用请求；工具还没有运行。
3. 应用检查请求并执行工具，把结果作为 `role="tool"` 消息带上对应的 `tool_call_id`。
4. 应用把更新后的消息再次发给模型。模型可以继续请求工具，也可以返回文字。

没有工具调用时，这个示例把模型文字交给用户。DeepSeek 的工具调用文档也采用“模型提出调用—应用执行—结果交回模型”的往返方式；模型本身不会执行你的 Python 函数。

## 看代码里的循环

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
    messages.append(message.model_dump(exclude_none=True))

    if not message.tool_calls:
        if choice.finish_reason != "stop":
            return f"模型未正常结束：{choice.finish_reason}"
        return message.content or ""

    if choice.finish_reason != "tool_calls":
        return f"工具调用未正常结束：{choice.finish_reason}"

    for call in message.tool_calls:
        result = run_tool(call)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": result,
        })
```

`messages` 保留了用户输入、模型的工具请求和工具结果，所以模型下一轮能依据执行结果继续判断。示例按返回顺序逐个执行调用；如果改成并行，先确认这些工具互不依赖，并且并发执行不会带来副作用问题。

## 停止不代表任务已完成

这里有两种不同的停止信号：

- 没有 `tool_calls` 且 `finish_reason` 为 `stop`：这轮模型回复正常结束，程序把文字交给调用方。
- 到达 `MAX_TURNS`：程序停止继续请求，避免循环无限延长。

两者都不能单独证明用户目标已经达成。比如工具返回了错误，模型仍可能生成“已完成”。面试时可以继续追问：应用如何验证结果？应根据任务查看可信证据，例如文件差异、测试退出码或数据库状态，而不是只信模型的自我报告。

`finish_reason` 也值得检查：DeepSeek 文档列出的结束原因包括 `length`、`content_filter`、`insufficient_system_resource` 和 `aborted`。本例只有在没有工具调用且原因为 `stop` 时才返回模型文字；有工具调用时也只有原因为 `tool_calls` 才执行。其他状态都交给调用方，避免执行可能被截断的参数。生产应用还需对 API 超时、无效工具参数和工具执行失败分别定义恢复策略。

每次继续循环都会再请求一次模型并带上消息历史，会增加延迟和 token 成本。直接回答就足够的任务不必调用工具；工具调用只是模型可选的下一步。

## 面试练习

假设 Agent 已经调用工具，但第 8 轮仍未给出最终答案。你会向调用方返回什么状态？如何区分“循环被上限截停”和“任务成功完成”？

<details>
<summary>参考思路</summary>

应明确报告循环触及上限，不能伪装成成功答案；如果有部分结果，也要标出尚未验证的部分。要判断任务成功，需要按任务类型检查外部证据。若经常触顶，再检查工具是否返回过多内容、任务是否需要拆分，或循环是否缺少清晰的停止条件。

</details>

## 参考

- [learn-claude-code：s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code/tree/main/s01_agent_loop)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling)
