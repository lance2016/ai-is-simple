<div align="center">

<img src="./assets/readme-hero.png" alt="AI 如此简单" width="100%" />

# AI 如此简单

**一张图 + 一句话 + 一小段代码，把一个 AI Agent 概念真正讲明白。**

面向刚开始学习 **AI / LLM / Agent** 的开发者。  
不堆术语，不先上框架，从一次最普通的 LLM 请求开始，再一步一步搭出完整 Agent。

</div>

---

## 这是什么？

很多 Agent 教程一上来就是框架、配置和几十个概念。

这个项目反过来：

> **先理解最小原理，再逐步增加能力。**

每一章只解决一个问题：

1. **先看图**：建立直觉；
2. **一句话理解**：先抓住核心；
3. **生活化例子**：把抽象概念落地；
4. **一小段代码**：真正跑起来。

最终你会从一次普通 Chat Completion 和一个最小循环开始，逐渐理解：

**Chat Completion → Agent Loop → Tool Use → Permission → Planning → Subagents → Skills → Context → Memory → Tasks → MCP → Agent Teams → Harness → Workflow**

---

## 一张图看懂这门课

<img src="./assets/learning-roadmap.png" alt="AI Agent 学习路线" width="100%" />

学习主线可以先记成：

```text
Chat Completion
      ↓
Agent Loop
      ↓
Tool Use
      ↓
Permission
      ↓
Planning / Subagents / Memory / MCP ...
```

可以把一个成熟 Agent 想成不断升级的小助手：

> **会思考 → 会使用工具 → 会规划 → 会记忆 → 会协作 → 会长期运行**

所有复杂 Agent，最后都建立在同一个最小循环上：

```text
用户任务
   ↓
模型决定下一步
   ↓
需要工具？ ── 否 ──→ 输出答案
   │
   是
   ↓
执行工具
   ↓
工具结果返回模型
   └────────────→ 再次决定
```

---

## 学习路线

目前已完成 **7 / 18** 章。

| 状态 | 章节 | 核心概念 | 只记住一句话 |
| --- | --- | --- | --- |
| ✅ | [00 · Chat Completion](./chapters/00-chat-completion/) | 一次模型请求 | 模型只知道这一次请求提供给它的上下文 |
| ✅ | [01 · Agent Loop](./chapters/01-agent-loop/) | Agent 的最小循环 | 模型决定下一步，工具负责执行 |
| ✅ | [02 · Tool Use](./chapters/02-tool-use/) | 工具调用与分发 | 加工具，不需要重写整个循环 |
| ✅ | [03 · Permission](./chapters/03-permission/) | 权限 | 能做，不代表应该直接做 |
| ✅ | [04 · Hooks](./chapters/04-hooks/) | 扩展点 | 在关键位置留下可插拔接口 |
| ✅ | [05 · Planning](./chapters/05-planning/) | 计划 | 复杂任务先拆，再执行 |
| ✅ | [06 · Subagents](./chapters/06-subagents/) | 子 Agent | 大任务拆小，并隔离上下文 |
| ⏳ | 07 · Skill Loading | 技能加载 | 用到什么，再加载什么 |
| ⏳ | 08 · Context Compact | 上下文压缩 | 上下文有限，要主动腾空间 |
| ⏳ | 09 · Memory | 记忆 | 重要信息跨对话保留下来 |
| ⏳ | 10 · Tasks | 任务管理 | 把目标变成可追踪的步骤 |
| ⏳ | 11 · Background Tasks | 后台任务 | 慢任务不应该阻塞 Agent |
| ⏳ | 12 · Cron | 定时任务 | 让任务在未来自动发生 |
| ⏳ | 13 · Agent Teams | 多 Agent 协作 | 一个 Agent 忙不过来，就分工 |
| ⏳ | 14 · MCP | 外部能力协议 | 用统一方式连接外部工具 |
| ⏳ | 15 · Agent Harness | Agent 运行底座 | 把工具、上下文、权限和执行组织起来 |
| ⏳ | 16 · Workflow Runtime | 工作流 | 把稳定的编排方式沉淀成流程 |
| ⏳ | 17 · Goal Loop | 目标循环 | 目标决定 Agent 什么时候真正结束 |

> 不需要一次理解全部概念。  
> **按顺序学习即可，每一章都建立在前一章之上。**

---

## 5 分钟跑起来

### 1. 克隆项目

```bash
git clone https://github.com/lance2016/ai-is-simple.git
cd ai-is-simple
```

### 2. 创建 Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

### 3. 配置模型

```bash
cp .env.example .env
```

然后填写：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

### 4. 运行第 00 章

```bash
python chapters/00-chat-completion/code.py
```

先从一次最普通的模型请求开始，再继续阅读第 01 章，搭出最小可运行 Agent。

---

## 每章都长什么样？

```text
主图
 ↓
一句话总结
 ↓
生活化解释
 ↓
最小可运行代码
 ↓
今天只记住
 ↓
一个思考题
```

项目刻意避免两件事：

- ❌ 一开始堆大量框架 API；
- ❌ 用十几个术语解释另一个术语。

更希望你最后能做到：

> **合上文档，也能用自己的话解释这个概念。**

---

## 项目结构

```text
ai-is-simple/
├── README.md
├── Agents.md
├── STYLE_GUIDE.md
├── SOURCES.md
├── assets/
│   ├── readme-hero.png
│   ├── learning-roadmap.png
│   ├── chapter-00-chat-completion.png
│   ├── chapter-01-agent-loop.png
│   ├── chapter-02-tool-use.png
│   ├── chapter-03-permission.png
│   ├── chapter-04-hooks.png
│   ├── chapter-05-planning.png
│   └── chapter-06-subagents.png
├── requirements.txt
├── .env.example
└── chapters/
    ├── 00-chat-completion/
    │   ├── README.md
    │   └── code.py
    ├── 01-agent-loop/
    │   ├── README.md
    │   └── code.py
    ├── 02-tool-use/
    │   ├── README.md
    │   └── code.py
    ├── 03-permission/
    │   ├── README.md
    │   └── code.py
    ├── 04-hooks/
    │   ├── README.md
    │   └── code.py
    ├── 05-planning/
    │   ├── README.md
    │   └── code.py
    └── 06-subagents/
        ├── README.md
        └── code.py
```

每个章节都是一个独立的小单元：

**README 负责讲明白，代码负责跑明白。**

---

## 默认技术栈

为了降低学习成本，项目尽量保持统一：

- **Python**
- **DeepSeek**
- **OpenAI Python SDK**
- **OpenAI-compatible API**
- `.env` 管理本地配置

重点不是某个模型或框架，而是理解 **Agent 背后的通用机制**。

---

## 适合谁？

如果你：

- 刚开始学习 AI Agent；
- 会一点 Python，但对 Agent 架构没有完整心智模型；
- 用过 LangChain / LangGraph / Claude Code，却想知道底层到底发生了什么；
- 正在准备 AI 应用开发 / Agent 工程相关面试；

这个项目就是为这种学习方式准备的。

---

## 项目边界

这是个人学习与教学项目，不是 `learn-claude-code`、DeepSeek 或其他项目的官方文档。

部分学习主线受到 [`shareAI-lab/learn-claude-code`](https://github.com/shareAI-lab/learn-claude-code) 启发，但会重新组织概念、解释、插图与代码，让内容更适合初学者阅读。

- 配图规范：[STYLE_GUIDE.md](./STYLE_GUIDE.md)
- 项目协作规范：[Agents.md](./Agents.md)
- 参考来源：[SOURCES.md](./SOURCES.md)

---

<div align="center">

### 从一次请求开始，慢慢看懂整个 Agent 世界。

如果这个项目对你有帮助，欢迎 ⭐ Star 或一起补充新的章节。

</div>
