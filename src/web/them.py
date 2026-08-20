"""Authenticated Dashboard switch for the otherwise invisible them module.

结构与 `web/you.py` 一一对应，包括那套「先摘工具、再落盘关闭」的顺序：
关闭时若先落盘、后摘工具，中间那一瞬工具还在清单里但库已经说关了，
调用会打到一个已关闭的模块上。开启则反过来。

多一个可写字段 `max_tokens_per_person`：每人的配额上限由人类在前端定
（poluz 2026-08-20），所以它是配置项不是常量。
"""

import threading

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ombrebrain.them import ThemStoreError

from . import _shared as sh

# 前端能把每人配额调到多大。封顶不是性能考虑：them 是沉淀不是日记，
# 一个人能写满几千 token 的档案，这个模块就变成了在给人建档。
MAX_TOKENS_CEILING = 4000
MIN_TOKENS_FLOOR = 200


def register(mcp) -> None:
    commit_lock = threading.Lock()

    def response_payload() -> dict[str, object]:
        state = sh.them_service.status()
        return {
            "enabled": bool(state.enabled),
            "state_revision": int(state.state_revision),
            "max_tokens_per_person": int(sh.them_service.max_tokens_per_person),
        }

    @mcp.custom_route("/api/settings/them", methods=["GET"])
    async def get_them_setting(request: Request) -> Response:
        error = sh._require_auth(request)
        if error:
            return error
        return JSONResponse(response_payload(), headers={"Cache-Control": "no-store"})

    @mcp.custom_route("/api/settings/them", methods=["POST"])
    async def set_them_setting(request: Request) -> Response:
        error = sh._require_auth(request)
        if error:
            return error
        try:
            body = await sh._read_json_object(request)
        except (ValueError, TypeError):
            return JSONResponse({"error": "无效 JSON"}, status_code=400)
        if not set(body) <= {"enabled", "state_revision", "max_tokens_per_person"}:
            return JSONResponse(
                {"error": "只接受 enabled、state_revision 和 max_tokens_per_person"},
                status_code=400,
            )
        if not {"enabled", "state_revision"} <= set(body):
            return JSONResponse(
                {"error": "enabled 和 state_revision 必填"}, status_code=400
            )
        enabled = body.get("enabled")
        revision = body.get("state_revision")
        if (
            not isinstance(enabled, bool)
            or isinstance(revision, bool)
            or not isinstance(revision, int)
        ):
            return JSONResponse({"error": "开关参数格式无效"}, status_code=400)

        quota = body.get("max_tokens_per_person")
        if quota is not None:
            if isinstance(quota, bool) or not isinstance(quota, int):
                return JSONResponse({"error": "配额必须是整数"}, status_code=400)
            if not MIN_TOKENS_FLOOR <= quota <= MAX_TOKENS_CEILING:
                return JSONResponse(
                    {
                        "error": f"每人配额只能在 {MIN_TOKENS_FLOOR}–{MAX_TOKENS_CEILING} "
                        "之间；再大就不是沉淀，是在给人建档了。"
                    },
                    status_code=400,
                )

        with commit_lock, sh.them_tool_gate.lock:
            before = sh.them_service.status()
            if revision != before.state_revision:
                return JSONResponse(
                    {"error": "开关状态已变化，请刷新后重试"}, status_code=409
                )
            try:
                if enabled:
                    state = sh.them_service.set_enabled(True, expected_revision=revision)
                    visible = sh.them_tool_gate.sync(True)
                else:
                    visible = sh.them_tool_gate.sync(False)
                    if visible:
                        raise RuntimeError("MCP tool removal failed")
                    state = sh.them_service.set_enabled(False, expected_revision=revision)
                if visible != state.enabled:
                    raise RuntimeError("MCP tool state mismatch")
                if quota is not None:
                    section = sh.them_service.config.setdefault("them", {})
                    section["max_tokens_per_person"] = quota
            except ThemStoreError as exc:
                try:
                    sh.them_tool_gate.sync(sh.them_service.status().enabled)
                except Exception:
                    pass
                status = 409 if "revision conflict" in str(exc) else 503
                message = (
                    "开关状态已变化，请刷新后重试" if status == 409 else "them 暂时不可用"
                )
                return JSONResponse({"error": message}, status_code=status)
            except Exception:
                if enabled and before.enabled is False:
                    current = sh.them_service.status()
                    if current.enabled:
                        try:
                            sh.them_service.set_enabled(
                                False, expected_revision=current.state_revision
                            )
                        except Exception:
                            pass
                try:
                    sh.them_tool_gate.sync(sh.them_service.status().enabled)
                except Exception:
                    pass
                return JSONResponse({"error": "them 开关未能生效"}, status_code=503)

        return JSONResponse(response_payload(), headers={"Cache-Control": "no-store"})
