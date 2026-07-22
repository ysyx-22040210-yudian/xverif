# UT: MMU 设计意图

## 适用范围

适用于 MMU/TLB/PTW/PMP/PMA/permission 相关 UT。

## 正确行为

- TLB 将 VA 翻译为 PA，并附带权限、属性和异常信息。
- TLB miss 由 PTW 完成页表遍历后回填。
- permission、PMP/PMA 和 page fault 判定必须与请求类型一致。
- 翻译结果进入 LSU/cache 前必须与原请求保持对应。

## 关键不变量

- VA/ASID/VM state 与 TLB response 不能错配。
- fault 信息不能被延迟到错误请求，也不能被错误清除。
- replay 请求必须复用正确的翻译状态。
- DCache request 使用的 PA 必须对应当前 load/store。

## 常见调试入口

- VA、PA、TLB hit/miss、PTW response、permission/fault bits。
- LSU request 与 TLB response 的时序关系。
