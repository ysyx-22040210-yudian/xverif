# Full-chip: LSU / Cache 设计意图

## 适用范围

适用于整芯片 LSU、LoadQueue、StoreQueue、DCache、MSHR、refill/response 相关 case。

## 正确行为

- load/store 请求的地址、mask、size、source 与返回数据保持对应。
- store mask 只更新目标 byte lane。
- DCache miss/refill 的 beat/source/order 必须和 MSHR 项一致。
- replay 或 violation 检测不能改变最终 architectural 语义。

## 关键不变量

- load writeback data 必须来自正确地址、正确 beat、正确 lane。
- response source 或 beat 错配会让最终 mismatch 远离根因事件。
- partial store、multi-beat refill、多 outstanding miss 是高风险窗口。

## 常见调试入口

- bad load/store 的地址、mask、size、source、beat。
- DCache response、MSHR source、refill beat、writeback data。
