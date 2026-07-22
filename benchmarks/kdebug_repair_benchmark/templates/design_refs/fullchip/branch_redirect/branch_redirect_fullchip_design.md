# Full-chip: Branch / Redirect 设计意图

## 适用范围

适用于 branch、jump、redirect、frontend PC、commit PC 相关 case。

## 正确行为

- branch/jump 的 target 按 ISA 和预测/校正逻辑计算。
- redirect target 必须被 frontend 按正确时序接收。
- 错误路径指令必须被 flush，正确路径指令不能被错误取消。
- PC mismatch 可能早于寄存器 mismatch 暴露。

## 关键不变量

- redirect valid、target、原因和 uop/pc 必须对应。
- frontend 接收到的 redirect target 必须等于 producer 生成的 target。
- commit PC、difftest PC 和 frontend PC 的差异需要按时间因果回溯。

## 常见调试入口

- first PC divergence。
- 最近一次 redirect producer、target、frontend accept、commit PC。
