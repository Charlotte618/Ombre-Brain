"""导入前备份必须覆盖导入会写的每一类文件。

上层在备份失败时会中止导入，理由写着「为避免覆盖后无法找回记忆」——
也就是说它把这个 zip 当**完整回滚点**用。而原先它只打包 `*.md`：
`_sources/` 下的原文证据、`.you` / `.them` 两个模块库都会被导入覆盖，
却一个都没备份。

一个不完整的回滚点比没有回滚点更危险：人会依着它去做不可逆的操作。
"""

import os
import zipfile

import pytest

from web.github import _pre_import_backup, _should_back_up_before_import


# 导入实际会写的四类路径，来源见 github_sync 的安装循环与 _MODULE_SNAPSHOT_PATHS
被导入覆盖的 = [
    "2026/08/bucket_abc.md",
    "_sources/deadbeef.source",
    ".you/you.sqlite3",
    ".them/them.sqlite3",
    ".you/you.sqlite3-wal",
    ".them/them.sqlite3-shm",
]


@pytest.mark.parametrize("相对路径", 被导入覆盖的)
def test_导入会覆盖的都在备份范围里(相对路径):
    assert _should_back_up_before_import(相对路径), (
        f"{相对路径} 会被导入覆盖，却不在备份范围里——"
        "回滚点缺了它，导入失败后这份数据就找不回来了"
    )


@pytest.mark.parametrize("相对路径", [
    ".import_backups/pre_import_x.zip",   # 备份自己，不能套娃
    "embeddings.db",                      # 导入不写它，靠「重算所有向量」恢复
    "notes.txt",
])
def test_导入不碰的不必备份(相对路径):
    assert not _should_back_up_before_import(相对路径)


def test_真打出来的zip里四类文件都在(tmp_path):
    """不只测判定函数，测真跑一遍 zip 里到底有什么。"""
    for 相对路径 in 被导入覆盖的:
        目标 = tmp_path / 相对路径
        目标.parent.mkdir(parents=True, exist_ok=True)
        目标.write_bytes(b"x")
    (tmp_path / "embeddings.db").write_bytes(b"x")

    zip路径 = _pre_import_backup(str(tmp_path))
    assert zip路径, "备份没生成"
    with zipfile.ZipFile(zip路径) as z:
        打包了 = {n.replace(os.sep, "/") for n in z.namelist()}

    for 相对路径 in 被导入覆盖的:
        assert 相对路径 in 打包了, f"{相对路径} 没进备份"
    assert "embeddings.db" not in 打包了
