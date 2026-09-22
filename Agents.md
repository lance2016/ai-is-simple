# Agents.md

这是 `ai-is-simple` 项目的协作偏好。后续修改内容、代码和配图时，优先遵守这里的约定。

## 项目定位

- 项目名称：AI 如此简单。
- 面向人群：刚开始接触 AI、Agent 和大模型的初学者。
- 内容来源：参考 `shareAI-lab/learn-claude-code`，但用自己的话重新解释，不把本项目写成原项目的官方文档。
- 核心目标：让读者先看懂图，再理解概念，最后看懂一小段代码。

## 项目分层

- 第一部分是理论篇：`chapters/00-17/`，每章只讲一个 Agent 机制，代码保持独立和短小。
- 第二部分是实战篇：`labs/`，把理论机制重新组合成可运行的小项目。
- 实战篇可以参考真实 Agent Harness（例如 Pi）的设计理念，但不要直接复制复杂实现；先保持 Python + DeepSeek + OpenAI SDK，确保初学者能读懂和运行。
- 实战篇的最小 Coding Agent 默认采用 Pi 风格的四工具边界：`read`、`write`、`edit`、`bash`；列目录、搜索代码、查看状态和运行检查等能力优先通过受控的 `bash` 完成，不要为了每个动作单独注册工具。
- Pi 只作为扩展阅读或 TypeScript 实战入口，不替代理论篇的基础循环。

## 文字偏好

- 开头先用一句话总结核心结论。
- 先图后文，再结合代码展开。
- 使用中文、短句和生活化的例子。
- 多用小标题、列表和短段落，避免大段说教。
- 每一章只讲一个核心概念，不追求一次讲完所有细节。
- 第一次出现的术语要顺手解释，例如 Harness、tool call、context。
- 结尾保留一句“今天只记住”和一个简单思考题。

## 配图偏好

- 每一章的首页主视觉必须使用 ImageGen 工具生成或编辑，不能直接用 Mermaid 作为最终主图；后续生成章节时不要跳过 ImageGen。
- 所有章节主图统一放在根目录 `assets/`，文件名必须带章节编号和主题，例如 `chapter-02-tool-use.png`，不要在章节目录下再创建图片目录。
- 实战篇封面图统一放在根目录 `assets/`，使用 `lab-NN-topic.png` 命名，例如 `lab-01-mini-coding-agent.png`。
- 每一章只保留一张主图，避免两张表达同一概念的图重复出现。
- 优先使用已经确认过的、简洁、克制、信息层级清楚的教学图。
- 新章节配图生成时，优先参考已经确认的章节主图保持系列统一；当前系列参考图为 `assets/chapter-01-agent-loop.png`。
- 当前已确认的章节主图：`assets/chapter-00-chat-completion.png`、`assets/chapter-01-agent-loop.png`、`assets/chapter-02-tool-use.png`、`assets/chapter-03-permission.png`、`assets/chapter-04-hooks.png`、`assets/chapter-05-planning.png`、`assets/chapter-06-subagents.png`、`assets/chapter-07-skill-loading.png`、`assets/chapter-08-context-compact.png`、`assets/chapter-09-memory.png`、`assets/chapter-10-tasks.png`、`assets/chapter-11-background-tasks.png`、`assets/chapter-12-cron-scheduler.png`、`assets/chapter-13-agent-teams.png`、`assets/chapter-14-mcp-plugin.png`、`assets/chapter-15-integrated-harness.png`、`assets/chapter-16-workflow-runtime.png`、`assets/chapter-17-goal-loop.png`。
- 图片中的文字必须清晰可辨认，不能依赖随机生成的长段文字。
- 配色保持简洁：少量颜色表达角色或状态，不用复杂渐变和装饰性噪点。
- 流程图需要明确区分：输入、模型决策、工具执行、工具结果、终止输出。
- Mermaid 只能用于前期结构草稿或代码解释；正式章节首页不得用 Mermaid 替代 ImageGen 主图，也不要在同一章同时放 Mermaid 和含义相同的图片。

## 代码偏好

- 默认使用 DeepSeek 模型。
- 默认模型：`deepseek-flash`，允许通过 `DEEPSEEK_MODEL` 覆盖。
- 默认使用 OpenAI Python SDK。
- 默认 API 地址：`https://api.deepseek.com`，允许通过 `DEEPSEEK_BASE_URL` 覆盖。
- API Key 从 `.env` 读取，不要写进代码或提交到 Git。
- 代码要适当添加注释，解释“为什么这样做”，不要给每一行都加注释。
- 初学者示例优先使用安全、范围明确的工具；如果使用 `bash`，必须限制工作区、阻止敏感路径，并对写入、执行和不确定命令保留确认机制。
- 保留可运行的小例子，并在文档里告诉读者如何运行。
- 各章 `code.py` 是独立教学示例，不要把它们描述成已经自动拼成一个完整生产级 Agent。
- README 的代码片段只展示本章新增或关键变化，不重复粘贴完整循环；完整可运行代码放在 `code.py`。
- 每章适当说明“什么时候用、什么时候不用、代价或相邻概念的区别”，避免只讲 API 用法。

## 每章推荐结构

```text
# 章节标题

主图

一句话总结

## 先看图
用 3～5 个要点说明图中的关系

## 用生活例子理解
一个简短类比

## 用 DeepSeek 跑起来
一小段真实代码 + 关键注释

## 今天只记住
一句话复盘

## 想一想
一个简单问题
```

## 修改前检查

- 是否仍然只讲一个概念？
- 开头是否能用一句话说清楚？
- 图和文字是否在解释同一件事？
- 是否出现大段难读的文字？
- 示例代码是否使用 DeepSeek + OpenAI SDK？
- 是否通过语法检查，并且没有把 API Key 写入仓库？
