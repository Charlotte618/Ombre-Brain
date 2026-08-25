"""浮现区的新近性：预留位置 + 久未浮现的新桶护栏（3.6.0）。

两个问题同源——**都是「累积量」被当成了「状态」**：

1. 权重是累积的。旧桶靠历史访问把分数攒到很高（实测最高 51），新桶从 0 起步，
   永远排不进前列。潮汐后醒来 14 条浮现里 12 条是一个月前的。
2. `activation_count == 0` 有两种意思：「很久没被想起」和「还没来得及被想起」。
   判据本身分不出来，于是几分钟前刚写下的桶被标着 💤 放进「久未浮现」区。

对应两条修法：给浮现区留几个位置给近 7 天的桶（配额，不动打分公式），
以及给久未浮现池加一个 24 小时的年龄下限。
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

import tools._runtime as rt
from tools.breath.surface import surface_default


class DisabledEmbedding:
    enabled = False


class WeightedDecay:
    """按 metadata 里预置的 score 返回，模拟"旧桶攒了很高的权重"。"""

    is_running = True

    async def ensure_started(self):
        return None

    def calculate_score(self, metadata):
        return float(metadata.get("_score", metadata.get("importance") or 5))


class PlainBucketManager:
    def __init__(self, buckets):
        self.buckets = list(buckets)

    async def list_all(self, include_archive=False):
        return list(self.buckets)

    async def get_stats(self):
        return {"permanent_count": 0, "dynamic_count": len(self.buckets)}

    def footprint_snapshot(self):
        raise RuntimeError("no footprint in tests")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _bucket(bucket_id, *, age_days=0, age_hours=0, score=1.0,
            importance=5, activation_count=3):
    created = datetime.now() - timedelta(days=age_days, hours=age_hours)
    return {
        "id": bucket_id,
        "content": f"{bucket_id} 的正文。",
        "metadata": {
            "name": bucket_id,
            "type": "dynamic",
            "importance": importance,
            "domain": ["回归测试"],
            "created": _iso(created),
            "last_active": _iso(created),
            "activation_count": activation_count,
            "_score": score,
        },
    }


def _install(monkeypatch, manager, surfacing=None):
    monkeypatch.setattr(rt, "config", {"surfacing": surfacing or {}})
    monkeypatch.setattr(rt, "bucket_mgr", manager)
    monkeypatch.setattr(rt, "decay_engine", WeightedDecay())
    monkeypatch.setattr(rt, "embedding_engine", DisabledEmbedding())
    monkeypatch.setattr(rt, "logger", MagicMock())
    monkeypatch.setattr(rt, "mark_op", None)
    # 浮现区自带两处随机：top20 内洗牌、3% 偶遇。这里测的是排序规则，
    # 不关掉的话用例会时绿时红——而"偶尔红一次"比一直红更难查。
    monkeypatch.setattr("tools.breath.surface.random.shuffle", lambda _seq: None)
    monkeypatch.setattr("tools.breath.surface.random.random", lambda: 1.0)


# --------------------------------------------------------------
# 预留位置
# --------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_buckets_get_reserved_slots_against_high_weight_veterans(
    monkeypatch,
):
    """这就是现场：一堆权重极高的旧桶 + 几条新桶，新桶原本一条都进不来。"""
    veterans = [
        _bucket(f"old-{i}", age_days=30, score=51.0 - i) for i in range(10)
    ]
    fresh = [_bucket(f"new-{i}", age_days=i, score=0.5) for i in range(3)]
    _install(monkeypatch, PlainBucketManager(veterans + fresh))

    out = await surface_default(max_results=10, max_tokens=100_000, tag_filter=[])

    surfaced = [b["id"] for b in veterans + fresh if f"[bucket_id:{b['id']}]" in out]
    assert any(bid.startswith("new-") for bid in surfaced), surfaced
    # 三个位置都该给到新桶
    assert sum(1 for bid in surfaced if bid.startswith("new-")) == 3
    # 权重最高的那条不能被挤掉——头版还是头版
    assert "[bucket_id:old-0]" in out


@pytest.mark.asyncio
async def test_recent_slots_are_sorted_newest_first(monkeypatch):
    fresh = [_bucket(f"new-{i}", age_days=i, score=0.5) for i in range(3)]
    veterans = [_bucket(f"old-{i}", age_days=30, score=51.0) for i in range(10)]
    _install(monkeypatch, PlainBucketManager(veterans + fresh))

    out = await surface_default(max_results=10, max_tokens=100_000, tag_filter=[])

    positions = [out.index(f"[bucket_id:new-{i}]") for i in range(3)]
    assert positions == sorted(positions), "新的应该排在前面"


@pytest.mark.asyncio
async def test_buckets_older_than_the_window_do_not_claim_the_quota(monkeypatch):
    """8 天前的桶不算「近期」，配额不该被它占掉。"""
    veterans = [_bucket(f"old-{i}", age_days=30, score=51.0) for i in range(10)]
    stale = _bucket("eight-days", age_days=8, score=0.5)
    _install(monkeypatch, PlainBucketManager(veterans + [stale]))

    out = await surface_default(max_results=5, max_tokens=100_000, tag_filter=[])

    assert "[bucket_id:eight-days]" not in out


@pytest.mark.asyncio
async def test_quota_never_takes_more_than_half_the_surface(monkeypatch):
    """预留不能变成霸占：max_results 小的时候配额要跟着缩。"""
    veterans = [_bucket(f"old-{i}", age_days=30, score=51.0) for i in range(10)]
    fresh = [_bucket(f"new-{i}", age_days=0, score=0.5) for i in range(5)]
    _install(monkeypatch, PlainBucketManager(veterans + fresh))

    out = await surface_default(max_results=4, max_tokens=100_000, tag_filter=[])

    new_count = sum(1 for i in range(5) if f"[bucket_id:new-{i}]" in out)
    assert new_count <= 2, f"4 个位置里新桶占了 {new_count} 个"


@pytest.mark.asyncio
async def test_recent_slots_zero_restores_the_old_behaviour(monkeypatch):
    """留了关掉的口子：recent_slots=0 回到 3.5.0 的纯权重排序。"""
    veterans = [_bucket(f"old-{i}", age_days=30, score=51.0 - i) for i in range(10)]
    fresh = [_bucket("new-0", age_days=0, score=0.5)]
    _install(
        monkeypatch,
        PlainBucketManager(veterans + fresh),
        surfacing={"recent_slots": 0},
    )

    out = await surface_default(max_results=5, max_tokens=100_000, tag_filter=[])

    assert "[bucket_id:new-0]" not in out


@pytest.mark.asyncio
async def test_quota_is_a_noop_when_everything_is_already_recent(monkeypatch):
    """前排本来就都是新桶时不该重排顺序——配额已经自然满足了。"""
    fresh = [_bucket(f"new-{i}", age_days=0, score=10.0 - i) for i in range(5)]
    _install(monkeypatch, PlainBucketManager(fresh))

    out = await surface_default(max_results=5, max_tokens=100_000, tag_filter=[])

    positions = [out.index(f"[bucket_id:new-{i}]") for i in range(5)]
    assert positions == sorted(positions), "全是新桶时应保持权重顺序"


# --------------------------------------------------------------
# 久未浮现的新桶护栏
# --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_bucket_created_minutes_ago_is_not_long_unsurfaced(monkeypatch):
    """刚写下的桶天然 activation_count=0，不该被标成「久未浮现」。

    冷启动通道最多接 2 条，第 3 条起就漏进这个池——所以这里放 4 条。
    """
    fresh_important = [
        _bucket(f"fresh-{i}", age_hours=0, score=0.5,
                importance=9, activation_count=0)
        for i in range(4)
    ]
    filler = [_bucket(f"old-{i}", age_days=30, score=20.0) for i in range(5)]
    _install(monkeypatch, PlainBucketManager(filler + fresh_important))

    out = await surface_default(max_results=5, max_tokens=100_000, tag_filter=[])

    passive_section = out.split("=== 久未浮现 ===")
    if len(passive_section) > 1:
        for i in range(4):
            assert f"[bucket_id:fresh-{i}]" not in passive_section[1], (
                f"fresh-{i} 是几分钟前才写下的，不该出现在久未浮现区"
            )


@pytest.mark.asyncio
async def test_an_old_never_activated_bucket_still_counts_as_long_unsurfaced(
    monkeypatch,
):
    """护栏只挡新桶。真正久未浮现的还得照常出现，否则就是把功能删了。

    前两条 never-activated 会被冷启动通道接走（那是另一条独立机制），
    所以这里放三条——第三条才落到久未浮现池里，正是报告里说的"第 3 个起溢出"。
    """
    decoys = [
        _bucket(f"cold-{i}", age_days=40, score=30.0,
                importance=9, activation_count=0)
        for i in range(2)
    ]
    forgotten = _bucket(
        "forgotten", age_days=40, score=0.1, importance=9, activation_count=0
    )
    filler = [_bucket(f"old-{i}", age_days=30, score=20.0) for i in range(5)]
    _install(monkeypatch, PlainBucketManager(decoys + [forgotten] + filler))

    out = await surface_default(max_results=3, max_tokens=100_000, tag_filter=[])

    assert "=== 久未浮现 ===" in out
    assert "[bucket_id:forgotten]" in out.split("=== 久未浮现 ===")[1]
