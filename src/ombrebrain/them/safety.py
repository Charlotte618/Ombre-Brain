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


# 第一/第二人称指代。them 记的是「这个人本身」，而一句只讲这个人的话
# **不需要提到我**——「他评审时先问怎么退」不提我，「他跟我配合得顺」必须提。
# 所以「出现了人称」本身就是「这句话在讲两个人之间」的结构性信号。
_PRONOUN_RE = re.compile(
    r"(?:我们|咱们|我|咱|本人|自己人)"
    r"|(?<![A-Za-z])(?:we|us|our|me|myself)(?![A-Za-z])",
    re.IGNORECASE,
)


def describes_relationship(*texts: object) -> bool:
    """这句话在描述关系，而不是描述这个人吗？

    ## 两道判据，人称那道才是主力

    第一版只有一张关系句式表。真机试了六句，**漏掉四句**：
    「他跟我配合得比别人顺」「他比别人更懂我」「他站在我这边」
    「我们合作起来很顺」——它只拦得住字面出现「关系」「对我来说」的那两句。
    中文表达关系的方式太多，靠补词表永远补不完。

    换成结构性的判据：**句子里出现第一人称，就是在讲两个人之间。**
    them 记的是这个人本身，「他评审时先问怎么退」不需要提到我；
    一旦提到我，这句话的主语就不再只是他了。上面六句全部命中。

    句式表留着，它管的是不含人称的那一类——「A 和 B 之间有点僵」。

    ## 为什么宁可挡错

    被挡住的写法总能改成只讲这个人本身的说法（「他跟我配合得顺」→
    「他做事节奏快」）。而放行一条关系判断之后，它会安静地留在库里，
    参与以后的每一次浮现，还没有一个可被纠正的当事人。

    代价是「他怎么称呼我」这类也会被挡。那是有意的：那件事讲的是
    他与我之间，不是他本身。
    """
    joined = "\n".join(str(text or "") for text in texts)
    if _PRONOUN_RE.search(joined):
        return True
    return any(pattern.search(joined) for pattern in _RELATIONSHIP_PATTERNS)


def contains_forbidden_subject(*texts: object) -> bool:
    """them 的禁止主题 = you 的那张表 + 关系描述。"""
    return _you_forbidden(*texts) or describes_relationship(*texts)
