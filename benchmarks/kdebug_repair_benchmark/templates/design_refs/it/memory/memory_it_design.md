# IT: Memory 子系统设计意图

## 适用范围

适用于 memory subsystem IT，包括 AXI/TileLink memory path、mask、burst、readback、cache/refill 交互。

## 正确行为

- store 或 write burst 的地址、mask、data beat 必须写入预期位置。
- partial write 只更新 mask 选中的 byte lane。
- readback 必须反映最近一次对同一地址和 byte lane 的有效写入。
- 多 beat burst 的 beat index、offset 和 data lane 必须一致。

## 关键不变量

- address low bits、beat index 和 byte mask 的组合决定最终写入 lane。
- 写后读一致性是判断 memory path 是否正确的核心证据。
- response 顺序必须和协议约束以及 scoreboard 期望一致。

## 常见调试入口

- failing address、expected/actual data、byte mask、beat index。
- 最近一次写入该地址的 transaction 和后续读回 transaction。
