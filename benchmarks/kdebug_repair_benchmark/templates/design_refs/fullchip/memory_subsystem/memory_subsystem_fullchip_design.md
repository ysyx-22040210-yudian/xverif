# Full-chip: Memory Subsystem 设计意图

## 适用范围

适用于整芯片 MMU、TLB、PTW、DCache、refill、permission、PMP/PMA 交互 case。

## 正确行为

- VA 到 PA 的翻译结果必须对应当前 memory request。
- permission/fault 信息必须和请求类型、页表项、PMP/PMA 状态一致。
- cache/refill request 使用的 PA、source、beat 必须与翻译和 MSHR 项一致。
- exception 或 access fault 不能错误地绑定到其他请求。

## 关键不变量

- TLB/PTW response 与 DCache request 之间不能错拍或错配。
- fault bit 延迟或提前会导致难以从最终 mismatch 直接定位。
- refill/source/beat 错配可表现为 late data mismatch。

## 常见调试入口

- VA、PA、TLB hit/miss、PTW response、permission/fault。
- DCache request、MSHR source、refill beat、bad load/exception。
