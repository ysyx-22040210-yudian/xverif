# UT: AXI 总线设计意图

## 适用范围

适用于 AXI UT case，例如写通道配对、burst length、last beat、error backpressure。

## 正确行为

- AW 通道接受写地址和事务属性，W 通道接受写数据 beat，B 通道返回写响应。
- AR 通道接受读地址和事务属性，R 通道返回读数据 beat。
- 每个 burst 的 beat 数必须与 AxLEN 归一化后的长度一致。
- WLAST/RLAST 必须只在对应 burst 的最后一个 beat 有效。
- B/R response 的 ID 或 source 必须能回到正确的请求事务。
- backpressure 期间，valid 侧 payload 必须保持稳定。

## 关键不变量

- `valid && ready` 才表示该通道一次传输完成。
- 多 outstanding 写事务下，B response 不能绑定到错误 AW owner。
- error response 不能破坏 beat 计数和 response 排序。
- burst 边界不能提前或延后消费 last beat。

## 常见调试入口

- AW/W/B 或 AR/R 的 handshake 时间窗。
- ID/source、burst length、beat index、last 标记。
- scoreboard 的 expected/actual transaction。
