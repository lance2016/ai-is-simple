# 第 00 章：Chat Completion —— 一次请求到底发生了什么？

![Chat Completion：一次请求的输入与输出](../../assets/chapter-00-chat-completion.png)

> **一句话总结：大模型不会自动知道你的应用发生了什么，它只会根据这一次请求提供给它的上下文生成下一条回复。**

Chat Completion（聊天补全）就是把一组消息发给模型，请它生成下一条回复。开始看 Agent 如何使用工具之前，先理解这次普通请求。

很多复杂的 Agent，最后都建立在这个简单结构上：

```text
你的程序
   ↓
构造上下文
   ↓
调用模型
   ↓
得到 assistant message（模型回复）
```

## 1. 先看最简单的一次请求

使用 OpenAI Python SDK 风格调用 DeepSeek：

```python
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

messages = [
    {"role": "system", "content": "你是一个简洁的 Python 助手。"},
    {"role": "user", "content": "Python 的 list 和 tuple 有什么区别？"},
]

response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
)

print(response.choices[0].message.content)
```

这里先只看懂一条关系：

```text
messages
   ↓
模型
   ↓
assistant message
```

这还不是 Agent，只是一次普通的大模型请求。

## 2. `messages` 到底是什么

`messages` 可以简单理解成：

> **这一次请求里，你希望模型看到的对话上下文。**

最常见的角色可以先这样理解：

| `role`（消息角色） | 可以先理解成 |
| --- | --- |
| `system` | 给模型的总体规则和身份 |
| `user` | 用户说的话 |
| `assistant` | 模型之前说过的话 |
| `tool` | 工具执行后返回给模型的结果 |

## 3. 模型没有自动记住上一轮

假设第一轮对话是：

```python
messages = [
    {"role": "user", "content": "我叫小明。"},
]
```

模型回答：

```text
你好，小明。
```

接下来用户问：“我叫什么？”

程序通常会把前面的内容再次放进上下文：

```python
messages = [
    {"role": "user", "content": "我叫小明。"},
    {"role": "assistant", "content": "你好，小明。"},
    {"role": "user", "content": "我叫什么？"},
]
```

模型之所以看起来“记得”之前的聊天，通常是因为应用程序把历史消息再次发送给了它。

> **每一次调用，都应该把它看成一次新的模型请求。**

这里讨论的是普通 API 调用的心智模型，不展开 ChatGPT 产品里的 Memory。

## 4. 一次请求到底长什么样

可以先把一次请求想成一个装上下文的盒子：

```text
┌─────────────────────────────┐
│       一次模型请求           │
│                             │
│  model                      │
│                             │
│  messages                   │
│   ├─ system                 │
│   ├─ 对话历史               │
│   ├─ 当前 user message      │
│   └─ assistant 历史消息     │
│                             │
│  tools（可选）              │
└──────────────┬──────────────┘
               ↓
              LLM
               ↓
┌─────────────────────────────┐
│      assistant message       │
│                             │
│  content                    │
│        或                   │
│  tool_calls                 │
└─────────────────────────────┘
```

核心结论是：

> 大模型真正做的事情，可以先粗略理解成：根据当前上下文，生成下一条 `assistant message`。

### 这条回复接下来有两条路

| 返回内容 | 程序下一步 | 适合的场景 |
| --- | --- | --- |
| `assistant.content` | 直接展示或继续处理文本 | 普通解释、改写、总结 |
| `assistant.tool_calls`（工具调用请求） | 程序执行工具，把 `role="tool"` 结果追加后再次请求 | 需要读文件、查日期、写入外部系统 |

`tools` 只是“可选能力说明”，不是每次都必须调用。模型可以选择直接回答；即使模型提出了 `tool_call`，也只是提出请求，真正执行仍由程序决定。

## 下一章会发生什么

如果模型返回 `tool_calls`，程序可以执行对应工具，再把结果加入下一次请求。第 01 章会把这个过程放进循环里；本章先记住：程序准备每次请求的上下文，模型根据它返回一条消息。

## 用 DeepSeek 跑起来

本章的完整代码在 [`code.py`](./code.py)。它只做五件事：

1. 构造 `messages`；
2. 调用一次 Chat Completion；
3. 把 assistant 回复 append 回 `messages`；
4. 再加入第二条 user message；
5. 再调用一次。

先配置 `.env`：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

运行：

```bash
uv run python chapters/00-chat-completion/code.py
```

重点观察这两行：

```python
messages.append(assistant_message.model_dump(exclude_none=True))
messages.append({"role": "user", "content": "我叫什么名字？"})
```

第一行保存模型之前的回复，第二行加入新的问题。多轮连续性来自这些消息被再次发送，而不是模型在请求之间自动记住了什么。

## 今天只记住

> **每次请求都由程序提供上下文；模型根据这份上下文生成下一条回复。历史消息要由程序再次发送。**

## 想一想

假设你和模型已经聊了 20 轮。现在用户发送第 21 条消息。

模型为什么还能理解前面聊过的内容？

是因为模型自己一直记着，还是因为程序做了什么？

<details>
<summary>参考思路（先自己想一想，再展开）</summary>

是程序做的。每次请求时，程序把前 20 轮的 user / assistant 消息重新放进 `messages` 发出去，模型只是在这一次请求里读到了它们。聊得越久，这份历史越长，这也是第 08 章要处理上下文变长的原因。

</details>

## 参考

- [DeepSeek OpenAI SDK 调用示例](https://api-docs.deepseek.com/api_samples/chat_python/)
- [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat)
