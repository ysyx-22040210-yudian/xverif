# Full-chip: Control 设计意图

## 适用范围

适用于 valid/ready/rfWen/flush/replay/redirect 等控制链路 case。

## 正确行为

- valid/ready 表示 pipeline stage 间真实传输。
- flush 必须取消错误路径上的指令，不能取消正确路径上的已确认更新。
- rfWen 必须与当前有效写回 uop 对齐。
- replay/redirect 不能让控制信号和数据 payload 脱节。

## 关键不变量

- 数据正确不代表控制正确；rfWen 被吞或 flush 错位也会导致 architectural mismatch。
- control signal 的 first bad event 往往早于最终寄存器 mismatch。
- backpressure 或 flush 期间 payload 与控制位必须保持一致。

## 常见调试入口

- valid/ready、rfWen、flush、redirect、commit valid。
- 正确 result data 是否被错误控制信号阻止提交。
