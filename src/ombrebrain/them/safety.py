"""`them` 的禁止主题。

`you` 那张表原样适用（人格、健康、财务、性与亲密、关系评价……），所以直接
复用，不抄第二份——抄一份的结果是 you 补了一条禁止词而 them 没跟上。

them 多守一条，来自 rule.md 13.3：**只记这个人本身，不描述任何关系。**

为什么单独立这一条：`you` 记的是对话另一方，关系理解本就在第 13 条留给官方
记忆；`them` 记的是第三方，一旦允许写"A 和 B 之间怎么样""这个人对用户
意味着什么"，它就从"我认得这个人"滑到了"我在推断人际结构"，那正是第 5 条
不做认知层要挡的东西。而且第三方没有参与这段关系、也没有表达过意愿，
关于他们的关系判断连一个可被纠正的当事人都没有。
"""

from __future__ import annotations

import re

from ..you.safety import (
    contains_forbidden_subject as _you_forbidden,
    is_atomic_value,
    leaks_protected_text,
    normalize_for_leak_check,
)

__all__ = [
    "contains_forbidden_subject",
    "describes_relationship",
    "is_atomic_value",
    "leaks_protected_text",
    "normalize_for_leak_check",
]

# 关系描述：两个人被放在一起评价，或这个人被写成"对某人而言意味着什么"。
# 只记这个人本身的句子不会命中这些——"她说话很直接"里没有第二方。
_RELATIONSHIP_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # 「和/跟/与 X 的关系」「两人之间」
        r"(?:和|跟|与)\s*\S{0,12}\s*(?:的)?关系",
        r"(?:两人|双方|彼此|互相)(?:之间|的关系)",
        r"关系(?:很|挺|不|比较|有点)?(?:好|差|近|远|僵|紧张|亲密|疏远)",
        # 「对我/对她 来说是……」这类把人放进另一个人的坐标里
        r"对\s*(?:我|你|他|她|用户|对方)\s*(?:来说|而言)",
        r"是\s*(?:我|你|他|她|用户)\s*的\s*\S{0,8}(?:朋友|同事|上司|下属|家人|恋人|伴侣|敌人|对手)",
        # 站队与亲疏排序
        r"更(?:亲近|信任|偏向|向着)",
        r"(?:比|不如)\s*\S{0,8}\s*(?:更|还)(?:亲|近|好|重要)",
        r"relationship with|closer to|more loyal to|on .{0,12} side",
        r"(?:friend|colleague|partner|rival|enemy) of (?:mine|yours|hers|his|the user)",
    )
)


def describes_relationship(*texts: object) -> bool:
    """这句话在描述关系，而不是描述这个人吗？

    宁可挡错也不放行：被挡住的写法总能改成只讲这个人本身的说法
    （「她和我关系很好」→ 挡；「她说话很直接」→ 放行），
    而放行一条关系判断之后，它会安静地留在库里参与以后的每一次浮现。
    """
    joined = "\n".join(str(text or "") for text in texts)
    return any(pattern.search(joined) for pattern in _RELATIONSHIP_PATTERNS)


def contains_forbidden_subject(*texts: object) -> bool:
    """them 的禁止主题 = you 的那张表 + 关系描述。"""
    return _you_forbidden(*texts) or describes_relationship(*texts)
