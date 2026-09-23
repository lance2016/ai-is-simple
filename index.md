---
layout: home

hero:
  name: AI 如此简单
  text: 一张图 + 一句话 + 一小段代码
  tagline: 面向刚开始学习 AI / LLM / Agent 的开发者。先看懂图，再理解概念，最后跑起一小段代码，亲手做出一个 Coding Agent。
  actions:
    - theme: brand
      text: 从第 00 章开始
      link: /chapters/00-chat-completion/
    - theme: alt
      text: 项目介绍
      link: /intro
    - theme: alt
      text: 直接做实战
      link: /labs/01-mini-coding-agent/

features:
  - title: 基础核心
    details: 00～03 章：一次模型请求、最小循环、工具调用、权限。读完就能看懂一个最小但完整的 Agent。
    link: /chapters/00-chat-completion/
  - title: 按场景选用的能力
    details: Hooks、Planning、Subagents、Memory、MCP、Workflow……遇到对应问题再读，不必全部具备。
    link: /intro#学习路线
  - title: 工程化
    details: 15～17 章：用 Harness 把用到的能力组织起来，再用流程和目标决定 Agent 何时结束。
    link: /chapters/15-integrated-harness/
---

## 学习路线

![AI Agent 学习路线](./assets/learning-roadmap.png)

18 章不是一条必须走完的直线，而是**一条主干 + 一组按场景选用的能力**。先读主干（00～03、15），其余章节按需要挑着读。

## 实战三步走

| 阶段 | 内容 |
| --- | --- |
| ① 主干 | [Lab 01 · Mini Coding Agent](/labs/01-mini-coding-agent/)：`read / write / edit / bash` 四个工具 + 网页界面 + 授权确认 |
| ② 挂能力 | [Lab 02 记忆](/labs/02-memory/) · [Lab 03 子 Agent](/labs/03-subagent/) · [Lab 04 MCP](/labs/04-mcp/) · [Lab 05 测试验证](/labs/05-verify/)：每个只写一个扩展文件，Agent Loop 一行不改 |
| ③ 看工程实现 | Pi 扩展阅读：理解 TypeScript Harness 如何用 Extension、Skill、Session 扩展 |
