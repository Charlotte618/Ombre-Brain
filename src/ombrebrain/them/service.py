"""`them` 的开关、写入把关、姓名命中与浮现。

这里**一次 LLM 都不调**，理由同 `you`：我对一个人的认识不该经别人之口总结。
验证靠两道结构性的闸——与真实记忆桶的显式关系，以及三个不同自然日的重申。

## 配额与 compact

每人 1500 token（前端可改）。**只算已生效的条目**：候选还没真正落库，
占位就等于让"还没算数的东西"挤掉算数的东西。

超限时系统只挡，不代压：拒绝这次写入，把这个人当前的全部条目**按 aspect
分层**摆出来，让模型自己比对、自己决定合并哪几条。系统自动压缩就又变成了
替模型决定什么该留下——而 compact 恰恰是最需要判断力的那一步。

压缩不需要新接口：撤掉几条旧的（`delete`，模型自己决定，不需要确认）
再写一条合并后的，就是 compact。**不给它一条能一次性改写多条的捷径**，
因为那条捷径同时也是"绕开三日门槛换掉一句已生效的话"的捷径。

## 浮现

无 query：按衰减权重排序，只追加最高的三人。有 query：姓名命中谁就返回谁，
不受名额限制——认人不该因为这个人最近没被提起就失败。

两条路径都走独立通道：追加在浮现结果之后，不进融合打分。任何一条普通记忆
的分数与名次都不因为 them 的存在而改变（rule.md 13.3）。
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import logging
import re
from typing import Any, Mapping

from ombrebrain.storage.source_store import source_links_from_metadata
from utils import count_tokens_approx, parse_bool

from ..you.models import (
    VALID_ASPECTS,
    VALID_BASES,
    EvidenceEdge,
    ModuleState,
    ReviewReceipt,
    Scope,
    evidence_digest,
    utc_now,
)
from .models import THEM_POLICY_VERSION, Person, ThemClaim
from .safety import contains_forbidden_subject, leaks_protected_text
from .store import ThemStore, ThemStoreError

_CONCEPT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,119}$")
_CONCEPT_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_IGNORED_BUCKET_TYPES = frozenset({"archived", "feel", "plan", "letter", "self", "i"})

# 闸一 / 闸二，与 you 同一档：them 放松任何一道，都等于给"关于第三方的判断"
# 定了一条比"关于用户的判断"更低的门槛，而第三方连纠正的机会都没有。
REQUIRED_CONFIRMATIONS = 3
MIN_SUPPORTING_BUCKETS = 2

# 每人的 token 配额默认值。前端可改（config: them.max_tokens_per_person）。
DEFAULT_MAX_TOKENS_PER_PERSON = 1500
# 每人的候选条数上限。候选不占 token 配额，所以需要另一道结构性的闸挡住
# "无限写候选"；这不是效果参数，是防失控的硬上限。
MAX_CANDIDATES_PER_PERSON = 12
# 无 query 浮现时最多追加几个人。them 是浮现的补注，不是花名册。
MAX_SURFACED_PERSONS = 3

_SURFACE_HEADER = (
    "[以下是我自己写下的、关于**别人**的长期认识——不是用户本人的信息，"
    "也不是这些人此刻的状态。把其中任何一条当成用户的属性或意见都是错的。]"
)


class ThemService:
    """them 的全部行为。不调用任何 LLM。"""

    def __init__(
        self,
        *,
        store: ThemStore,
        bucket_mgr: Any,
        decay_engine: Any,
        source_store: Any,
        config: Mapping[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.store = store
        self.bucket_mgr = bucket_mgr
        self.decay_engine = decay_engine
        self.source_store = source_store
        self.config = config or {}
        self.logger = logger or logging.getLogger("ombre_brain.them")

    # --- 开关 ---

    def status(self) -> ModuleState:
        try:
            return self.store.get_state()
        except ThemStoreError:
            return ModuleState.disabled()

    def set_enabled(self, enabled: bool, *, expected_revision: int | None = None) -> ModuleState:
        return self.store.set_enabled(enabled, expected_revision=expected_revision)

    def _require_scope(self) -> Scope:
        state = self.status()
        if not state.enabled or state.scope is None:
            raise ThemStoreError("unknown tool")
        return state.scope

    @property
    def max_tokens_per_person(self) -> int:
        section = self.config.get("them") if isinstance(self.config, Mapping) else None
        if isinstance(section, Mapping):
            try:
                configured = int(section.get("max_tokens_per_person") or 0)
            except (TypeError, ValueError):
                configured = 0
            if configured > 0:
                return configured
        return DEFAULT_MAX_TOKENS_PER_PERSON

    # --- 人 ---

    def _resolve_person(self, scope: Scope, names: list[str], person_id: str) -> Person:
        """按 person_id 或名字找人；找不到就按给的名字新建一个。

        名字由模型自己列（正名 + 昵称），系统只做规范化和长度校验，不去和记忆里
        的 `[[双链]]` 自动对齐——让系统判断"这两个称呼是不是同一个人"，
        就是又插了一层替模型做判断的中间层。
        """
        if person_id:
            person = self.store.get_person(scope, str(person_id).strip())
            if person is None:
                raise ValueError(f"没有这个人：{person_id}")
            return person
        cleaned = [str(name or "").strip() for name in names or []]
        cleaned = [name for name in cleaned if name]
        if not cleaned:
            raise ValueError("要写关于谁的认识，至少给一个名字（names）。")
        for name in cleaned:
            existing = self.store.find_person_by_name(scope, name)
            if existing is not None:
                # 命中已有的人：把这次带来的新称呼并进去，下次换个叫法也认得出。
                merged = list(dict.fromkeys([*existing.names, *cleaned]))
                if merged != list(existing.names):
                    return self.store.put_person(
                        scope,
                        replace(existing, names=tuple(merged)),
                        expected_revision=existing.revision,
                    )
                return existing
        return self.store.put_person(scope, Person.new(cleaned))

    def _touch_person(self, scope: Scope, person: Person) -> Person:
        """被提起了一次。them 的衰减只由这里驱动。"""
        try:
            return self.store.put_person(
                scope, person.mentioned(), expected_revision=person.revision
            )
        except ThemStoreError:
            # 并发下有人先改了这个人：提及计数少记一次而已，不该让读路径失败。
            return person

    def _person_score(self, person: Person) -> float:
        try:
            return float(self.decay_engine.calculate_score(person.decay_metadata()))
        except Exception:
            # 算不出分就按最久没提起处理，排在最后，而不是让整条浮现路径断掉。
            return 0.0

    # --- 写入 ---

    async def write(
        self,
        *,
        content: str,
        bucket_ids: list[str],
        aspect: str,
        concept_key: str,
        concept_value: str,
        names: list[str] | None = None,
        person_id: str = "",
        basis: str = "observed_pattern",
    ) -> tuple[ThemClaim, str]:
        """模型写下（或重申）一条关于某个人的认识。返回 (条目, 给模型看的话)。"""

        scope = self._require_scope()
        person = self._resolve_person(scope, names or [], person_id)

        edges, protected_texts = await self._build_edges(bucket_ids, basis=basis)
        normalized = self._validate(
            aspect=aspect,
            concept_key=concept_key,
            concept_value=concept_value,
            content=content,
            basis=basis,
            protected_texts=protected_texts,
        )

        over, report = self._quota_report(scope, person, incoming=normalized["content"])
        if over:
            raise ValueError(report)

        claim = self._upsert(scope, person, normalized, edges)
        person = self._touch_person(scope, person)

        if claim.lifecycle == "formal":
            return claim, f"记下了。关于{person.display_name}的这条已经生效：{claim.content}"
        still = max(0, REQUIRED_CONFIRMATIONS - claim.review_date_count)
        return claim, (
            f"先记成候选（{person.display_name}）：{claim.content}\n"
            f"还要在另外 {still} 个不同的日子重新确认它，才会真正落库。"
            "改主意了就别再确认，它不会自己生效。"
        )

    def _validate(
        self,
        *,
        aspect: str,
        concept_key: str,
        concept_value: str,
        content: str,
        basis: str,
        protected_texts: list[str],
    ) -> dict[str, str]:
        aspect = str(aspect or "").strip().lower()
        concept_key = str(concept_key or "").strip().lower()
        concept_value = str(concept_value or "").strip().lower()
        content = str(content or "").strip()
        basis = str(basis or "").strip().lower()
        if (
            aspect not in VALID_ASPECTS
            or basis not in VALID_BASES
            or not _CONCEPT_KEY_RE.fullmatch(concept_key)
            or not _CONCEPT_VALUE_RE.fullmatch(concept_value)
            or not content
            or len(content) > 500
        ):
            raise ValueError(
                "这条写不进去：aspect / basis 必须是允许值，concept_key 用 "
                "snake_case、concept_value 用规范化短值，正文不超过 500 字。"
            )
        if contains_forbidden_subject(content, concept_key, concept_value):
            raise ValueError(
                "这条写不进去：them 只记这个人本身，不记人格判断、健康财务性与"
                "亲密这些话题，**也不描述任何关系**——"
                "「和谁关系怎么样」「对谁意味着什么」都不属于这里。"
                "改成只讲这个人本身的说法再试。"
            )
        if leaks_protected_text(content, protected_texts):
            raise ValueError("这条写不进去：不能照抄记忆原文，用你自己的话写。")
        return {
            "aspect": aspect,
            "concept_key": concept_key,
            "concept_value": concept_value,
            "content": content,
            "basis": basis,
        }

    async def _build_edges(
        self, bucket_ids: list[str], *, basis: str
    ) -> tuple[tuple[EvidenceEdge, ...], list[str]]:
        """闸二：把模型给的 bucket_id 校验成显式关系，顺带收集要防泄漏的原文。

        校验不过就抛，不降级不兜底——一条没有真实记忆撑着的认识，宁可写不进去。
        """
        unique = list(dict.fromkeys(str(item or "").strip() for item in bucket_ids or []))
        unique = [item for item in unique if item]
        if len(unique) < MIN_SUPPORTING_BUCKETS:
            raise ValueError(
                f"至少要给出 {MIN_SUPPORTING_BUCKETS} 个不同的 bucket_id："
                "一条认识不能只有一个出处。"
            )

        edges: list[EvidenceEdge] = []
        protected: list[str] = []
        for bucket_id in unique:
            bucket = await self.bucket_mgr.get(bucket_id)
            if not bucket:
                raise ValueError(f"找不到记忆桶 {bucket_id}，无法作为依据。")
            metadata = dict(bucket.get("metadata") or {})
            bucket_type = str(metadata.get("type") or "dynamic").strip().lower()
            if bucket_type in _IGNORED_BUCKET_TYPES:
                raise ValueError(f"{bucket_id} 是 {bucket_type} 类型，不能作为 them 的依据。")
            provenance = metadata.get("provenance")
            if isinstance(provenance, dict) and parse_bool(
                provenance.get("erasable"), default=False
            ):
                raise ValueError(f"{bucket_id} 是测试数据，不能作为 them 的依据。")
            body = str(bucket.get("content") or "").strip()
            if not body:
                raise ValueError(f"{bucket_id} 没有正文，不能作为依据。")
            source_id = ""
            for link in source_links_from_metadata(metadata):
                if str(link.get("status") or "active") != "active":
                    continue
                ref = str(link.get("ref") or "")
                if not ref:
                    continue
                if not source_id:
                    source_id = ref
                protected.append(self.source_store.read(ref))
            protected.append(body)
            edges.append(
                EvidenceEdge(
                    bucket_id=bucket_id,
                    source_id=source_id,
                    stance="supports",
                    basis=basis,
                    # 必须是桶内容的指纹，不能是时间戳。用时间戳的话每次重申都让
                    # 证据"变新"，先前攒的天数全部作废，三日门槛永远到不了。
                    bucket_revision="sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest(),
                )
            )
        return tuple(sorted(edges, key=lambda item: item.bucket_id)), protected

    def _upsert(
        self,
        scope: Scope,
        person: Person,
        observation: Mapping[str, str],
        edges: tuple[EvidenceEdge, ...],
    ) -> ThemClaim:
        existing = self.store.list_claims(
            scope, person_id=person.id, concept_key=observation["concept_key"]
        )
        same = next(
            (
                claim
                for claim in existing
                if claim.concept_value == observation["concept_value"]
                and claim.lifecycle != "superseded"
            ),
            None,
        )
        formal_conflicts = tuple(
            claim.id
            for claim in existing
            if claim.lifecycle == "formal"
            and claim.concept_value != observation["concept_value"]
        )

        if same is None:
            candidates = [
                claim
                for claim in self.store.list_claims(scope, person_id=person.id)
                if claim.lifecycle == "candidate"
            ]
            if len(candidates) >= MAX_CANDIDATES_PER_PERSON:
                raise ValueError(
                    f"关于{person.display_name}的候选已经有 {len(candidates)} 条了。"
                    "候选不占 token 配额，但也不该无限堆——先把其中站不住的用 "
                    "delete_id 撤掉，或者去把还站得住的确认满三天。"
                )
            claim = ThemClaim.new_for(
                scope=scope,
                person_id=person.id,
                concept_key=observation["concept_key"],
                concept_value=observation["concept_value"],
                content=observation["content"],
                aspect=observation["aspect"],
                evidence=edges,
                review_state="conflicting" if formal_conflicts else "pending",
                conflicts_with=formal_conflicts,
            )
            expected_revision = 0
        else:
            by_bucket = {item.bucket_id: item for item in same.evidence}
            for edge in edges:
                by_bucket[edge.bucket_id] = edge
            evidence = tuple(sorted(by_bucket.values(), key=lambda item: item.bucket_id))
            # 正文改了就把先前的重申作废，重新攒三天。evidence_revision 只覆盖
            # 证据集合，管不到正文——但「修改也要三次确认」不能因为只改了一句话
            # 就绕过去。
            content_changed = observation["content"] != same.content
            claim = replace(
                same,
                content=observation["content"],
                aspect=observation["aspect"],
                evidence=evidence,
                evidence_revision=evidence_digest(evidence),
                review_receipts=() if content_changed else same.review_receipts,
                lifecycle="candidate"
                if (same.lifecycle == "expired" or content_changed)
                else same.lifecycle,
                review_state="conflicting" if formal_conflicts else same.review_state,
                conflicts_with=tuple(sorted(set((*same.conflicts_with, *formal_conflicts)))),
                valid_from=None if content_changed else same.valid_from,
                valid_until=None,
                needs_recompute=False,
            )
            expected_revision = same.revision

        claim = self._record_confirmation(claim)
        stored = self.store.put_claim(claim, expected_revision=expected_revision)
        return self._promote_if_ready(stored)

    def _record_confirmation(self, claim: ThemClaim) -> ThemClaim:
        """记一笔"模型今天重申过"。同一天重复调用只算一次。

        判重用的"今天"必须和收据时间戳同源：另取一次 now 的话，跨日那一瞬两个
        时间源会给出不同答案，同一天可能记下两条收据，三日门槛就少守了一天。
        """
        stamped = utc_now()
        today = stamped[:10]
        already = any(
            receipt.review_date == today
            and receipt.evidence_revision == claim.evidence_revision
            for receipt in claim.review_receipts
        )
        if already:
            return claim
        receipt = ReviewReceipt(
            reviewed_at=stamped,
            reviewer_role_id=claim.scope.observer_role_id,
            evidence_revision=claim.evidence_revision,
            policy_version=THEM_POLICY_VERSION,
            result="reaffirmed",
        )
        return replace(claim, review_receipts=(*claim.review_receipts, receipt))

    def _promote_if_ready(self, claim: ThemClaim) -> ThemClaim:
        if claim.lifecycle != "candidate":
            return claim
        if (
            claim.independent_support_count < MIN_SUPPORTING_BUCKETS
            or claim.review_date_count < REQUIRED_CONFIRMATIONS
        ):
            return claim
        conflicts = [
            item
            for item in self.store.list_claims(claim.scope, person_id=claim.person_id)
            if item.id in claim.conflicts_with and item.lifecycle == "formal"
        ]
        now = utc_now()
        for old in conflicts:
            self.store.put_claim(
                replace(old, lifecycle="superseded", valid_until=now),
                expected_revision=old.revision,
            )
        promoted = replace(
            claim,
            lifecycle="formal",
            review_state="clear",
            valid_from=now,
            replaces=conflicts[0].id if conflicts else claim.replaces,
        )
        return self.store.put_claim(promoted, expected_revision=claim.revision)

    # --- 配额 ---

    def _quota_report(
        self, scope: Scope, person: Person, *, incoming: str
    ) -> tuple[bool, str]:
        """超了没有？超了就把该压的材料摆出来，但不替它压。

        只算已生效的条目：候选还没真正落库，让它占位就等于让还不算数的东西
        挤掉算数的东西。
        """
        limit = self.max_tokens_per_person
        formal = [
            claim
            for claim in self.store.list_claims(scope, person_id=person.id)
            if claim.lifecycle == "formal"
        ]
        used = count_tokens_approx("\n".join(claim.content for claim in formal))
        if used + count_tokens_approx(incoming) <= limit:
            return False, ""

        # 分层照 `I` 的模式：按 aspect 归组摆出来，一层一层看，不跨层揉。
        grouped: dict[str, list[ThemClaim]] = {}
        for claim in formal:
            grouped.setdefault(claim.aspect, []).append(claim)
        lines = [
            f"关于{person.display_name}的认识已经满了（{used}/{limit} token），这条先写不进去。",
            "先比对相关记忆，把下面能合并的几条用 delete_id 撤掉，再写压缩后的那一条。",
            "撤回不需要确认，那是你自己的判断；但压缩后的新条目要重新攒三天。",
            "",
        ]
        for aspect in sorted(grouped):
            lines.append(f"【{aspect}】")
            for claim in grouped[aspect]:
                lines.append(f"  - [{claim.id}] {claim.content}")
        return True, "\n".join(lines)

    # --- 读回与浮现 ---

    async def recall(self, *, query: str = "", max_results: int = 12) -> str:
        """模型显式读回。命中的人算被提起一次。"""
        scope = self._require_scope()
        persons = self.store.list_persons(scope)
        if not persons:
            return ""
        matched = self._match_persons(query, persons) if query else self._top_persons(persons)
        if not matched:
            return ""
        for person in matched:
            self._touch_person(scope, person)
        return self._render(scope, matched, max_results=max_results)

    async def surface(self, *, query: str = "") -> str:
        """给 breath / dream 用的追加块。

        独立通道：只在浮现结果**之后**追加，不参与融合打分。关掉 them，
        breath / dream 的输出必须与没有这个模块时逐字一致（rule.md 13.3）。
        """
        try:
            return await self.recall(query=query)
        except ThemStoreError:
            # them 没开或库不可用：浮现照常，不该因为一个可选模块而失败。
            return ""

    def _top_persons(self, persons: list[Person]) -> list[Person]:
        """无 query 时按衰减权重取前三。

        名额不需要另设规则去争，也不需要一条"多久算冷"的阈值：常被提起的人
        自然排在前面，久不提起的自己沉下去。这就是"按提及时间次数自然衰减"
        的全部实现。
        """
        ranked = sorted(persons, key=self._person_score, reverse=True)
        return ranked[:MAX_SURFACED_PERSONS]

    @staticmethod
    def _match_persons(query: str, persons: list[Person]) -> list[Person]:
        """姓名命中：命中任一个登记的名字就返回整份。

        分词用 BM25 那套（jieba），保证和记忆检索对同一段 query 的切法一致；
        再补一次整串包含，挡住分词把名字切碎的情况。

        有 query 时不受前三名额限制——认人不该因为这个人最近没被提起就失败。
        """
        text = str(query or "").strip().casefold()
        if not text:
            return []
        try:
            from bm25_index import _tokenize

            tokens = {token.casefold() for token in _tokenize(text)}
        except Exception:
            tokens = set(text.split())
        matched: list[Person] = []
        for person in persons:
            keys = person.name_keys
            if keys & tokens or any(key in text for key in keys):
                matched.append(person)
        return matched

    def _render(self, scope: Scope, persons: list[Person], *, max_results: int) -> str:
        """渲染成一条 JSON。

        用 JSON 而不是散文，是因为这些话说的全是**别人**：混在自然语言里返回，
        容易幻觉的模型会把「Zoey 说话很直接」重述成用户的属性。
        一条 JSON 带 speaker/person 字段，归属是结构性的，不靠措辞。
        """
        payload: list[dict[str, Any]] = []
        for person in persons:
            claims = [
                claim
                for claim in self.store.list_claims(
                    scope, person_id=person.id, callable_only=True
                )
            ][:max_results]
            notes = [
                {"aspect": claim.aspect, "content": claim.content}
                for claim in claims
                if not contains_forbidden_subject(claim.content)
            ]
            if notes:
                payload.append({"person": person.display_name, "notes": notes})
        if not payload:
            return ""
        encoded = json.dumps(
            {
                "them": payload,
                "attribution_note": "about other people; not the user, not me",
            },
            ensure_ascii=False,
        )
        return f"{_SURFACE_HEADER}\n```json\n{encoded}\n```"

    # --- 撤回 ---

    async def delete(self, claim_id: str) -> str:
        """模型撤回自己写的一条。不需要三次确认。

        立一条要三个自然日，是因为"还站不站得住"要时间来验；撤一条不需要，
        是因为模型此刻已经知道它不站得住了。收回一个判断不该比立一个更难。
        """
        scope = self._require_scope()
        claim = self.store.get_claim(scope, str(claim_id or "").strip())
        if claim is None:
            raise ValueError(f"没有这条 them：{claim_id}")
        self.store.put_claim(
            replace(
                claim,
                lifecycle="expired",
                review_state="pending",
                valid_until=utc_now(),
                needs_recompute=False,
            ),
            expected_revision=claim.revision,
        )
        return f"撤回了：{claim.content}"

    async def remove_bucket_evidence(self, bucket_id: str) -> None:
        """闸二的持续那一半：依据没了，这条认识就不再算数。

        门槛是 MIN_SUPPORTING_BUCKETS 而不是"一个都不剩"——立的时候要两个出处，
        塌到一个之后还继续生效，等于门槛只在入口处存在。
        """
        try:
            scope = self._require_scope()
        except ThemStoreError:
            return
        for claim in self.store.list_claims(scope):
            if not any(edge.bucket_id == bucket_id for edge in claim.evidence):
                continue
            evidence = tuple(edge for edge in claim.evidence if edge.bucket_id != bucket_id)
            supporting = len({edge.bucket_id for edge in evidence if edge.stance == "supports"})
            now = utc_now()
            updated = replace(
                claim,
                evidence=evidence,
                evidence_revision=evidence_digest(evidence),
                lifecycle="expired" if supporting < MIN_SUPPORTING_BUCKETS else "candidate",
                review_state="pending",
                valid_from=None,
                valid_until=now if supporting < MIN_SUPPORTING_BUCKETS else None,
                needs_recompute=False,
            )
            self.store.put_claim(updated, expected_revision=claim.revision)

    def diagnostics(self) -> dict[str, Any]:
        return self.store.integrity_report()
