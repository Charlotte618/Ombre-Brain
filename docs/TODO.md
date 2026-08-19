# You 模块实施清单

本清单把 [`YOU_MODULE_SPEC.md`](YOU_MODULE_SPEC.md) 拆成可独立验证的实现步骤。每项完成后才进入下一项。

## 1. 产品与架构门禁

- [x] 更新 `rule.md` 与 README 的哲学边界。
- [x] 接受 ADR-0004，明确独立开关、内部派生状态、MCP 显隐和原文保护。
- 验收：现行规则不再与 `You` 规格冲突，且未宣称它是人格或认知层。
- 验证：`rg -n "You|不是.*认知|mcp_require_auth" rule.md README.md docs/adr/ADR-0004-you-derived-understanding-boundary.md`

## 2. 领域与持久化

- [x] 实现稳定三维作用域、开关状态、Claim/Evidence/Receipt/Projection schema。
- [x] 实现 SQLite 事务状态仓库、固定分类策略和原文连续片段检查。
- 范围外：用户可见画像、条目编辑、历史回填。
- 验证：`pytest tests/test_you_domain.py -q`

## 3. 耐久流水线

- [x] 接入 canonical bucket change，提交后登记只含 ID/revision 的 You outbox。
- [x] 实现幂等消费、迟到 revision 拒绝、候选形成、跨日审视、升格、冲突和来源失效。
- 范围外：关闭期间和启用前历史的自动回填。
- 验证：`pytest tests/test_you_pipeline.py -q`

## 4. 开关 API 与 MCP

- [x] 实现已认证 `GET/POST /api/settings/you`。
- [x] 实现单个 `You` 工具热注册/移除和调用时二次门禁。
- [x] 更新 Public Tool Design Contract，证明其他工具与鉴权不变。
- 验证：`pytest tests/test_you_toggle.py tests/test_public_tool_design_phase16.py -q`

## 5. 前端唯一开关

- [x] 在 Dashboard 常规设置增加一个二元开关及真实生效状态。
- [x] 确认不存在 Claim、证据、画像、数量、历史或条目操作界面。
- 验证：`pytest tests/test_you_frontend_contract.py -q`

## 6. 备份、迁移与完整验收

- [x] 本地导出与 GitHub 备份显式包含 `.you` 数据并验证清单。
- [x] 更新 README、INTERNALS、规格状态和测试契约。
- [x] 运行针对性、全量 pytest 和更新清单检查。
- [x] 2026-08-19 在隔离临时 vault 中启动真实 `streamable-http` 双连接器服务，完成 MCP `tools/list` 验收：主 `/mcp` 为 `13 → 14 → 13`，`/mcp-extra` 恒为 3，合计 `16 → 17 → 16`；只新增 `You`，其余工具 manifest 逐项不变；旧会话调用 `You` 被按未知工具拒绝；`mcp_require_auth` 保持不变。
  > 以上是在合并前的 `testing@081d939`（3.3.0 双连接器）基底上测的，保留作历史记录。
- [x] 2026-08-19 合并到 `testing` 3.4.1（信件已并回主链路、`/mcp-extra` 退役）后重新验收：唯一连接器 `/mcp` 为 `16 → 17 → 16`，只增减 `You`；拿过期 `state_revision` 提交开关返回 `409`；Docker `--no-cache` 从零构建，容器内全量 pytest `2336 passed, 124 skipped`；MCP 工具逐个真实调用 `25/25` 符合预期。
- [x] 2026-08-19 基于最新 `testing` 使用 `docker build --no-cache` 生成镜像 `ombre-brain:acceptance-testing-20260819`（镜像 ID `20b52b71d4a0`），从该镜像启动隔离容器；`/health` 返回 `ok`、`/api/version` 返回 `3.3.0`，启动日志无非预期错误。
- [x] 2026-08-19 在真实 Dashboard 上完成桌面 `1440×900` 与移动 `390×844` 浏览器验收：页面无横向溢出，`You` 区域和开关完整可见，开关均可完成 `关闭 → 开启 → 关闭` 并持久化真实状态，浏览器控制台无应用错误。
- 验证：备份归档专项测试 `35 passed`；合并后定向门禁 `156 passed, 90 skipped`；全量 pytest
  （排除提交前无法读取合并结果 `HEAD` 字节的清单断言）`2341 passed, 99 skipped, 1 deselected`；
  Ruff 与 `deploy/gen_update_manifest.py --check` 通过。
- 真实 MCP 验收结果：关闭态合计 16 个工具，开启态 17 个工具，关闭后恢复 16 个工具；新增集合仅为
  `You`。合并提交后 `test_shipped_manifest_matches_repository_bytes` 已通过；无缓存 Docker 构建/启动及
  Dashboard 桌面/移动端验收均已通过。
