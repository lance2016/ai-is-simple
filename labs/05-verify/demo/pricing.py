"""一个故意留了 bug 的小模块，给 Agent 练手用。"""


def apply_discount(price: float, percent: float) -> float:
    """打折。percent=20 表示便宜 20%，也就是打八折。"""
    if not 0 <= percent <= 100:
        raise ValueError("percent 必须在 0 到 100 之间")
    return price * percent / 100


def order_total(items: list[tuple[float, int]]) -> float:
    """items 是 (单价, 数量) 的列表，返回总价。"""
    return sum(price for price, quantity in items)
