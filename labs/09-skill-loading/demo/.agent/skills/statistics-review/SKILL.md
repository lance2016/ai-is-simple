---
name: statistics-review
description: 审查 stats.py 统计函数的计算逻辑、边界值和异常输入
---

# Statistics Review

1. 先读取 `stats.py`，确认函数当前的实现和调用方式。
2. 读取 `.agent/skills/statistics-review/scripts/inspect_stats.py`，再运行：

   ```bash
   python3 .agent/skills/statistics-review/scripts/inspect_stats.py stats.py
   ```

3. 根据脚本提示检查空输入、奇偶长度和数量边界。脚本只定位值得检查的代码，不判断结果是否正确。
4. 手动核对算法。`median()` 收到偶数个数值时应取中间两项的平均值；空输入应明确报错；`top_n()` 的数量不应超过列表长度。
5. 只报告能从源码确认的问题，并给出文件位置和最小修改建议。修复后运行项目已有的检查。
