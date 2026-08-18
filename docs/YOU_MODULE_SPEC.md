# `You` 模块功能规格

> 状态：Draft for Review
>
> 产品基线：已确认，不再追加需求访谈
>
> 实现状态：尚未开始
>
> 面向读者：产品、后端、前端、安全与测试开发者
>
> 最后更新：2026-08-18

本文件是待评审的目标规格，不描述当前已经上线的行为。当前能力仍以 `README.md`、
`docs/INTERNALS.md` 和代码为准。

## 1. 一句话定义

`You` 是角色基于真实记忆证据，经过长期沉淀形成的、只供模型隐式调用的“关于你的认识”。

它表达的是“角色从共同经历中如何认识这个用户”，不是对用户的客观定性、心理诊断、
人格评分或行为控制指令。

## 2. 背景与问题

Ombre Brain 当前擅长保存时间里发生的事：事件、感受、承诺、关系和原文证据。
这些记忆可以被检索和浮现，但“多次经历共同说明了什么”仍主要依赖模型在每次对话中
临时重建。

这会产生两个问题：

1. 明确称呼、边界和稳定沟通偏好无法可靠跨会话生效。
2. 同一认识可能在不同会话中被反复推断，表述和结论不稳定。

`You` 通过“原子 Claim + 证据关系 + 审视回执 + 可重建投影”解决这些问题，同时不把
记忆系统变成人格引擎。

## 3. 与 `I` 的关系

| 能力 | `I` | `You` |
|---|---|---|
| 对象 | 角色自己 | 用户 |
| 形成依据 | 自省与记忆碰撞 | 用户表达、行为和共同事件 |
| 沉淀方式 | 多次 dream 后升格 | 多次审视、独立证据与分类门槛 |
| 最终权威 | 角色自身 | 用户通过总开关决定模块是否存在于 MCP |
| 普通对话浮现 | 不直接浮现 | 仅通过单个 You 工具返回 semantic hint |
| 候选用途 | 继续参与自省 | 不驱动角色行为 |

两者语义对称，但权限不镜像。角色可以自主形成 `I`，却不能仅凭反复思考定义 `You`。

## 4. 产品原则

### 4.1 认识必须有现实依据

每条正式认识都必须能追溯到 Ombre 的普通记忆桶及其证据关系。审视次数证明它被认真
考虑过，独立证据才证明它在现实中有依据；二者不能互相替代。

### 4.2 用户只控制模块总开关

前端只展示一个 `You` 总开关，不展示 Claim、画像、证据、候选、历史版本或任何条目级操作。
用户通过这个开关决定单个 `You` MCP 工具是否暴露；不存在确认、纠正、拒绝、禁止主动提起
或删除 You 条目的 UI/API。

关闭只停用派生认识模块，不自动改变原始记忆。原始记忆仍遵守 Ombre 既有的软归档、审批
和证据保留边界。

### 4.3 正式不等于命令

任何由 `You Claim` 生成的 semantic hint 都必须保持：

```text
instructional_force = none
may_control_reasoning = false
```

它是描述性历史上下文，不是系统指令、当前用户命令或角色行为控制器。当前对话永远可以
修正、推翻或限制历史认识。

### 4.4 内部投影不是事实源

Projection 只是正式 Claim 的可重建内部投影。它可以被缓存，但必须能随时从 Claim 重建，
不能被直接编辑、提供用户界面，也不能反向成为新 Claim 的证据。

### 4.5 失败时宁可少用，不可错用

证据缺失、状态冲突、作用域不明、重算未完成或权限无法验证时，该 Claim 不得进入上下文。

### 4.6 显式开关与关闭零影响

`You` 必须由 Ombre 前端中唯一可见的独立功能开关控制，默认关闭。开关按完整
`owner_instance_id + observer_role_id + subject_user_id` 作用域持久化，不能复用普通记忆、
`I`、dream、breath、官方记忆或其他模块的开关。

关闭时必须同时停止候选生成、Review Receipt、重算、投影、上下文注入和公开读取；现有
You 派生数据只保留为不可调用的静态数据，不删除、不更新，也不得反向改变普通 Bucket、
Source、Relation、`I` 数据或既有对话行为。开关状态缺失、损坏或无法验证时按关闭处理。

重新开启不是历史回填授权。模块只能从重新开启后的新 bucket change event 继续工作；历史
回填仍须使用单独、显式、可暂停且可审计的操作。

### 4.7 对话中隐式生效且禁止照搬原文

`You` 除前端总开关外没有任何用户可见界面。在普通对话中，它必须是不可见的内部语义辅助：
回答不得暴露 `You`、Claim、Evidence、Projection、评分、来源或“画像命中”等内部机制，也
不得把 Source Bucket、Source、Claim 或 Projection 的原句直接展示、引用或拼接给用户。

运行时只能向回答模型提供经过服务端净化和抽象的语义提示，不提供 Source Bucket 或 Source
正文。模型必须结合当前对话重新组织语言，不能把注入文本当作可直接输出的文案。称呼、
专有名词、日期等无法合理改写的原子值可以按事实使用，但不得携带其来源句或上下文原文。

## 5. 目标与非目标

### 5.1 MVP 目标

- 让明确称呼、用户边界和稳定沟通偏好跨会话可靠生效。
- 让普通偏好和相处习惯经过多事件、跨日期审视后形成可追溯认识。
- 让源记忆的变化能够可靠使派生认识失效或重算。
- 在固定上下文预算内提供少量、当前可用的正式认识。
- 前端只提供默认关闭的独立总开关，确保未启用或关闭后对既有能力和回答没有行为影响。
- 由总开关单独控制 `You` MCP 工具是否出现在工具清单，其他 MCP 工具始终不受影响。
- 让认识在普通对话中只以模型重新组织后的自然表达生效，不暴露机制或复用原文。

### 5.2 明确非目标

- 不做人格分类、心理诊断、价值判断或用户评分。
- 不替用户做决定，不生成自主目标，不控制角色答案。
- 不从单次情绪或一次性状态生成长期画像。
- 不替代普通记忆、Source、Relation、`I` 或官方记忆。
- 不建立团队共享的全局用户档案。
- 不提供画像页、Claim 列表、证据页、候选页、历史页或任何条目级管理 API。
- 不使用 `mcp_require_auth` 控制 You；该字段只负责整个 `/mcp` 端点的鉴权。

## 6. 术语

| 术语 | 含义 |
|---|---|
| `You Claim` | 只表达一个认识的原子记录 |
| Source Bucket | Claim 所依据的 Ombre 普通记忆桶 |
| Evidence Edge | Claim 与一个来源桶之间的支持或反驳关系 |
| Evidence Group | 代表一个独立现实事件或独立表达的证据组 |
| Review Receipt | 某次审视使用了什么证据快照、得出什么结果的回执 |
| Projection | 从正式 Claim 重建、仅供生成 semantic hint 的内部投影 |

## 7. 作用域与身份

每条 Claim 必须绑定稳定作用域：

```yaml
scope:
  owner_instance_id: owner_xxx
  observer_role_id: role_xxx
  subject_user_id: user_xxx
```

- `owner_instance_id` 标识当前隔离的 Ombre 实例或 vault 所属者。
- `observer_role_id` 标识形成认识的角色，不使用可变显示名作为身份。
- `subject_user_id` 标识被认识的用户，不使用昵称或称呼作为身份。

读取、写入、重算和投影都必须携带完整作用域。缺少任一维度时失败关闭，禁止回退到
`global`、`default` 或其他用户的 Profile。

`AI_NAME` 与 `OMBRE_OWNER_NAME` 只用于显示，不能作为数据库主键、隔离键或授权依据。

## 8. 数据模型

### 8.1 `You Claim`

```yaml
schema_version: 1
id: you_xxx

scope:
  owner_instance_id: owner_xxx
  observer_role_id: role_xxx
  subject_user_id: user_xxx

content: 用户疲惫时通常更希望先安静一会儿
aspect: interaction_preference

lifecycle: candidate
review_state: pending
recall_policy: contextual
sensitivity: normal

evidence:
  - bucket_id: evt_xxx
    source_id: src_xxx
    evidence_group_id: eg_xxx
    stance: supports
    basis: observed_pattern

review_receipts:
  - reviewed_at: 2026-08-18T09:00:00+08:00
    reviewer_role_id: role_xxx
    evidence_revision: evr_xxx
    policy_version: you-policy-v1
    result: remains_plausible

valid_from: null
valid_until: null
replaces: null
conflicts_with: []

derivation:
  evidence_revision: evr_xxx
  policy_version: you-policy-v1
  projection_revision: 0
  needs_recompute: false

created_at: 2026-08-18T09:00:00+08:00
updated_at: 2026-08-18T09:00:00+08:00
```

`source_id` 在来源桶没有不可变 Source 时可以为空；`bucket_id`、`evidence_group_id`、
`stance` 和 `basis` 不可为空。

Claim 的 `content` 必须是对证据含义的重新表述，不得复制 Source Bucket 或 Source 中的
完整句子或连续原文片段。精确称呼、专有名词、日期等不可合理改写的原子值除外。

### 8.2 正交状态

不得用单一 `stage` 同时表达生命周期、冲突和权限。

```text
lifecycle    = candidate | formal | superseded | expired
review_state = pending | clear | conflicting
recall_policy = core | contextual
```

Claim 只有同时满足以下条件，才能用于生成普通对话所需的 semantic hint：

```text
lifecycle == formal
review_state == clear
当前时间位于 valid_from / valid_until 范围内
derivation.needs_recompute == false
所有必要 Evidence Edge 仍然有效
调用符合 recall_policy
```

### 8.3 状态转换

```text
candidate + pending
        ↓ 服务端门槛通过
formal + clear
        ↓ 被新版本替代 / 到期
superseded / expired

candidate + pending
        ↓ 与当前正式认识冲突
candidate + conflicting
        ↓ 新证据满足版本替代门槛
formal + clear / superseded
```

新观察不得直接覆盖正式 Claim。冲突候选在解决前不能进入主动行为或核心画像。

### 8.4 模块开关状态

开关是独立于 Claim 的作用域级配置：

```yaml
you_module:
  enabled: false
  scope:
    owner_instance_id: owner_xxx
    observer_role_id: role_xxx
    subject_user_id: user_xxx
  state_revision: 1
  changed_at: 2026-08-18T09:00:00+08:00
  changed_by: user_xxx
```

- 默认值必须是 `false`，只有前端总开关调用已认证配置 API 才能开启。
- 所有生产者、消费者、读取端和注入端都必须检查同一份权威状态与 revision，不能各自维护
  含义不同的本地开关。
- `enabled=false` 是最高优先级的调用否决条件；缓存中的旧 Claim、投影或 MCP 会话不能绕过它。
- 开关不得读写 `mcp_require_auth`，也不得注册、隐藏或改变任何非 You MCP 工具。
- 关闭不等于删除；现有 You 派生数据保留为不可调用的静态数据。

## 9. 证据模型

### 9.1 Evidence Edge

每条证据边必须说明：

- `bucket_id`：对应的普通记忆桶。
- `source_id`：可选的不可变原文 Source。
- `evidence_group_id`：独立现实事件或表达的分组 ID。
- `stance`：`supports` 或 `contradicts`。
- `basis`：`explicit_statement`、`observed_pattern`、`shared_event` 或
  `user_confirmation`。

### 9.2 独立证据判定

门槛按独立 Evidence Group 数量计算，不按桶数量计算。以下情况默认合并为一个证据组：

- 同一次 `grow` 产生、共享相同 `grow_batch_id` 的桶。
- 引用同一个不可变 `source_id` 的多个桶。
- 通过 `same_event` 关联的桶。
- 仅是 `continuation_of` / `continues` 的连续记录，且没有新的独立用户表达。
- 从同一个合并来源拆出的派生桶。

仅主题、人物或情绪相似不能证明是同一证据组，也不能证明彼此独立。

### 9.3 证据失效

以下变化会触发依赖 Claim 的同步失效标记和异步重算：

- 来源桶出现 `deleted_at` 删除墓碑，或在既有受控边界内被物理擦除。
- 来源桶正文被替换或关键元数据发生改变。
- Source 绑定被 detach、损坏或校验失败。
- Relation 变化导致 Evidence Group 重新归并或拆分。

仅因自动衰减进入普通 archive，不等同于用户删除，也不单独使 Evidence Edge 失效。它只改变
普通记忆的可见性；Claim 仍须保留证据链接和审计能力。若归档同时带有 `deleted_at`，则按
删除源记忆处理。

来源桶恢复后必须重新计算证据 revision，不能直接恢复旧 Claim 的可调用状态。

## 10. 审视模型

`review_dates` 不足以证明真正审视过，MVP 使用结构化 Review Receipt：

```yaml
- reviewed_at: 2026-08-18T09:00:00+08:00
  reviewer_role_id: role_xxx
  evidence_revision: evr_xxx
  policy_version: you-policy-v1
  result: remains_plausible
```

规则：

- 同一自然日最多计一次有效审视。
- 审视必须引用当时的 `evidence_revision`。
- 相同证据快照在不同日期的重复审视可以证明时间稳定性，但不能增加独立证据数量。
- 证据发生实质变化后，旧审视记录保留审计价值，但新版本必须重新通过门槛。
- 后台定时器运行成功不等于审视成功；只有生成并持久化有效 Receipt 才计数。

## 11. 形成流程

```text
已认证作用域的 You 开关为 enabled
        ↓
hold / grow 持久化原始记忆
        ↓
写入 canonical bucket change event
        ↓
durable You recompute outbox
        ↓
生成或更新原子 You candidate
        ↓
按 Evidence Group、Review Receipt、aspect、sensitivity 检查门槛
        ↓
服务端状态机升格为 formal
        ↓
重建仅供 You 工具使用的内部投影
```

dream 可以产生一次 Review Receipt，但不是候选生成或重算的唯一入口。用户从不调用 dream
时，`You` 仍必须通过耐久后台队列正常工作。

### 11.1 流水线不变量

- 开关关闭时，普通记忆链路照常完成，但不得创建或消费 You outbox 任务。
- 每个异步任务必须携带入队时的开关 `state_revision`；执行前再次读取权威状态。关闭后到达的
  旧任务直接作废，不生成 Claim、Receipt 或 Projection。
- Bucket 先耐久落盘，You 任务后入队。
- Outbox 采用至少一次投递，处理器必须幂等。
- Checkpoint 只记录进度，不是 Claim 或证据真源。
- Checkpoint 丢失或损坏时失败关闭或从已知良好副本恢复，不得当作首次运行覆盖旧状态。
- 源删除墓碑和证据变更先同步阻断召回，再异步重算投影。
- 旧 revision 的迟到任务不得覆盖新 revision。

## 12. 分类与升格门槛

| 类型 | 初始规则 | 默认调用策略 |
|---|---|---|
| 明确称呼 | 原始证据落盘后，下一次整理可直接 formal | `core` |
| 明确边界 | 原始证据落盘后，下一次整理可直接 formal | `core` |
| 明确长期事实 | 仅在语义明确长期有效或用户要求记住时直接 formal；否则先 candidate | `contextual` |
| 普通偏好 | 至少 2 个独立 Evidence Group + 3 个不同日期 Review Receipt | `contextual` |
| 相处习惯 | 至少 2 个独立 Evidence Group + 3 个不同日期 Review Receipt | `contextual` |
| 性格判断 | 不生成候选 | 不适用 |
| 自我认同 | 不生成候选 | 不适用 |
| 关系评价 | 不生成候选 | 不适用 |
| 健康、创伤、财务、性与亲密经历 | 不生成候选 | 不适用 |
| 临时情绪和一次性状态 | 默认不生成候选 | 不适用 |

模型可以建议 `aspect` 和 `sensitivity`，但服务端必须使用固定分类规则复核。模型不能把
服务端判定的敏感等级降级。

## 13. 冲突、版本与时间

### 13.1 普通观察冲突

普通观察与正式 Claim 冲突时，只创建 `candidate + conflicting`，不得覆盖当前正式版本。

### 13.2 版本替代

冲突候选取得足够的新独立证据并重新通过分类门槛后，创建新的 Claim revision，旧 Claim
进入 `superseded`，并通过 `replaces` 形成版本链。禁止原地改写旧 Claim 正文。

普通对话读取只能使用当前有效版本；旧版本仅保留内部审计与重算用途，不提供用户界面或
公开 API。

### 13.3 时间变化

独立证据足以证明认识随时间变化时，创建新版本并填写 `valid_from` / `valid_until`。旧版本进入
`superseded` 或 `expired`，内部投影只使用当前有效版本。

## 14. 删除语义

`You` 不提供条目级删除、驳回或禁止主动提起能力。前端总开关只控制模块运行和单个 MCP
工具暴露，不删除普通记忆，也不删除已形成的 You 派生数据。

普通自动归档不是“删除源记忆”：它不单独撤销 Claim 的证据效力。带 `deleted_at` 的
delete-to-archive 才触发依赖 Claim 的级联失效。来源变化或受控物理擦除后的处理继续遵守
第 9.3 节；该内部失效过程没有用户界面。

## 15. 调用策略

### 15.1 MCP 暴露门禁

- `enabled=true` 时，MCP `tools/list` 和 tool search 中只新增一个 `You` 工具。
- `enabled=false` 时，`You` 必须从 MCP 工具清单和 tool search 中完全消失，其他工具的名称、
  schema、权限和行为保持不变。
- 关闭后，持有旧工具清单的客户端直接调用 `You` 时，服务端必须返回与未知工具等价的 MCP
  错误；不得返回 `feature_disabled`、Claim 数量或任何能证明内部数据存在的信息。
- 开关变化必须刷新工具清单。若当前 FastMCP 版本不能向既有会话可靠发送 list-changed 通知，
  前端必须明确提示重启服务并重新连接 MCP，不能伪装成即时生效。
- 此门禁与 `mcp_require_auth` 正交；总开关不得关闭整个 `/mcp` 端点或改变鉴权模式。

### 15.2 `core` 与 `contextual`

- `core` 仅用于明确称呼、明确边界和关键沟通偏好；`contextual` 用于偏好、习惯、目标和生活背景。
- 两类内容都只能由已暴露的单个 `You` MCP 工具读取；不得通过 `/breath-hook`、普通 `breath`
  或其他工具旁路注入。
- 工具支持 bounded query 和 aspect 过滤；无 query 时只返回受预算约束的 `core` semantic hints。
- MVP 单次返回上限建议为 160 tokens 且最多 6 条，最终数值可通过评测调整。
- 超出预算时按固定类别顺序和时效裁剪，不使用“用户价值分”或人格评分。
- 渲染为第 15.4 节定义的短 semantic hint，不渲染 Claim 或 Projection 正文；Claim ID、aspect
  和生效时间仅作为服务端 sidecar 元数据用于审计，不进入 MCP 工具响应。
- 服务端只选择 `formal + clear + current + callable` 的 Claim，并按第 15.4 节返回 semantic hint。
- 结果数量和 token 均受硬上限约束。

### 15.3 不可调用状态

以下 Claim 永远不能用于生成普通对话的 semantic hint：

- candidate
- conflicting
- superseded
- expired
- needs_recompute
- 证据缺失或作用域不匹配

### 15.4 对话不可见与复述策略

- 开关关闭时，MCP 工具清单、SessionStart、普通工具和回答提示中不得出现任何 You 内容或
  占位提示。
- 开关开启时，普通对话只能接收服务端生成的 bounded semantic hints；不得接收 Source
  Bucket 正文、Source 正文、Evidence 标题或可直接照搬的自然语言画像段落。
- semantic hint 只描述当前回答可能需要的事实含义，并继续携带
  `instructional_force=none`；它不是回答模板。
- 回答模型必须结合当前 user turn 自行组织表达，不得声明自己正在读取、命中或引用用户画像。
- `You` 服务必须在 MCP 边界内完成原文隔离：先把 Claim 再抽象成非句子的语义零件，再把候选
  输出与 Source Bucket、不可变 Source、Claim 和 Projection 做归一化连续片段检查。连续片段
  阈值、中文归一化和不可改写原子值白名单由版本化策略统一定义。
- 抽象生成、保护文本读取或泄漏检查异常时失败关闭：本轮不返回 semantic hint，不得降级为
  Claim、Projection 或任何原文。这样宿主模型从 MCP 得不到可照搬原句，只能自行组织表达。
- Ombre 无法读取宿主模型最终回答；宿主侧 final-response middleware 可作为额外纵深防护，
  但不是暴露 `You` 工具的前置条件，也不能替代上述 MCP 出口检查。

## 16. `You` 工具边界

`You` 可以在名称和概念上与 `I` 对应，但普通对话权限更窄。

### 16.1 MVP 公开能力

- 仅在前端总开关开启后注册并暴露一个只读 `You` 工具。
- 支持 bounded query、aspect 过滤和服务端固定结果上限。
- 不返回 Source Bucket、Source、Evidence、Claim、Projection 或内部元数据，只返回服务端生成
  的短 semantic hint；semantic hint 必须通过第 15.4 节的原文复制检查。
- 功能关闭时工具不注册、不列出、不检索、不返回占位结果；旧会话直调按未知工具处理。

### 16.2 非公开能力

- 候选生成由内部 consolidation / outbox handler 完成。
- 升格由服务端状态机完成，模型没有 `force_promote` 后门。
- 重算和投影重建属于 restricted/admin command boundary，不提供用户 API。

### 16.3 工具返回安全边界

所有 semantic hint 都必须被包装为不可信历史数据，不能仅因来自 `You` 就获得更高指令权限。

## 17. 前端总开关

- 前端只显示一个 `启用 You` 二元开关及必要的生效状态，不新增页面、卡片、列表、摘要、计数、
  历史、证据或条目操作。
- 开关默认关闭。关闭提示只说明“停止形成和使用 You，并从 MCP 隐藏 You 工具；其他记忆与
  MCP 工具不受影响”。
- 开启提示只说明“You 工具将在 MCP 中可用”；不得展示已形成多少认识或任何内容预览。
- 若切换需要服务重启或客户端重新连接，前端必须明确显示真实生效状态，不能只改变按钮外观。
- 前端调用已认证配置 API，服务端原子增加 `state_revision`；环境变量覆盖、写入失败或重启失败
  时，按钮必须回显实际未生效状态。

## 18. 投影

Projection 是以下输入的确定性、可重建输出：

```text
scope + 当前有效 formal Claims + projection policy version
```

投影必须保存：

- 输入 Claim ID 与 revision 清单。
- `projection_revision`。
- `policy_version`。
- 生成时间和 token 数量。

投影只供服务端生成 semantic hint 使用，不提供用户界面，也不能整段注入普通对话。投影生成
和 semantic hint 生成都必须执行 Source Bucket 与 Source 原文复制检查，发现连续原文片段时
拒绝保存并重试。

Claim 变化后旧投影立即标记 stale，不得继续使用。投影生成失败时，可以基于当前有效 Claim
重新生成 semantic hint；若 semantic hint 也失败，本轮完全不使用 You，不能回退到 Claim 正文
或过期画像。

## 19. 安全、隐私与授权

- 前端总开关操作必须验证当前用户就是 `subject_user_id`，并原子增加 `state_revision`。
- 任一读取都必须同时验证 owner、observer role 和 subject user 作用域。
- 敏感分类由服务端固定策略判定，模型不能降低；MVP 对敏感类别直接禁止生成候选。
- 日志不得记录完整 Claim、原文 Source 或 semantic hint 正文。
- GitHub 备份和本地导出必须明确包含或排除 You 数据，并在清单中记录；不得静默遗漏。
- 不生成用户忠诚度、依赖度、说服、操控或人格符合度指标。

## 20. 失败处理与一致性

| 失败 | 要求行为 |
|---|---|
| Claim 文件或记录损坏 | 隔离该 Claim、报告诊断、禁止召回 |
| Checkpoint 损坏 | 失败关闭或恢复备份，不覆盖旧状态 |
| Outbox 重复投递 | 幂等处理，不生成重复 Claim/Receipt |
| 旧任务迟到 | revision 检查拒绝覆盖新状态 |
| Source 缺失 | Claim 立即不可调用并进入重算 |
| Projection 过期 | 不使用旧投影；重新生成 semantic hint，失败则本轮不用 You |
| 作用域缺失 | 拒绝读取或写入，禁止 global fallback |
| 开关状态缺失、损坏或权限无法验证 | 按关闭处理，不运行或调用 You，其他模块继续正常工作 |
| 关闭后旧 You 任务迟到 | 按 `state_revision` 拒绝执行，不更新任何 You 数据 |
| 原文泄漏检查失败或不可用 | 本轮不使用 You，禁止直接返回 Source Bucket、Source、Claim 或 Projection 原文 |
| MCP 动态注册/移除失败 | API 失败并回滚到权威关闭态；You 保持不可见，其他工具继续可用 |
| 关闭后旧会话直接调用 You | 按未知工具拒绝，不返回功能状态或内部数据存在性 |
| 宿主 final-response middleware 缺失 | 仍只返回已通过 MCP 出口检查的非句子语义零件；不放宽原文门禁 |

## 21. MVP 验收标准

1. 单次情绪表达不会形成正式画像。
2. 性格判断、自我认同、关系评价及敏感类别不会生成候选。
3. 同一次 `grow` 拆出的多个桶不能冒充多个独立证据。
4. 新观察不会直接覆盖旧认识，只能先形成冲突候选并重新通过门槛。
5. 来源桶出现删除墓碑、受控物理擦除或证据内容变化后，依赖 Claim 在重算完成前不可调用；
   普通自动归档不会被误判为用户删除。
6. 迟到的后台任务不能恢复已失效或被替代的 Claim。
7. 单次 You 工具返回始终受固定 token 和条目数量预算限制。
8. 多 owner、多角色和多用户数据不会跨作用域返回。
9. 所有 semantic hint 保持 `instructional_force=none`。
10. 新安装和未显式配置时 You 默认关闭，前端只显示一个独立总开关。
11. 前端不显示 Claim、画像、证据、候选、历史、数量或任何条目操作。
12. You 关闭时不会生成、审视、重算、投影或读取任何 Claim，普通记忆、`I`、dream、
    breath 和既有回答链路的行为保持不变。
13. You 关闭时不出现在 MCP `tools/list` 和 tool search 中，其他 MCP 工具保持原有 schema 与行为。
14. 关闭后，缓存旧清单的客户端直调 You 会得到未知工具错误，不会看到 `feature_disabled`。
15. 开启后只新增一个 You MCP 工具；`mcp_require_auth`、整个 `/mcp` 和其他工具不发生变化。
16. You 只能通过该 MCP 工具读取，`/breath-hook`、普通 `breath` 和其他工具没有旁路注入。
17. 关闭后到达的旧任务不能更新 You；重新开启不会自动回填关闭期间或更早的历史事件。
18. You 开启后，普通回答不暴露内部机制，不包含 Source Bucket、Source、Claim 或 Projection
    的连续原文片段，只使用模型结合当前对话重新组织的表达。
19. 原文泄漏检查不可用时，You 工具不返回 semantic hint，而不是降级为原文。
20. 服务端工具清单在开关事务内即时增减；客户端若缓存旧清单，重新拉取 `tools/list` 或重连后
    必须看到权威状态。

## 22. 测试策略

### 22.1 领域测试

- 正交状态转换与非法组合拒绝。
- 分类门槛和敏感等级不可降级。
- Evidence Group 独立性计算。
- Review Receipt 跨日去重。
- 版本链、冲突和有效期。
- 禁止类别不会生成候选。

### 22.2 一致性测试

- 默认关闭、开关 revision 竞争、关闭后迟到任务和多进程缓存失效。
- 关闭前后普通记忆、`I`、dream、breath 与非 You 工具的回归输出和副作用保持一致。
- `tools/list` / tool search 只随 You 开关增减单个工具，其他工具 manifest 逐字段一致。
- 关闭后旧会话直调 You 返回未知工具；重连或重启后的工具清单与真实开关一致。
- `mcp_require_auth` 在开关前后保持不变。
- 重新开启只消费新事件，除非用户另行启动显式历史回填。
- Source 普通归档、删除墓碑、恢复、修改和缺失时各自正确的失效或保留行为。
- Outbox 至少一次投递与幂等。
- 旧 revision 迟到任务。
- Checkpoint 损坏和恢复。
- Projection stale 检测、semantic hint 重建与失败关闭。

### 22.3 权限与安全测试

- owner / role / user 三维隔离。
- 前端总开关与配置 API 授权。
- Claim、Projection、证据和内部计数不存在用户读取 API。
- Claim 中包含命令式或 prompt injection 文本时仍无指令力。
- Source Bucket、Source、Claim 和 Projection 原文复制检测；中文标点/空白归一化绕过；
  不可改写原子值白名单。
- 普通回答不暴露 You、Claim、Evidence、Projection 或画像命中机制。
- 日志、备份和导出不泄漏或遗漏敏感 You 数据。

### 22.4 端到端场景

- 称呼直接形成 core。
- 两次独立相处事件加三次跨日审视形成 contextual preference。
- 性格判断和敏感类别始终不生成候选。
- 冲突候选重新通过门槛后新版本生效，旧版本仅内部审计可见。
- 默认关闭时完整普通对话链路与未安装 You 的基线一致。
- 关闭时 MCP 清单没有 You；开启后服务端清单只增加 You，缓存清单的客户端重新拉取或重连后
  与权威状态一致。
- `/breath-hook` 和普通 `breath` 在开关前后都不包含 You 内容。
- 开启后命中 Claim 的回答只自然复述其含义，不复现任何受保护原句。
- 未提供 final-response middleware 的接入方也只能取得通过 MCP 出口检查的非句子语义零件，
  不能取得 Source、Claim 或 Projection 原文。

## 23. 观测指标

只允许 memory-health 指标：

这些指标只用于内部诊断与测试，不进入 Dashboard、公开 API 或 `You` 工具响应。

- Claim 数量按 lifecycle / review_state 分类。
- Evidence 缺失数量。
- needs_recompute 数量。
- Outbox lag 和失败重试数量。
- Projection lag 和 stale 数量。
- 因作用域、状态、证据或预算被拒绝的召回数量。

禁止记录或推导用户价值、忠诚度、依赖度、可说服性、关系强度或人格符合度分数。

## 24. 兼容与迁移

- 现有普通桶不需要批量迁移。
- MVP 可以从功能启用后的新 bucket change event 开始生成 Claim。
- You 开关默认关闭；升级不得因为已有数据、配置缺失或旧版本行为而自动开启。
- 历史回填必须是单独、显式、可暂停和可审计的任务，默认关闭。
- `I` 数据不能迁移或复制为 `You`。
- 早期试验产生的自由文本画像不能导入、展示或直接成为正式 Claim。

## 25. 外部参考

设计参考 [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
的分层记忆、增量 Persona 更新、稳定/动态上下文拆分和固定预算做法，但不引入其运行时依赖。

明确不采用：

- 把自由文本 Persona 当作 L3 权威数据。
- 自动生成“核心原型”“认知内核”或隐性人格结论。
- 把长期用户要求编码成具有特殊命令力的全局 instruction。
- 只依赖累计条数、定时器或 checkpoint 推进派生状态。
- team + agent 作用域忽略具体 subject user 的 Profile 隔离方式。

`You` 的证据边、敏感门槛、版本链、来源失效和 MCP 显隐门禁是 Ombre 自己的产品边界。

## 26. 实施前置

### 26.1 先裁决现有哲学边界

当前 `README.md` 的设计哲学仍把 Ombre 的边界定义为“时间里发生的事，不是你是谁”，
`rule.md` 第 13 条则把“对用户的了解”主要交给官方记忆。`You` 提议把其中一部分重新定义为
Ombre 内部的、证据驱动且受用户总开关约束的派生认识。这是产品边界变化，不是普通工程实现细节。

“产品基线已确认”表示本规格不再继续需求访谈，不等于现有运行时和哲学文档已经改变。
开发开始前必须由项目所有者明确接受这次职责重划，并同步更新 `rule.md` 的唯一真源与
`README.md` 的对外表述；在此之前，不得把本文件当成现行行为依据。

### 26.2 ADR 与工程门禁

实现前必须先完成新的 ADR，至少回答：

- 为什么 `You` 不是 cognition、用户评分或人格执行器。
- 为什么它是派生认识而不是新的普通记忆真源。
- 普通记忆的遗忘和软归档如何继续成立。
- 当前思考为什么仍属于 LLM，而不是记忆控制答案。
- 默认关闭的独立开关如何贯穿生产、消费、MCP 工具注册、读取与缓存，并证明关闭态零影响。
- 如何保证 `tools/list` 只增减单个 You 工具，且不复用 `mcp_require_auth` 或改变其他工具。
- FastMCP 服务端清单如何热增减；缓存清单的客户端如何重新拉取或重连。
- semantic hint 与输出原文泄漏检查如何保证普通对话只自然复述、不暴露机制或原句。
- MCP 出口如何在宿主最终回答不可见时仍保证不返回原文；宿主 final-response middleware 仅作
  可选纵深防护。
- 新 public `You` 工具如何通过 Public Tool Design Contract。
- 需要哪些属性式、回归、隔离和端到端测试。

## 27. 建议实施顺序

1. ADR、红线和 public tool contract。
2. 默认关闭的作用域级独立开关、revision 门禁和关闭态零影响回归基线。
3. 前端唯一总开关、配置 API 与真实生效状态回显。
4. Claim / Evidence / Receipt 领域模型与状态机。
5. Bucket change event、耐久 outbox、失效和重算。
6. You MCP 工具条件注册、工具清单刷新和旧会话未知工具门禁。
7. semantic hint、MCP 出口原文泄漏检查与可选宿主纵深防护。
8. Projection、备份、导出、诊断和完整端到端测试。

在第 1 步和第 2 步通过评审前，不应实现自动升格或上下文注入。

## 28. 评审清单

评审者只需围绕以下问题给出意见：

- 产品：`You` 是否仍是“关于你的认识”，而不是用户档案或人格判断？
- 界面：除唯一总开关外，是否没有任何 Claim、画像、证据、历史或条目操作可见？
- 证据：任何正式 Claim 是否都能追溯到独立现实证据？
- 安全：Claim 是否始终无命令力，敏感内容是否失败关闭？
- 一致性：源证据变化、迟到任务和缓存是否可能恢复旧认识？
- MCP：关闭时 You 是否从工具清单完全消失，且其他工具与鉴权配置逐项不变？
- 隔离：默认关闭和运行中关闭是否确实不会改变任何非 You 功能或回答链路？
- 表达：开启后是否只在对话中隐式生效，并由模型重新组织语言而不复用原文？
- MVP：是否存在可以推迟、但不影响上述不变量的实现内容？
