"""几个简单的统计函数，留给 Agent 做代码审查练习。"""


def average(numbers):
    # 平均值
    return sum(numbers) / len(numbers)


def median(numbers):
    # 中位数
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    return ordered[middle]


def top_n(numbers, n):
    # 最大的 n 个数
    result = []
    ordered = sorted(numbers)
    for i in range(n):
        result.append(ordered[len(ordered) - 1 - i])
    return result
