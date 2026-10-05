# 第 02 章：Tool Use —— 模型报名字，程序找到函数

![Tool Use：工具分发示意图](../../assets/chapter-02-tool-use.png)

> **一句话总结：模型返回工具名和参数，应用按登记表找到 Python 函数并执行。**

第 01 章已经有了 Agent Loop。本章解决它遇到多个工具时的分发问题：模型提出调用请求，应用从允许的工具中找到对应处理函数，再把结果送回模型。模型不会直接运行 Python 函数。

## 一次调用经过哪些部分

- `TOOLS` 描述模型可选的工具，以及参数格式。
- `message.tool_calls` 带回模型提出的工具名和参数。
- `TOOL_HANDLERS` 把工具名映射到应用里的 Python 函数。
- 函数执行后，应用用对应的 `tool_call_id` 把结果放进 `role="tool"` 消息。

因此，新增一个工具要同时做三件事：写工具定义、实现处理函数、把名称登记到 `TOOL_HANDLERS`。Agent Loop 不必为每个工具增加一条 `if/elif`。

## 为什么用登记表

如果在循环里不断加 `if/elif`，工具数量一多，分发逻辑就和循环、错误处理混在一起。字典把“哪些名字能执行”列成一份清单：未知名称没有处理函数，就作为错误结果返回。

```python
TOOL_HANDLERS = {
    "list_files": list_files,
    "read_file": read_file,
    "get_today": get_today,
}

handler = TOOL_HANDLERS.get(name)
if handler is None:
    return f"Error: 未注册的工具 {name}"
```

这份登记表是应用支持的工具白名单，但不是完整的权限系统。它能拒绝未登记的工具名；不能单独判断当前用户是否有权读取某个文件、也不能判断某项写入是否需要确认。下一章会加上执行前的权限检查。

## 工具定义不是输入验证

`TOOLS` 里的 JSON Schema 是给模型看的工具说明和参数约束。本例使用普通的 Chat Completions 工具定义，没有开启 DeepSeek 的 Beta `strict` 模式。即使启用了严格格式约束，也仍要在应用侧检查业务规则：比如路径是否越界、数值是否在允许范围内、当前用户是否能访问目标资源。模型生成的参数还可能不是合法 JSON，所以 `run_tool()` 会捕获解析和执行错误，并把错误内容作为工具结果送回模型。

本章示例把文件访问限制在项目目录，并隐藏点号开头的路径（如 `.env` 和 `.git`）。这是方便学习的窄范围保护，不是生产环境的完整沙箱；真实服务还需根据用户身份和资源规则明确授权。

## 工具要拆多细

如果已有上下文就足够回答，不必为了“像 Agent”而调用工具；需要读取外部数据或改变外部状态时，再给模型相应能力。

像 `read_file` 这样的窄工具，输入和结果都容易界定，也更容易逐项加校验；代价是工具定义和维护数量会增加。`bash` 这类宽工具更灵活，但命令解释、执行范围和副作用检查都要由 Harness 承担。选择时看任务能否用清楚、可验证的接口表达，不要为了工具数量少就把所有能力塞进一个函数。

本项目实战篇会用受控的 `bash`，因为 Coding Agent 需要组合列目录、搜索、检查等命令；这里用 `list_files`、`read_file` 展示清晰的专用接口。两种设计适合不同边界。

## 用 DeepSeek 跑起来

完整示例在 [`code.py`](./code.py)，直接运行：

```bash
uv run python chapters/02-tool-use/code.py
```

`run_tool()` 做三步：解析参数、查 `TOOL_HANDLERS`、调用函数。执行结果再和 `tool_call_id` 一起追加到消息历史，下一轮模型就能看到对应工具的返回。即使结果是错误信息，也只是模型收到的一条工具结果；它不代表任务成功，是否重试仍由后续循环和应用策略决定。

```python
for tool_call in message.tool_calls:
    result = run_tool(tool_call)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": result,
    })
```

一条模型回复可能包含多个工具调用；本例会按返回顺序逐个执行，再把结果交回模型。如果第二个调用需要依赖第一个工具的结果，就不能假设它已经看过该结果：模型要先收到结果，才能据此提出下一次调用。相互独立的读取任务则可以由应用考虑并行执行，但必须为每个调用保留对应的 `tool_call_id`。

## 面试追问：模型返回了一个未知工具名，怎么办？

<details>
<summary>参考思路</summary>

不要把模型给出的名字直接当作 Python 函数或用 `eval()` 执行。先解析参数，再通过应用维护的登记表查找处理函数；名称不存在就返回明确错误。还要区分工具定义的格式约束、应用侧的参数和业务校验、以及下一章讨论的授权检查。

</details>

## 参考

- [DeepSeek Tool Calls 官方说明](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completions API：工具调用字段与参数](https://api-docs.deepseek.com/api/create-chat-completion/)
- [OpenAI Function Calling：工具定义与应用侧执行流程](https://developers.openai.com/api/docs/guides/function-calling)
- [learn-claude-code：s02 Tool Use](https://github.com/shareAI-lab/learn-claude-code/tree/main/s02_tool_use)
