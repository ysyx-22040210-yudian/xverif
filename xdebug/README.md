# xdebug 源码布局

- `src/api`：公开 JSON 请求、响应封装与动作调度。
- `src/core`：公共路径、基础类型与通信辅助能力。
- `src/session`：统一会话登记。
- `src/runtime`：私有后端工作目录与日志隔离。
- `src/backend`：设计与波形私有服务适配。
- `src/design`：设计数据库查询实现。
- `src/waveform`：波形、事件及协议查询实现。
- `src/combined`：动态生效驱动的联合查询实现。

公开调用只通过仓库根目录的 `tools/xdebug-env` 完成。
