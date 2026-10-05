# 第 03 章：Permission——工具执行前的权限判断

![Permission：工具执行前的权限检查](../../assets/chapter-03-permission.png)

> **一句话总结：模型提出工具调用，应用程序决定它能不能执行。**

模型返回 `write_note(path, content)`，不代表文件已经写入。Harness（连接模型、工具和运行规则的应用代码）应在调用工具函数前检查这次操作；需要确认时，先展示具体内容，得到同意后再执行。

## 沿着图看执行顺序

本章的边界在“模型提议”与“工具执行”之间：

1. 模型提出工具和参数；
2. 程序检查工具、参数和资源范围；
3. 策略决定直接允许、要求确认，或拒绝；
4. 只有通过检查的调用才进入工具函数。

这三种结果在代码里分别是 `ALLOW`、`ASK` 和 `DENY`。它们是应用自己的策略决定，不由提示词或模型回答决定。DeepSeek 的工具调用文档也把模型返回的 function call 和应用实际执行函数分成两步：函数需要由应用提供并调用。

## 权限判断和用户确认不是一回事

一个常见面试追问是：“用户点了允许，操作就一定合法的吗？”不一定。确认只表示用户同意眼前这个动作；服务端仍要检查当前用户能不能改这个资源、目标和参数是否在允许范围内。

| 机制 | 它回答的问题 | 示例中的做法 |
| --- | --- | --- |
| 参数校验 | 请求格式和路径是否符合预期？ | 路径不能跳出项目，读取范围有限 |
| 授权策略 | 当前调用者能否执行此操作？ | 示例只允许写入 `notes/` |
| 用户确认 | 用户是否同意这一次具体写入？ | 展示路径和完整内容后再询问 |
| 执行隔离 | 即使应用判断出错，影响范围能否被限制？ | 生产环境还应使用文件、进程或网络隔离 |

本例是单人命令行程序，所以 `input()` 只是演示“先问、后执行”。多人服务要从已认证的服务端会话取得用户身份和资源归属，不能把模型参数里的 `user_id` 当成身份凭证。确认也应绑定到当前用户和这次具体操作；参数变化后，需要重新确认。未知工具、格式错误的参数和越界路径都应失败关闭，也就是拒绝执行。

提示词可以引导模型，但不能当权限边界。仓库文件、网页和工具返回内容都可能包含恶意指令；读取到内容不代表应照做。权限校验要放在所有工具调用必经的执行入口，工具注解或模型自述也不能代替程序检查。

## 代码里新增了哪一步

第 02 章的最小执行方式是：

```python
handler = TOOL_HANDLERS[name]
result = handler(**arguments)
```

本章先得到明确的策略结果，再处理确认，最后才调用处理函数：

```python
decision, reason = check_permission(name, arguments)

if decision is PermissionDecision.DENY:
    return f"Permission denied: {reason}"
if decision is PermissionDecision.ASK and not confirm_write(arguments):
    return "Permission denied: 用户没有确认写入"

return TOOL_HANDLERS[name](**arguments)
```

把策略判断与询问用户分开，方便面试时解释各自职责：策略决定“这类动作是否可做”，确认流程决定“当前这次动作是否获准继续”。真实服务还要在执行前再次核对用户、目标和参数，避免把一份旧确认复用到不同动作上。

示例只开放了很小的范围：

- `read_file` 只读取根目录指定的教学文档和 `chapters/` 下的文件，并拒绝 `.env`、`.git` 等路径；
- `write_note` 只写入 `notes/`，确认提示会展示写入路径和完整内容；
- `delete_file` 永远拒绝，模型即使提出调用也不会进入工具函数。

每次写入都弹确认比较容易造成“确认疲劳”，让人习惯性点击同意。真实产品通常会结合风险、操作范围和执行隔离来控制提示频率；确认框不能单独承担全部安全责任。[Anthropic 对权限提示与沙箱的说明](https://www.anthropic.com/engineering/claude-code-sandboxing)给出了这类取舍的实际案例。

## 运行示例

完整代码在 [`code.py`](./code.py)，它沿用第 02 章的 Tool Use，只展开权限边界。先在 `.env` 中配置：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

运行：

```bash
uv run python chapters/03-permission/code.py
```

可以依次试试读取 `README.md`、写入 `notes/today.txt`，再请求删除 `README.md`。观察删除请求：即使模型发出了工具调用，程序也会在执行前拒绝它。

### 面试追问

如果用户确认写入 `notes/today.txt`，但执行前目标路径或文件内容变了，还能沿用这次确认吗？

<details>
<summary>参考思路</summary>

不能。确认应对应到具体用户和具体参数；操作内容变化，就重新校验并再次确认。执行入口还要确认授权，不能只凭一个 `confirmed=True` 就放行。

</details>

## 参考

- [learn-claude-code：s03 Permission](https://github.com/shareAI-lab/learn-claude-code/tree/main/s03_permission)
- [DeepSeek Tool Calls 官方说明](https://api-docs.deepseek.com/guides/tool_calls/)
- [Anthropic：Beyond permission prompts—sandboxing Claude Code](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [OWASP：AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)
