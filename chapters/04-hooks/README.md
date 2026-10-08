# 第 04 章：Hooks —— 在生命周期节点上自动插入逻辑

![Hooks：把扩展逻辑挂在循环节点上](../../assets/chapter-04-hooks.png)

> **一句话总结：Hook 不是工具，也不是模型的决策，而是系统在固定时机自动执行的扩展逻辑。模型决定做什么，工具负责去做，Hook 负责“每次做的前后，顺便还要做什么”。**

**本章新增：** 在 Agent Loop 的固定节点上留出扩展口，日志、权限、记忆这类逻辑挂上去，循环本身不用改。

## 为什么需要 Hooks

Demo 阶段的 Agent Loop 很干净：问模型、执行工具、回传结果，十来行就够了。

一旦要上线，各种需求就来了：

- **日志**：用户问了什么，模型调了哪些工具。
- **tracing / 监控**：每一步花了多久，哪一步出的错。
- **memory 保存**：对话结束后，把值得记住的信息存下来。
- **权限检查**：危险的工具执行前要拦一下。
- **异常处理**：出错时告警、记录现场。
- **评测**：每次回答后打分，用来改进 Agent。

如果全都直接写进循环，会变成这样：

```python
def agent_loop(task):
    log("start", task)                       # logging
    trace = start_trace()                    # tracing
    memory = load_memory(task)               # memory
    for _ in range(MAX_TURNS):
        try:
            step = decide(state)
            if step.is_final:
                save_memory(state)           # memory
                evaluate(step.answer)        # evaluation
                trace.end()                  # tracing
                return step.answer
            if not check_permission(step):   # permission
                ...
            log("tool", step)                # logging
            result = execute(step)
            trace.record(step, result)       # tracing
            state.append((step, result))
        except Exception as exc:
            alert(exc)                       # error handling
            raise
```

真正的核心只有 `decide`、`execute`、`state.append` 三行，其他十几行都是“顺便要做的事”。问题很明显：

- 循环越来越长，核心逻辑被淹没。
- 每加一项需求，都要改动最核心的代码。
- 想临时关掉评测或换一套日志，也得改循环。

Hook 的思路是：**在循环里固定留几个“插口”，其他逻辑挂到插口上，循环本身不再改。**

## LLM、Tool、Hook 各管什么

| 角色 | 负责什么 | 谁来触发 | 模型知道它吗 |
| --- | --- | --- | --- |
| LLM | 决定下一步做什么 | 循环每轮调用 | —— |
| Tool | 提供执行能力，由代码完成具体动作 | **模型主动选择** | 知道，在 `tools` 清单里 |
| Hook | 在生命周期节点插入额外逻辑 | **系统到点自动执行** | 不知道，也选不了 |

一句话区分：**Tool 是模型主动选择调用的能力，Hook 是系统自动执行的生命周期逻辑。**

### 用机器人的例子看一遍

孩子对陪伴机器人说：“帮我拍张照！”

1. **LLM** 理解请求，决定调用 `take_photo`。（决策）
2. **Hook** `before_tool_call`：检查家长是否允许使用摄像头。（系统自动）
3. **Tool** `take_photo` 打开摄像头拍照。（模型选的能力）
4. **Hook** `after_tool_call`：记录这次行为、写入 trace。（系统自动）
5. **LLM** 回复：“拍好啦，要看看吗？”
6. **Hook** `after_response`：更新 memory，比如“孩子喜欢拍照”。（系统自动）

第 2、4、6 步都不在 `tools` 清单里，模型不会、也不该决定要不要做。记录行为、检查权限，是**每次都必须发生**的系统能力，不能指望模型“想起来”。

判断一段逻辑该做成 Tool 还是 Hook，可以问一句：**要不要做，取决于任务内容吗？**

- 取决于任务内容，就做成 Tool，让模型判断。比如用户说“记住我喜欢蓝色”，模型调用 `save_memory`。
- 不管什么任务都要做，就做成 Hook，让系统保证。比如每轮结束自动保存对话摘要。

## Hook 挂在哪：生命周期节点

把上面那段代码改成 Hook 的写法：

```python
def agent_loop(task):
    emit("before_agent_start", task)
    for _ in range(MAX_TURNS):
        try:
            step = decide(state)
            if step.is_final:
                emit("after_response", step)
                return step.answer
            blocked = emit("before_tool_call", step)
            if blocked:
                result = blocked
            else:
                result = execute(step)
                emit("after_tool_call", step, result)
            state.append((step, result))
        except Exception as exc:
            emit("on_error", exc)
            raise
```

日志、trace、memory、评测都从循环里搬走了，各自注册到对应节点上。循环只剩核心流程和几个 `emit`。

常见的生命周期节点：

| 节点 | 什么时候触发 | 典型用途 | 本章代码里的事件名 |
| --- | --- | --- | --- |
| `before_agent_start` | 任务开始前 | 记录输入、加载 memory、开始 trace | `UserPromptSubmit` |
| `before_tool_call` | 工具执行前 | 权限检查、审计日志 | `PreToolUse` |
| `after_tool_call` | 工具执行后 | 结果检查、统计、trace | `PostToolUse` |
| `after_response` | 模型给出最终回复后 | 保存 memory、评测、结束 trace | `Stop` |
| `on_error` | 出错时 | 告警、记录现场 | 本章代码未实现 |

不同框架的叫法各不相同，本项目代码用的是右边一列的名字。**要记的是节点的位置，不是名字。**

还有一点：Hook 能不能改变流程，取决于循环怎么处理它的返回值。上面的伪代码里，只有 `before_tool_call` 的返回值能拦下工具，其他节点只是“观察”。事件名本身不决定行为，循环才决定。

## 放回全书看：每个概念管一件事

| 概念 | 管什么 | 在哪讲 |
| --- | --- | --- |
| Context | 提供信息：这次请求带给模型的所有内容 | 第 00、08 章 |
| LLM | 根据上下文做决策 | 第 00 章 |
| Agent Loop | 驱动多轮交互 | 第 01 章 |
| Tool | 执行业务动作 | 第 02 章 |
| Hook | 扩展 Agent 的生命周期 | 本章 |
| Workflow | 用代码编排固定流程 | 第 16 章 |

前五个组成一个能用的 Agent；Workflow 站在外面，用代码约束它。第 03 章的权限检查原本直接写在循环里，本章把它挪到了 `before_tool_call` 上，这就是 Hook 的典型用法。

## 用 DeepSeek 跑起来

完整代码在 [`code.py`](./code.py)。它注册了几个 Hook：记录用户输入、工具执行前做权限检查和日志、工具返回后检查结果长度、结束时打印消息数。读文件可以直接执行，写笔记会先要求确认，删除会被拒绝。

在 `.env` 配好 DeepSeek API Key 后运行：

```bash
uv run python chapters/04-hooks/code.py
```

循环里和 Hook 相关的只有这几行：

```python
blocked = trigger_hooks("PreToolUse", name, arguments)
if blocked:
    result = blocked
else:
    result = run_tool(tool_call)
    trigger_hooks("PostToolUse", name, result)
```

`trigger_hooks()` 按注册顺序运行某个事件的全部回调，返回第一个非 `None` 的结果。权限回调返回一段拒绝说明，循环就不执行工具；即使已经拒绝，后面的日志回调仍会记录这次尝试。

试着让 Agent 读取 `README.md`，再请它写一条笔记。观察 `[hook]` 日志在工具执行前出现；拒绝写入时，工具函数不会运行。

这个版本没有隔离 Hook 异常：回调抛错会直接中断当前 Agent 调用。真实系统要为每类 Hook 定好出错时是拒绝、放行还是重试。

## 什么时候用，什么时候不用

- **适合 Hook**：跨工具、每次都要发生的逻辑，比如日志、trace、统计、memory 保存。
- **不必用 Hook**：只在一处用到、又直接影响核心流程的简单判断，写在循环里反而更清楚。
- **代价**：Hook 是隐式调用，读循环代码时看不出到底挂了什么；多个 Hook 的执行顺序和异常也要额外管理。
- **别把安全全押在 Hook 上**：可选的回调可能漏注册或被移除。真正的授权要放在每次执行都必经的工具入口；Lab 01 就把路径和权限检查写在 Python Harness 里。

## 今天只记住

Tool 是模型主动选择的能力，Hook 是系统到点自动执行的逻辑；Hook 让日志、权限、记忆这些事从循环里搬出去，循环只管核心流程。

## 想一想

想阻止某个写操作，挂在 `after_tool_call`（本章代码里的 `PostToolUse`）上的 Hook 能做到吗？

<details>
<summary>参考思路</summary>

不能。`after_tool_call` 触发时，写操作已经发生了。拦截要放在 `before_tool_call`，并且在所有执行路径都会经过的工具入口再强制校验一次。

</details>

## 参考

- [learn-claude-code：s04 Hooks](https://github.com/shareAI-lab/learn-claude-code/tree/main/s04_hooks)（参考事件挂点的讲解思路；事件名和控制行为以本项目代码为准。）
