from pathlib import Path


DASHBOARD = Path(__file__).parents[1] / "frontend" / "dashboard.html"


def _you_section(html: str) -> str:
    start = html.index('<div class="config-section" id="sec-you"')
    end = html.index('<!-- ① 我 -->', start)
    return html[start:end]


def test_dashboard_exposes_only_one_you_switch_and_no_internal_views():
    html = DASHBOARD.read_text(encoding="utf-8")
    section = _you_section(html)

    assert '<h3>你 <span class="sec-en">You</span></h3>' in section
    assert "在长期相处中慢慢理解你" in section
    assert "关闭后不再更新或使用，不影响其他功能。" in section
    assert 'aria-describedby="you-setting-description"' in section
    assert section.count('role="switch"') == 1
    assert 'id="you-enabled-sw"' in section
    assert "button" not in section.lower()
    for forbidden in ("审核", "证据", "画像", "历史", "claim", "receipt", "projection"):
        assert forbidden not in section.lower()


def test_dashboard_you_request_only_submits_switch_and_revision():
    html = DASHBOARD.read_text(encoding="utf-8")
    start = html.index("async function toggleYouSetting")
    end = html.index("async function saveSamplingSettings", start)
    handler = html[start:end]

    assert html.count("/api/settings/you") == 2
    assert "enabled: desired" in handler
    assert "state_revision: _youStateRevision" in handler
    for forbidden in ("claim_id", "evidence", "review", "delete", "approve", "reject"):
        assert forbidden not in handler.lower()
