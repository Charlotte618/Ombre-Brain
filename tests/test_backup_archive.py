import io
import sqlite3
import zipfile

import frontmatter
import pytest

from backup_archive import (
    BackupArchiveError,
    build_export_archive,
    read_backup_archive,
)
from bucket_manager import BucketManager
from embedding_engine import EmbeddingEngine
from migrate_engine import MigrateEngine


class _Backend:
    def vector_dim(self):
        return 2


def _config(root):
    return {
        "buckets_dir": str(root),
        "embedding": {"enabled": False},
        "storage": {"external_change_poll_seconds": 0},
    }


def _engine(config, model="test-embedding"):
    engine = EmbeddingEngine(config)
    engine.model = model
    engine._backend = _Backend()
    return engine


def _write_bucket(root, bucket_id="memory-1", content="important memory"):
    path = root / "dynamic" / "general" / f"memory_{bucket_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(
        content,
        id=bucket_id,
        name="Memory",
        type="dynamic",
        domain=["general"],
        created="2026-07-11T12:00:00",
    )
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def _rewrite_zip(payload, updates):
    source = zipfile.ZipFile(io.BytesIO(payload), "r")
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            target.writestr(info.filename, updates.get(info.filename, source.read(info)))
    return output.getvalue()


def test_export_archive_has_verified_manifest_and_sqlite_snapshot(tmp_path):
    vault = tmp_path / "vault"
    bucket = _write_bucket(vault)
    engine = _engine(_config(vault))
    engine._store_embedding("memory-1", [0.1, 0.2], "digest")

    payload, manifest = build_export_archive(
        str(vault), engine.db_path, {"exported_at": "now", "version": "test"}
    )
    package = read_backup_archive(payload)

    assert package["integrity_verified"] is True
    assert package["integrity_warning"] == ""
    assert package["manifest"] == manifest
    assert package["files"]["buckets/dynamic/general/memory_memory-1.md"] == bucket.read_bytes()
    assert "embeddings.db" in package["files"]
    assert manifest["file_count"] == 3

    db_file = tmp_path / "snapshot.db"
    db_file.write_bytes(package["files"]["embeddings.db"])
    with sqlite3.connect(db_file) as connection:
        row = connection.execute(
            "SELECT bucket_id, content_hash FROM embeddings WHERE bucket_id = ?",
            ("memory-1",),
        ).fetchone()
    assert row == ("memory-1", "digest")


def test_manifest_rejects_tampered_member(tmp_path):
    vault = tmp_path / "vault"
    path = _write_bucket(vault)
    engine = _engine(_config(vault))
    payload, _ = build_export_archive(
        str(vault), engine.db_path, {"exported_at": "now", "version": "test"}
    )
    member = f"buckets/dynamic/general/{path.name}"
    tampered = _rewrite_zip(payload, {member: b"changed after manifest"})

    with pytest.raises(BackupArchiveError, match="不一致|校验失败"):
        read_backup_archive(tampered)


def test_reader_rejects_traversal_and_normalizes_legacy_windows_paths():
    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("buckets/../../outside.md", b"bad")
    with pytest.raises(BackupArchiveError, match="不安全路径"):
        read_backup_archive(malicious.getvalue())

    legacy = io.BytesIO()
    with zipfile.ZipFile(legacy, "w") as archive:
        archive.writestr("buckets\\dynamic\\general\\old.md", b"legacy")
    package = read_backup_archive(legacy.getvalue())
    assert package["integrity_verified"] is False
    assert package["files"] == {"buckets/dynamic/general/old.md": b"legacy"}
    assert "旧版备份" in package["integrity_warning"]


@pytest.mark.asyncio
async def test_export_to_empty_vault_restores_markdown_and_current_embedding_schema(tmp_path):
    source_vault = tmp_path / "source"
    _write_bucket(source_vault, content="restore this exact text")
    source_engine = _engine(_config(source_vault))
    source_engine._store_embedding("memory-1", [0.3, 0.4], "source-hash")
    payload, _ = build_export_archive(
        str(source_vault),
        source_engine.db_path,
        {
            "exported_at": "2026-07-11T12:00:00",
            "version": "test",
            "embedding": {"model": "test-embedding", "dim": 2, "backend": "api"},
        },
    )

    target_vault = tmp_path / "target"
    target_config = _config(target_vault)
    target_engine = _engine(target_config)
    manager = BucketManager(target_config, embedding_engine=target_engine)
    migrate = MigrateEngine(target_config, manager, target_engine)

    parsed = await migrate.parse_zip(payload)
    assert parsed["ok"] is True
    assert parsed["integrity_verified"] is True
    await migrate.apply({})

    restored = await manager.get("memory-1")
    assert restored is not None
    assert restored["content"] == "restore this exact text"
    assert await target_engine.get_embedding("memory-1") == [0.3, 0.4]
    assert target_engine.get_content_hash("memory-1") == "source-hash"
    assert migrate.get_status()["result"] == {"imported": 1, "skipped": 0}


@pytest.mark.asyncio
async def test_keep_both_maps_imported_vector_to_new_id(tmp_path):
    source_vault = tmp_path / "source"
    _write_bucket(source_vault, content="imported version")
    source_engine = _engine(_config(source_vault))
    source_engine._store_embedding("memory-1", [0.7, 0.8], "imported-hash")
    payload, _ = build_export_archive(
        str(source_vault),
        source_engine.db_path,
        {
            "exported_at": "now",
            "version": "test",
            "embedding": {"model": "test-embedding", "dim": 2, "backend": "api"},
        },
    )

    target_vault = tmp_path / "target"
    _write_bucket(target_vault, content="local version")
    target_config = _config(target_vault)
    target_engine = _engine(target_config)
    manager = BucketManager(target_config, embedding_engine=target_engine)
    migrate = MigrateEngine(target_config, manager, target_engine)

    parsed = await migrate.parse_zip(payload)
    assert parsed["conflicts_count"] == 1
    await migrate.apply({"memory-1": "keep_both"})

    buckets = await manager.list_all()
    assert {bucket["content"] for bucket in buckets} == {"local version", "imported version"}
    imported = next(bucket for bucket in buckets if bucket["content"] == "imported version")
    assert imported["id"] != "memory-1"
    assert await target_engine.get_embedding(imported["id"]) == [0.7, 0.8]


@pytest.mark.asyncio
async def test_overwrite_preserves_old_memory_under_unique_archived_id(tmp_path):
    source_vault = tmp_path / "source"
    _write_bucket(source_vault, content="imported version")
    source_engine = _engine(_config(source_vault))
    payload, _ = build_export_archive(
        str(source_vault),
        source_engine.db_path,
        {
            "exported_at": "now",
            "version": "test",
            "embedding": {"model": "test-embedding", "dim": 2, "backend": "api"},
        },
    )

    target_vault = tmp_path / "target"
    _write_bucket(target_vault, content="local version")
    target_config = _config(target_vault)
    target_engine = _engine(target_config)
    manager = BucketManager(target_config, embedding_engine=target_engine)
    migrate = MigrateEngine(target_config, manager, target_engine)

    await migrate.parse_zip(payload)
    await migrate.apply({"memory-1": "overwrite"})

    buckets = await manager.list_all(include_archive=True)
    assert {bucket["content"] for bucket in buckets} == {"local version", "imported version"}
    assert len({bucket["id"] for bucket in buckets}) == 2
    archived = next(bucket for bucket in buckets if bucket["content"] == "local version")
    assert archived["id"].startswith("memory-1-superseded-")
    assert archived["metadata"]["superseded_by"] == "memory-1"


@pytest.mark.asyncio
async def test_overwrite_leaves_old_memory_untouched_when_new_content_write_fails(tmp_path, monkeypatch):
    """回归锁死找茬会话发现的 bug：overwrite 冲突原来是「先删旧、再写新」，

    写新内容失败时旧桶已经被移进 archive/ 改名，两边都没有=数据丢失。
    修复后顺序反过来：新内容先完整落盘到暂存文件，写失败旧桶必须完全不受影响。
    """
    source_vault = tmp_path / "source"
    _write_bucket(source_vault, content="imported version")
    source_engine = _engine(_config(source_vault))
    payload, _ = build_export_archive(
        str(source_vault),
        source_engine.db_path,
        {
            "exported_at": "now",
            "version": "test",
            "embedding": {"model": "test-embedding", "dim": 2, "backend": "api"},
        },
    )

    target_vault = tmp_path / "target"
    _write_bucket(target_vault, content="local version")
    target_config = _config(target_vault)
    target_engine = _engine(target_config)
    manager = BucketManager(target_config, embedding_engine=target_engine)
    migrate = MigrateEngine(target_config, manager, target_engine)

    def _boom(self, pb, target_id, buckets_dir):
        raise OSError("simulated disk failure while staging new content")

    monkeypatch.setattr(MigrateEngine, "_write_bucket_file_staged", _boom)

    await migrate.parse_zip(payload)
    await migrate.apply({"memory-1": "overwrite"})

    # 新内容落盘先炸：旧桶必须还在原地、原样、原 ID，完全没被删/被改名。
    buckets = await manager.list_all(include_archive=True)
    assert len(buckets) == 1
    survivor = buckets[0]
    assert survivor["id"] == "memory-1"
    assert survivor["content"] == "local version"
    assert survivor["metadata"].get("type") != "archived"
    assert migrate._apply_errors, "写入失败应该被记录成一条 apply error"


@pytest.mark.asyncio
async def test_overwrite_cleans_up_staged_file_when_old_bucket_handling_fails(tmp_path, monkeypatch):
    """写新内容成功，但处理旧桶（delete+rekey）失败：暂存文件必须被清理掉，

    不能留下一个既不是新桶也不是旧桶、谁都不认的孤儿 .staging 文件。
    """
    source_vault = tmp_path / "source"
    _write_bucket(source_vault, content="imported version")
    source_engine = _engine(_config(source_vault))
    payload, _ = build_export_archive(
        str(source_vault),
        source_engine.db_path,
        {
            "exported_at": "now",
            "version": "test",
            "embedding": {"model": "test-embedding", "dim": 2, "backend": "api"},
        },
    )

    target_vault = tmp_path / "target"
    _write_bucket(target_vault, content="local version")
    target_config = _config(target_vault)
    target_engine = _engine(target_config)
    manager = BucketManager(target_config, embedding_engine=target_engine)
    migrate = MigrateEngine(target_config, manager, target_engine)

    def _boom(self, bucket_id):
        raise OSError("simulated failure while archiving the old bucket")

    monkeypatch.setattr(MigrateEngine, "_rekey_archived_conflict", _boom)

    await migrate.parse_zip(payload)
    await migrate.apply({"memory-1": "overwrite"})

    staged_leftovers = list((target_vault / "dynamic").rglob("*.staging-*"))
    assert staged_leftovers == [], f"暂存文件没被清理: {staged_leftovers}"
    assert migrate._apply_errors, "旧桶处理失败应该被记录成一条 apply error"


@pytest.mark.asyncio
async def test_missing_snapshot_vector_is_durably_queued(tmp_path):
    source_vault = tmp_path / "source"
    _write_bucket(source_vault)
    source_engine = _engine(_config(source_vault))
    payload, _ = build_export_archive(
        str(source_vault),
        source_engine.db_path,
        {
            "exported_at": "now",
            "version": "test",
            "embedding": {"model": "test-embedding", "dim": 2, "backend": "api"},
        },
    )

    class Outbox:
        def __init__(self):
            self.queued = []

        def enqueue(self, bucket_id, content):
            self.queued.append((bucket_id, content))
            return True

    target_vault = tmp_path / "target"
    target_config = _config(target_vault)
    target_engine = _engine(target_config)
    manager = BucketManager(target_config, embedding_engine=target_engine)
    outbox = Outbox()
    manager.attach_embedding_outbox(outbox)
    migrate = MigrateEngine(target_config, manager, target_engine)

    assert (await migrate.parse_zip(payload))["ok"] is True
    await migrate.apply({})
    assert outbox.queued == [("memory-1", "important memory")]
    assert migrate.get_status()["reindex_progress"] == {"done": 1, "total": 1, "errors": 0}
