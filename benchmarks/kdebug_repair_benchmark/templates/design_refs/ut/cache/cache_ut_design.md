# UT: Cache 设计意图

## 适用范围

适用于 Cache UT，包括 refill、writeback、probe、MSHR、data array、tag/meta 路径。

## 正确行为

- 请求地址被分解为 tag、set、way、offset。
- 命中时返回对应 line/beat 的数据。
- miss 时分配 MSHR，并按 source/beat 顺序接收 refill。
- refill 数据写回 data array 后，后续 hit 必须读到一致的数据。
- store mask 只更新被选中的 byte lane。

## 关键不变量

- 同一个 MSHR source 的 response beat 不能错序映射。
- write mask、beat offset 和 line offset 必须一致。
- meta/tag 与 data array 更新必须保持一致。
- replay 或 nack 不能重复提交同一个已完成请求。

## 常见调试入口

- 请求地址、set/way、MSHR source、refill beat、data mask。
- load/store 返回数据与最近一次写入或 refill 的关系。
