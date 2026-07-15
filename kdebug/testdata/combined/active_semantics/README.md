# Active trace semantics fixture

这个 combined synthetic fixture 用真实 VCS daidir + FSDB 验证
`trace.active_driver` 的高风险语义：

- inactive mux branch 不应被当成 active cause；
- enable 为 0 时，不应追到当拍变化的上游 data；
- valid-ready 未握手时，不应追到当拍变化的 payload；
- arbiter loser 不应被当成 active cause；
- idle/default branch 应给出确定性 active driver；
- `limits.max_nodes` 截断仍应通过 `meta.truncated` 显式暴露。

该 fixture 独立于既有 `active_driver` 与 `interface_port_root`，避免新增 case
改变旧测试按源码行号断言的合同。
