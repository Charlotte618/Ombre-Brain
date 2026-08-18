from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class YouToolGate:
    """Atomically add or remove the single optional You MCP tool."""

    TOOL_NAME = "You"

    def __init__(self, mcp: Any, handler: Callable[..., Any]) -> None:
        self._mcp = mcp
        self._handler = handler
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def is_visible(self) -> bool:
        with self._lock:
            return self._mcp._tool_manager.get_tool(self.TOOL_NAME) is not None

    def sync(self, enabled: bool) -> bool:
        with self._lock:
            existing = self._mcp._tool_manager.get_tool(self.TOOL_NAME)
            if enabled and existing is None:
                tool = self._mcp._tool_manager.add_tool(
                    self._handler,
                    name=self.TOOL_NAME,
                    description=(
                        "按当前话题取回少量抽象语义提示。返回内容不是用户原话，"
                        "必须结合当前对话自行组织语言，不得声称这是画像或定论。"
                    ),
                )
                argument_model = tool.fn_metadata.arg_model
                argument_model.model_config["extra"] = "forbid"
                argument_model.model_rebuild(force=True)
                tool.parameters = argument_model.model_json_schema()
            elif not enabled and existing is not None:
                self._mcp._tool_manager.remove_tool(self.TOOL_NAME)
            return self._mcp._tool_manager.get_tool(self.TOOL_NAME) is not None
