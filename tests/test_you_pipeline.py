from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ombrebrain.you import EvidenceEdge, ReviewReceipt, YouService, YouStore, YouStoreError
class FakeBucketManager:
    def __init__(self):
        self.buckets = {}

    async def get(self, bucket_id):
        return self.buckets.get(bucket_id)


class FakeSourceStore:
    def __init__(self):
        self.sources = {}

    def read(self, source_id):
        return self.sources[source_id]


class FakeDehydrator:
    def __init__(self):
        self.observations = []
        self.review_result = "remains_plausible"
        self.hint = {"concepts": ["称呼", "Lin"], "relation": "日常交流优先使用"}

    async def extract_you_observations(self, _content):
        return list(self.observations)

    async def review_you_claim(self, _claim, _evidence):
        return self.review_result

    async def abstract_you_hint(self, _claim):
        return dict(self.hint)


def _service(tmp_path):
    manager = FakeBucketManager()
    sources = FakeSourceStore()
    dehydrator = FakeDehydrator()
    service = YouService(
        store=YouStore(tmp_path),
        bucket_mgr=manager,
        dehydrator=dehydrator,
        source_store=sources,
    )
    return service, manager, sources, dehydrator


def _bucket(content, **metadata):
    return {
        "id": metadata.pop("id", "memory-1"),
        "content": content,
        "metadata": {"type": "dynamic", **metadata},
    }


def _address_observation(value="lin"):
    return {
        "aspect": "preferred_address",
        "concept_key": "preferred_address",
        "concept_value": value,
        "content": f"对方偏好的日常称呼为 {value.title()}",
        "basis": "explicit_statement",
        "explicit": True,
        "long_term": True,
    }


@pytest.mark.asyncio
async def test_enabled_bucket_event_forms_core_claim_and_safe_hint(tmp_path):
    service, manager, _sources, dehydrator = _service(tmp_path)
    state = service.set_enabled(True, expected_revision=0)
    manager.buckets["memory-1"] = _bucket("以后请叫我 Lin，不要再用账户全名。")
    dehydrator.observations = [_address_observation()]

    assert service.observe_bucket_change(
        action="create",
        bucket_id="memory-1",
        content_hash="abc",
    ) is True
    assert await service.process_pending() == 1

    claims = service.store.list_claims(state.scope, callable_only=True)
    assert len(claims) == 1
    assert claims[0].lifecycle == "formal"
    assert claims[0].review_state == "clear"
    result = await service.recall()
    assert "称呼 / Lin" in result
    assert "以后请叫我" not in result
    assert claims[0].content not in result
    assert "You" not in result


@pytest.mark.asyncio
async def test_disabled_service_does_not_queue_read_or_create_storage(tmp_path):
    service, _manager, _sources, _dehydrator = _service(tmp_path)

    assert service.observe_bucket_change(
        action="create", bucket_id="memory-1", content_hash="abc"
    ) is False
    assert not (tmp_path / ".you").exists()
    with pytest.raises(YouStoreError, match="unknown tool"):
        await service.recall()


@pytest.mark.asyncio
async def test_sensitive_or_source_copy_observations_are_discarded(tmp_path):
    service, manager, _sources, dehydrator = _service(tmp_path)
    state = service.set_enabled(True)
    manager.buckets["memory-1"] = _bucket("她下班以后通常希望先安静一会儿，不要连续追问。")
    dehydrator.observations = [
        {
            "aspect": "communication_preference",
            "concept_key": "depression_support",
            "concept_value": "quiet",
            "content": "她有抑郁诊断，所以不要连续追问",
            "basis": "observed_pattern",
            "explicit": False,
            "long_term": True,
        },
        {
            "aspect": "communication_preference",
            "concept_key": "after_work_contact",
            "concept_value": "quiet",
            "content": "下班以后通常希望先安静一会儿",
            "basis": "observed_pattern",
            "explicit": False,
            "long_term": True,
        },
    ]
    service.observe_bucket_change(action="create", bucket_id="memory-1", content_hash="x")

    assert await service.process_pending() == 1
    assert service.store.list_claims(state.scope) == []


@pytest.mark.asyncio
async def test_update_removes_old_evidence_before_recomputing(tmp_path):
    service, manager, _sources, dehydrator = _service(tmp_path)
    state = service.set_enabled(True)
    manager.buckets["memory-1"] = _bucket("以后请叫我 Lin。")
    dehydrator.observations = [_address_observation()]
    service.observe_bucket_change(action="create", bucket_id="memory-1", content_hash="one")
    await service.process_pending()
    original = service.store.list_claims(state.scope)[0]

    manager.buckets["memory-1"] = _bucket("以后请叫我 Lynn。")
    dehydrator.observations = [_address_observation("lynn")]
    assert service.observe_bucket_change(
        action="update",
        bucket_id="memory-1",
        content_hash="two",
        changed_fields=("content",),
    ) is True
    await service.process_pending()

    claims = service.store.list_claims(state.scope)
    old = next(claim for claim in claims if claim.id == original.id)
    new = next(claim for claim in claims if claim.concept_value == "lynn")
    assert old.lifecycle == "expired"
    assert old.callable_at() is False
    assert new.lifecycle == "formal"
    assert new.callable_at() is True


def test_irrelevant_update_and_ordinary_archive_do_not_queue(tmp_path):
    service, _manager, _sources, _dehydrator = _service(tmp_path)
    service.set_enabled(True)

    assert service.observe_bucket_change(
        action="update",
        bucket_id="memory-1",
        content_hash="x",
        changed_fields=("last_active", "activation_count"),
    ) is False
    assert service.observe_bucket_change(
        action="archive", bucket_id="memory-1", content_hash="x"
    ) is False
    assert service.store.pending_outbox(now_epoch=10**12) == []


@pytest.mark.asyncio
async def test_contextual_claim_requires_two_groups_and_three_current_review_dates(tmp_path):
    service, manager, _sources, _dehydrator = _service(tmp_path)
    state = service.set_enabled(True)
    scope = state.scope
    manager.buckets["memory-1"] = _bucket("第一次表达了沟通偏好。", id="memory-1")
    manager.buckets["memory-2"] = _bucket("另一天再次表达相同偏好。", id="memory-2")
    observation = {
        "aspect": "communication_preference",
        "concept_key": "tired_conversation",
        "concept_value": "space_first",
        "content": "疲惫时更适合先留出交流空间",
        "basis": "observed_pattern",
        "explicit": False,
        "long_term": True,
    }
    first = EvidenceEdge(
        "memory-1", "eg_" + "1" * 64, "supports", "observed_pattern", "sha256:" + "1" * 64
    )
    claim = await service._upsert_observation(scope, observation, first)
    assert claim.lifecycle == "candidate"
    second = EvidenceEdge(
        "memory-2", "eg_" + "2" * 64, "supports", "observed_pattern", "sha256:" + "2" * 64
    )
    claim = await service._upsert_observation(scope, observation, second)
    assert claim.independent_support_count == 2
    assert claim.lifecycle == "candidate"

    today = datetime.now(timezone.utc)
    receipts = tuple(
        ReviewReceipt(
            (today - timedelta(days=offset)).isoformat(),
            scope.observer_role_id,
            claim.evidence_revision,
            "remains_plausible",
        )
        for offset in (0, 1, 2)
    )
    claim = service.store.put_claim(
        replace(claim, review_receipts=receipts), expected_revision=claim.revision
    )
    promoted = await service._promote_if_ready(claim)

    assert promoted.lifecycle == "formal"
    assert promoted.review_state == "clear"
    assert promoted.callable_at() is True


@pytest.mark.asyncio
async def test_delete_event_expires_dependent_claim(tmp_path):
    service, manager, _sources, dehydrator = _service(tmp_path)
    state = service.set_enabled(True)
    manager.buckets["memory-1"] = _bucket("以后请叫我 Lin。")
    dehydrator.observations = [_address_observation()]
    service.observe_bucket_change(action="create", bucket_id="memory-1", content_hash="one")
    await service.process_pending()

    manager.buckets.pop("memory-1")
    service.observe_bucket_change(action="delete", bucket_id="memory-1", content_hash="two")
    await service.process_pending()

    claim = service.store.list_claims(state.scope)[0]
    assert claim.lifecycle == "expired"
    assert claim.evidence == ()
    assert service.store.list_claims(state.scope, callable_only=True) == []
