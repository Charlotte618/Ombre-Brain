"""检索与强化解耦（3.6.0）。

3.6.0 之前，`breath_search` 对**每一条命中**都 touch()：刷新 last_active、
activation_count +1、触发时间涟漪。于是产生了一条谁都没打算要的规则——
**查得勤 == 更重要**。

实际发生的事：为核对事实、debug、反复找同一件事而读一条记忆，读着读着它的
权重就爬到最高（实测积到 51），新桶再也排不进浮现区。

检索是「我去找它」，强化是「找到之后，这条确实要紧」。前者是我的动作，
后者是关于这条记忆的判断，只有读完才做得出来。绑在一起等于让读取行为自己
给自己投票。

这个文件钉两件事：**检索一条都不 touch**，以及**显式强化仍然有效**。
少了后半条，这就不是解耦而是把强化删了。
"""

from unittest.mock import MagicMock

import pytest

from errors import ToolInputError

import tools._runtime as rt
from tools.breath import dispatch as breath_dispatch
from tools.trace import dispatch as trace_dispatch


class DisabledEmbedding:
    enabled = False


class NoopDecay:
    is_running = True

    async def ensure_started(self):
        return None

    def calculate_score(self, metadata):
        return float(metadata.get("importance") or 5)


class CountingBucketManager:
    """记下所有强化动作。touch / touch_many 都要盯——漏一个就等于没解耦。"""

    def __init__(self, buckets):
        self.buckets = list(buckets)
        self.touched: list[str] = []

    async def get(self, bucket_id):
        for b in self.buckets:
            if b["id"] == bucket_id:
                return b
        return None

    async def get_including_archive(self, bucket_id):
        return await self.get(bucket_id)

    async def search(self, _query, **_kwargs):
        return list(self.buckets)

    async def list_all(self, include_archive=False):
        return list(self.buckets)

    async def touch(self, bucket_id, ripple=True):
        self.touched.append(bucket_id)

    async def touch_many(self, bucket_ids, ripple=False):
        self.touched.extend(bucket_ids)

    async def get_stats(self):
        return {"permanent_count": 0, "dynamic_count": len(self.buckets)}

    def footprint_snapshot(self):
        raise RuntimeError("no footprint in tests")


def _bucket(bucket_id, content, *, activation_count=3):
    return {
        "id": bucket_id,
        "content": content,
        "metadata": {
            "name": bucket_id,
            "type": "dynamic",
            "importance": 7,
            "domain": ["回归测试"],
            "created": "2026-08-01T10:00:00",
            "last_active": "2026-08-01T10:00:00",
            "activation_count": activation_count,
        },
    }


@pytest.fixture
def manager(monkeypatch):
    mgr = CountingBucketManager([
        _bucket("hit-one", "被反复查询的那条记忆。"),
        _bucket("hit-two", "另一条也会命中的记忆。"),
    ])
    monkeypatch.setattr(rt, "config", {"surfacing": {}})
    monkeypatch.setattr(rt, "bucket_mgr", mgr)
    monkeypatch.setattr(rt, "decay_engine", NoopDecay())
    monkeypatch.setattr(rt, "embedding_engine", DisabledEmbedding())
    monkeypatch.setattr(rt, "logger", MagicMock())
    monkeypatch.setattr(rt, "fire_webhook", None)
    monkeypatch.setattr(rt, "mark_op", None)
    monkeypatch.setattr(rt, "record_v3_tool_event", lambda *_a, **_k: None)
    monkeypatch.setattr(rt, "deletion_requests", None, raising=False)
    monkeypatch.setattr(rt, "them_service", None, raising=False)
    monkeypatch.setattr("tools.breath.search.random.random", lambda: 1.0)
    return mgr


# --------------------------------------------------------------
# 检索侧：一条都不 touch
# --------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_search_reinforces_nothing(manager):
    """命中一条不代表它要紧，只代表我在找它。"""
    out = await breath_dispatch(query="记忆")

    assert "被反复查询的那条记忆。" in out
    assert manager.touched == []


@pytest.mark.asyncio
async def test_repeated_queries_never_accumulate_weight(manager):
    """这是 bug 的形状：为 debug 反复查同一件事，权重不该跟着涨。"""
    for _ in range(20):
        await breath_dispatch(query="记忆")

    assert manager.touched == []


@pytest.mark.asyncio
async def test_exact_bucket_id_lookup_reinforces_nothing(manager):
    """按完整 ID 取桶尤其不能强化。

    这条路径存在的理由就是「改之前先读一眼磁盘上的原文」——越是要改它越会
    先读它，读一次涨一次权重是纯粹的自我实现。
    """
    out = await breath_dispatch(query="hit-one")

    assert "被反复查询的那条记忆。" in out
    assert manager.touched == []


@pytest.mark.asyncio
async def test_default_surfacing_still_reinforces_nothing(manager):
    """无参浮现本来就不 touch。一并钉住，免得解耦时把它改反了。"""
    await breath_dispatch()

    assert manager.touched == []


# --------------------------------------------------------------
# 强化侧：显式、按桶、仍然有效
# --------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_reinforce_touches_exactly_that_bucket(manager):
    """解耦不是把强化删了——读完之后针对那一条说「这条要紧」仍然有效。"""
    result = await trace_dispatch(bucket_id="hit-one", reinforce=True)

    assert "已强化" in result
    assert manager.touched == ["hit-one"]


@pytest.mark.asyncio
async def test_explicit_reinforce_reports_the_new_count(manager):
    """回显强化前后的次数：看不到变化就等于没确认。"""
    result = await trace_dispatch(bucket_id="hit-one", reinforce=True)

    assert "3" in result and "4" in result


@pytest.mark.asyncio
async def test_reinforce_is_per_bucket_not_per_candidate_set(manager):
    """一次只强化一条。检索命中里绝大多数只是路过。"""
    await breath_dispatch(query="记忆")
    await trace_dispatch(bucket_id="hit-one", reinforce=True)

    assert manager.touched == ["hit-one"]
    assert "hit-two" not in manager.touched


@pytest.mark.asyncio
async def test_reinforce_on_a_missing_bucket_fails_loudly(manager):
    with pytest.raises(ToolInputError, match="找不到记忆"):
        await trace_dispatch(bucket_id="no-such-bucket", reinforce=True)

    assert manager.touched == []


@pytest.mark.asyncio
async def test_reinforce_false_does_not_touch(manager):
    """reinforce=False 走的是普通空调用（noop，见 cf8fcd6），一条也不该 touch。

    默认值是 False，所以这条同时守着「每一次普通 trace 都不会顺手强化」。
    """
    await trace_dispatch(bucket_id="hit-one", reinforce=False)

    assert manager.touched == []


# --------------------------------------------------------------
# 互斥：另外半个意图不能被静默丢掉
# --------------------------------------------------------------


@pytest.mark.asyncio
async def test_reinforce_refuses_to_share_a_call_with_field_updates(manager):
    with pytest.raises(ToolInputError, match="必须单独调用"):
        await trace_dispatch(bucket_id="hit-one", reinforce=True, importance=9)

    assert manager.touched == []


@pytest.mark.asyncio
async def test_reinforce_refuses_to_share_a_call_with_relation_edit(manager):
    with pytest.raises(ToolInputError, match="不能与关系修正同时使用"):
        await trace_dispatch(bucket_id="hit-one", reinforce=True, unlink="hit-two")

    assert manager.touched == []


@pytest.mark.asyncio
async def test_reinforce_refuses_to_share_a_call_with_quotes_replace(manager):
    with pytest.raises(ToolInputError, match="不能与 quotes_replace 同时使用"):
        await trace_dispatch(bucket_id="hit-one", reinforce=True, quotes_replace=[])

    assert manager.touched == []
