from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping
from uuid import uuid4


SCHEMA_VERSION = 1
POLICY_VERSION = "you-policy-v1"
VALID_ASPECTS = frozenset(
    {
        "preferred_address",
        "explicit_boundary",
        "stable_fact",
        "communication_preference",
        "interaction_habit",
    }
)
VALID_LIFECYCLES = frozenset({"candidate", "formal", "superseded", "expired"})
VALID_REVIEW_STATES = frozenset({"pending", "clear", "conflicting"})
VALID_RECALL_POLICIES = frozenset({"core", "contextual"})
VALID_STANCES = frozenset({"supports", "contradicts"})
VALID_BASES = frozenset(
    {"explicit_statement", "observed_pattern", "shared_event", "user_confirmation"}
)
_ID_RE = re.compile(r"^[a-z]+_[0-9a-f]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _require_id(value: object, prefix: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized.startswith(f"{prefix}_") or not _ID_RE.fullmatch(normalized):
        raise ValueError(f"invalid {prefix} id")
    return normalized


def _require_text(value: object, field_name: str, *, limit: int = 1000) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > limit or "\x00" in normalized:
        raise ValueError(f"invalid {field_name}")
    return normalized


@dataclass(frozen=True)
class Scope:
    owner_instance_id: str
    observer_role_id: str
    subject_user_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "owner_instance_id", _require_id(self.owner_instance_id, "owner")
        )
        object.__setattr__(
            self, "observer_role_id", _require_id(self.observer_role_id, "role")
        )
        object.__setattr__(
            self, "subject_user_id", _require_id(self.subject_user_id, "user")
        )

    @classmethod
    def new(cls) -> "Scope":
        return cls(_new_id("owner"), _new_id("role"), _new_id("user"))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Scope":
        return cls(
            owner_instance_id=value.get("owner_instance_id", ""),
            observer_role_id=value.get("observer_role_id", ""),
            subject_user_id=value.get("subject_user_id", ""),
        )

    @property
    def key(self) -> str:
        # 三个 id 直接拼。这是身份不是内容，没有「变了要检测」的需求，原来
        # sha256 一遍只是把它变得不可读：出问题时从库里捞出一串 64 位十六进制，
        # 看不出属于哪个 owner/role/user，还得反查。id 本身就在
        # module_state.scope_json 里明文存着，拼接不多暴露任何东西。
        # _ID_RE 限定了 `前缀_32位hex`，字符集里没有分隔符，拼不出歧义。
        return "|".join(
            (self.owner_instance_id, self.observer_role_id, self.subject_user_id)
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "owner_instance_id": self.owner_instance_id,
            "observer_role_id": self.observer_role_id,
            "subject_user_id": self.subject_user_id,
        }


@dataclass(frozen=True)
class ModuleState:
    enabled: bool = False
    scope: Scope | None = None
    state_revision: int = 0
    changed_at: str = ""
    changed_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        try:
            revision = int(self.state_revision)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid state_revision") from exc
        if revision < 0:
            raise ValueError("invalid state_revision")
        if self.enabled and self.scope is None:
            raise ValueError("enabled state requires a complete scope")
        object.__setattr__(self, "state_revision", revision)
        object.__setattr__(self, "changed_at", str(self.changed_at or ""))
        object.__setattr__(self, "changed_by", str(self.changed_by or ""))

    @classmethod
    def disabled(cls) -> "ModuleState":
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "scope": self.scope.to_dict() if self.scope else None,
            "state_revision": self.state_revision,
            "changed_at": self.changed_at,
            "changed_by": self.changed_by,
        }


@dataclass(frozen=True)
class EvidenceEdge:
    bucket_id: str
    evidence_group_id: str
    stance: str
    basis: str
    bucket_revision: str
    source_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "bucket_id", _require_text(self.bucket_id, "bucket_id", limit=200))
        object.__setattr__(
            self,
            "evidence_group_id",
            _require_text(self.evidence_group_id, "evidence_group_id", limit=200),
        )
        stance = str(self.stance or "").strip().lower()
        basis = str(self.basis or "").strip().lower()
        if stance not in VALID_STANCES:
            raise ValueError("invalid evidence stance")
        if basis not in VALID_BASES:
            raise ValueError("invalid evidence basis")
        object.__setattr__(self, "stance", stance)
        object.__setattr__(self, "basis", basis)
        object.__setattr__(
            self, "bucket_revision", _require_text(self.bucket_revision, "bucket_revision", limit=100)
        )
        source_id = str(self.source_id or "").strip()
        if len(source_id) > 200 or "\x00" in source_id:
            raise ValueError("invalid source_id")
        object.__setattr__(self, "source_id", source_id)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceEdge":
        return cls(**{key: value.get(key, "") for key in (
            "bucket_id", "evidence_group_id", "stance", "basis", "bucket_revision", "source_id"
        )})

    def to_dict(self) -> dict[str, str]:
        return {
            "bucket_id": self.bucket_id,
            "source_id": self.source_id,
            "evidence_group_id": self.evidence_group_id,
            "stance": self.stance,
            "basis": self.basis,
            "bucket_revision": self.bucket_revision,
        }


@dataclass(frozen=True)
class ReviewReceipt:
    reviewed_at: str
    reviewer_role_id: str
    evidence_revision: str
    result: str
    policy_version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewed_at", _require_text(self.reviewed_at, "reviewed_at", limit=80))
        object.__setattr__(
            self, "reviewer_role_id", _require_id(self.reviewer_role_id, "role")
        )
        object.__setattr__(
            self,
            "evidence_revision",
            _require_text(self.evidence_revision, "evidence_revision", limit=100),
        )
        result = str(self.result or "").strip().lower()
        if result not in {"remains_plausible", "contradicted", "insufficient"}:
            raise ValueError("invalid review result")
        object.__setattr__(self, "result", result)
        object.__setattr__(
            self, "policy_version", _require_text(self.policy_version, "policy_version", limit=80)
        )

    @property
    def review_date(self) -> str:
        return self.reviewed_at[:10]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewReceipt":
        return cls(
            reviewed_at=value.get("reviewed_at", ""),
            reviewer_role_id=value.get("reviewer_role_id", ""),
            evidence_revision=value.get("evidence_revision", ""),
            result=value.get("result", ""),
            policy_version=value.get("policy_version") or POLICY_VERSION,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "reviewed_at": self.reviewed_at,
            "reviewer_role_id": self.reviewer_role_id,
            "evidence_revision": self.evidence_revision,
            "policy_version": self.policy_version,
            "result": self.result,
        }


@dataclass(frozen=True)
class YouClaim:
    id: str
    scope: Scope
    concept_key: str
    concept_value: str
    content: str
    aspect: str
    lifecycle: str = "candidate"
    review_state: str = "pending"
    recall_policy: str = "contextual"
    sensitivity: str = "normal"
    evidence: tuple[EvidenceEdge, ...] = field(default_factory=tuple)
    review_receipts: tuple[ReviewReceipt, ...] = field(default_factory=tuple)
    valid_from: str | None = None
    valid_until: str | None = None
    replaces: str | None = None
    conflicts_with: tuple[str, ...] = field(default_factory=tuple)
    evidence_revision: str = ""
    projection_revision: int = 0
    needs_recompute: bool = False
    revision: int = 1
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_id(self.id, "you"))
        object.__setattr__(
            self, "concept_key", _require_text(self.concept_key, "concept_key", limit=120).lower()
        )
        object.__setattr__(
            self, "concept_value", _require_text(self.concept_value, "concept_value", limit=240).lower()
        )
        object.__setattr__(self, "content", _require_text(self.content, "content", limit=500))
        aspect = str(self.aspect or "").strip().lower()
        lifecycle = str(self.lifecycle or "").strip().lower()
        review_state = str(self.review_state or "").strip().lower()
        recall_policy = str(self.recall_policy or "").strip().lower()
        if aspect not in VALID_ASPECTS:
            raise ValueError("invalid claim aspect")
        if lifecycle not in VALID_LIFECYCLES:
            raise ValueError("invalid claim lifecycle")
        if review_state not in VALID_REVIEW_STATES:
            raise ValueError("invalid claim review_state")
        if recall_policy not in VALID_RECALL_POLICIES:
            raise ValueError("invalid claim recall_policy")
        if str(self.sensitivity or "normal").strip().lower() != "normal":
            raise ValueError("sensitive claims are forbidden")
        object.__setattr__(self, "aspect", aspect)
        object.__setattr__(self, "lifecycle", lifecycle)
        object.__setattr__(self, "review_state", review_state)
        object.__setattr__(self, "recall_policy", recall_policy)
        object.__setattr__(self, "sensitivity", "normal")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "review_receipts", tuple(self.review_receipts))
        object.__setattr__(self, "conflicts_with", tuple(str(v) for v in self.conflicts_with))
        for field_name in ("projection_revision", "revision"):
            try:
                parsed = int(getattr(self, field_name))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"invalid {field_name}") from exc
            if parsed < (1 if field_name == "revision" else 0):
                raise ValueError(f"invalid {field_name}")
            object.__setattr__(self, field_name, parsed)

    @classmethod
    def new(
        cls,
        *,
        scope: Scope,
        concept_key: str,
        concept_value: str,
        content: str,
        aspect: str,
        recall_policy: str,
        evidence: tuple[EvidenceEdge, ...],
        review_state: str = "pending",
        conflicts_with: tuple[str, ...] = (),
    ) -> "YouClaim":
        return cls(
            id=_new_id("you"),
            scope=scope,
            concept_key=concept_key,
            concept_value=concept_value,
            content=content,
            aspect=aspect,
            recall_policy=recall_policy,
            evidence=evidence,
            review_state=review_state,
            conflicts_with=conflicts_with,
            evidence_revision=evidence_digest(evidence),
        )

    @property
    def independent_support_count(self) -> int:
        return len({edge.evidence_group_id for edge in self.evidence if edge.stance == "supports"})

    @property
    def review_date_count(self) -> int:
        return len(
            {
                receipt.review_date
                for receipt in self.review_receipts
                if receipt.result == "remains_plausible"
                and receipt.evidence_revision == self.evidence_revision
            }
        )

    def callable_at(self, now: str | None = None) -> bool:
        current = now or utc_now()
        return bool(
            self.lifecycle == "formal"
            and self.review_state == "clear"
            and not self.needs_recompute
            and (not self.valid_from or self.valid_from <= current)
            and (not self.valid_until or current <= self.valid_until)
            and self.evidence
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "YouClaim":
        scope_raw = value.get("scope")
        if not isinstance(scope_raw, Mapping):
            raise ValueError("claim scope is missing")
        evidence_raw = value.get("evidence") or []
        receipts_raw = value.get("review_receipts") or []
        if not isinstance(evidence_raw, list) or not isinstance(receipts_raw, list):
            raise ValueError("invalid claim evidence or receipts")
        return cls(
            id=value.get("id", ""),
            scope=Scope.from_dict(scope_raw),
            concept_key=value.get("concept_key", ""),
            concept_value=value.get("concept_value", ""),
            content=value.get("content", ""),
            aspect=value.get("aspect", ""),
            lifecycle=value.get("lifecycle", "candidate"),
            review_state=value.get("review_state", "pending"),
            recall_policy=value.get("recall_policy", "contextual"),
            sensitivity=value.get("sensitivity", "normal"),
            evidence=tuple(EvidenceEdge.from_dict(item) for item in evidence_raw if isinstance(item, Mapping)),
            review_receipts=tuple(ReviewReceipt.from_dict(item) for item in receipts_raw if isinstance(item, Mapping)),
            valid_from=value.get("valid_from"),
            valid_until=value.get("valid_until"),
            replaces=value.get("replaces"),
            conflicts_with=tuple(value.get("conflicts_with") or ()),
            evidence_revision=value.get("evidence_revision", ""),
            projection_revision=value.get("projection_revision", 0),
            needs_recompute=bool(value.get("needs_recompute", False)),
            revision=value.get("revision", 1),
            created_at=value.get("created_at", ""),
            updated_at=value.get("updated_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "scope": self.scope.to_dict(),
            "concept_key": self.concept_key,
            "concept_value": self.concept_value,
            "content": self.content,
            "aspect": self.aspect,
            "lifecycle": self.lifecycle,
            "review_state": self.review_state,
            "recall_policy": self.recall_policy,
            "sensitivity": self.sensitivity,
            "evidence": [edge.to_dict() for edge in self.evidence],
            "review_receipts": [receipt.to_dict() for receipt in self.review_receipts],
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "replaces": self.replaces,
            "conflicts_with": list(self.conflicts_with),
            "evidence_revision": self.evidence_revision,
            "policy_version": POLICY_VERSION,
            "projection_revision": self.projection_revision,
            "needs_recompute": self.needs_recompute,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def evidence_digest(evidence: tuple[EvidenceEdge, ...] | list[EvidenceEdge]) -> str:
    payload = [edge.to_dict() for edge in evidence]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "evr_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
