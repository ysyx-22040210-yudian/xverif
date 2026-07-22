# Full-chip: Pipeline 设计意图

## 适用范围

适用于整芯片 pipeline、execute、bypass、writeback、commit 相关 case。

## 正确行为

- 指令从 issue/execute/writeback/commit 按设计时序推进。
- execute result、bypass result 和 writeback result 必须对应同一条指令。
- flush、replay、redirect 不能让错误结果提交。
- architectural state 只由有效提交或有效写回更新。

## 关键不变量

- 写回目的寄存器、写使能和写回数据必须来自同一 uop。
- bypass 选择不能使用 stale result。
- late failure 常见表现是前期运行正常，数千到数万周期后出现 difftest mismatch。

## 常见调试入口

- first bad commit/writeback window。
- uop id、pc、dest reg、rfWen、result data、bypass select。
