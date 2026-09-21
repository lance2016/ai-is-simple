# 第 01 章：Agent Loop

![Agent Loop：从用户任务开始，工具结果回到模型，直到输出答案](./assets/agent-loop.png)

## 先看图

这张图只想说明一件事：**Agent 不是模型说完一句话就结束，而是模型和工具之间不断交换信息。**

开始时，用户输入一次任务。模型决定要不要调用工具；如果要，就让工具执行。工具返回结果后，模型根据结果再次决定下一步。等到模型判断“不需要再调用工具”，循环才结束，最后输出答案。

## 用生活例子理解

你对一个助理说：

> “帮我整理一下上周的产品反馈，并生成一份报告。”

助理可能会这样工作：

1. 先理解你的任务；
2. 决定去哪里找反馈；
3. 使用文件搜索或数据库工具；
4. 读取工具返回的内容；
5. 根据结果决定要不要继续查找、统计或生成报告；
6. 信息足够后，停止调用工具，告诉你最终结果。

注意：第 5 步不是让用户重新输入，而是助理根据刚刚拿到的结果自己继续判断。这就是图中从“工具结果”回到“模型决定”的箭头。

## 最小的 Agent 是什么

项目的第一个课程把复杂的 Agent 简化成三个部分：

- **模型**：理解任务，决定下一步做什么；
- **工具**：执行模型要求的动作，例如运行命令；
- **循环**：把工具结果送回模型，让它继续判断。

可以用下面几行伪代码表示：

```python
def agent_loop(messages):
    while True:
        response = model(messages, tools)
        messages.append(response)

        tool_calls = find_tool_calls(response)
        if not tool_calls:
            return response

        results = [execute(call) for call in tool_calls]
        messages.append(results)
```

这里最关键的不是 `while True` 这几个字符，而是信息的流动：

```text
模型决定 → 工具执行 → 工具结果 → 模型再次决定
                         ↘ 不需要工具 → 输出答案
```

## 模型和 Harness 的分工

可以把模型理解成驾驶者，把 Harness 理解成车辆和道路：

- 模型负责理解、判断和选择动作；
- Harness 提供工具、上下文、权限和执行环境；
- 工具真的去读文件、运行命令或访问外部系统；
- 循环负责把结果带回来。

模型本身不会凭空获得“手脚”。没有工具和执行环境，它最多只能告诉你“应该运行什么命令”；有了 Harness，命令才会真的运行。

## 今天只记住

> **模型决定做什么，Harness 负责把它做出来。**

一个工具加一个循环，就构成了一个最小的 Agent。后面的权限、计划、记忆、团队协作等机制，都是在这个基础循环上逐步加出来的。

## 想一想

如果模型只有一把 `bash` 工具，会遇到什么问题？

提示：它可以做很多事，但每件事都要自己拼命令，容易出错。下一章要解决的，就是如何把更多清晰、专用的工具接进来。

## 参考

- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)
- [s01 Agent Loop](https://github.com/shareAI-lab/learn-claude-code/tree/main/s01_agent_loop)

