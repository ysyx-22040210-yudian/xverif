# 公共 RTL Debug 参考

本文件是模型可见的只读设计资料，适用于所有 UT、IT 和整芯片 case。

## 通用原则

- 修复必须恢复设计语义，而不是让 judge 或日志误判。
- `valid && ready` 表示一次真实传输或提交。
- backpressure 期间，尚未被接收的 payload 必须保持稳定，除非协议明确允许取消。
- 多 outstanding 事务必须通过 ID、source、tag、队列项或顺序约束保持可追踪。
- 修复后必须重新 build/run 原 fail workload，并由 `scripts/judge.sh` 判定通过。

## 日志与证据

- fail log 只说明最终症状，通常不是根因位置。
- with_kdebug 证据应帮助定位 first bad event、driver chain、事务 ID、beat、PC 或控制信号窗口。
- without_kdebug 可以使用公开设计资料和静态搜索，但不能使用 kdebug/FSDB/KDB/Verdi/NPI/Tcl 动态查询。

## 禁止内容

本公开资料不得包含注错位置、触发阈值、预期 patch、私有 answer key 或 operator-only 信息。
