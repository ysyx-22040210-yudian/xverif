# IT: Peripheral 子系统设计意图

## 适用范围

适用于 MMIO/peripheral IT，包括 UART、timer、VGA、PLIC、unmapped/error path。

## 正确行为

- MMIO 地址 decode 决定访问目标 peripheral。
- 合法 peripheral 返回对应 data/status。
- unmapped 或非法访问必须返回预期 error response。
- backpressure 期间 response payload 必须保持稳定。

## 关键不变量

- target select 不能沿用上一笔事务污染当前事务。
- response ID/status/data 必须和当前请求对应。
- 连续 error response 不能丢失、重复或错序。

## 常见调试入口

- MMIO address sequence、target decode、response status/data。
- `valid && !ready` 窗口内 payload 是否稳定。
