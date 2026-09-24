---
name: stats-median
type: episodic
scope: project
source: 对 stats.py 的一次代码审查
description: 上次检查 stats.py 时发现，median() 对偶数个数字取错位置；还要检查空列表
---

# stats.py 的中位数排查记录

- **现象：** `median()` 把列表排序后直接返回 `ordered[len(ordered) // 2]`。
- **原因：** 偶数个数字时，中位数应是中间两项的平均值；当前写法只取了靠右的一项。
- **复查：** 看当前 `stats.py` 的实现，再检查奇数、偶数和空列表输入。旧记录可能已经过时，不能代替读取当前代码。
