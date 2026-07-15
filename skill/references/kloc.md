# kloc 日志位置还原

kloc 把 UVM/仿真日志里的 `L_XXXXXXXX` 还原成源码 file/line/msg_id，并可统计热点或给日志加注释。

## 何时使用

- 用户给了带 `L_00000001` 的压缩日志。
- 需要还原 loc_id 对应源码位置。
- 需要查看源码上下文或统计高频 loc_id。
- 需要把压缩日志 annotate 成人类可读版本。

## 入口

优先 MCP `kverif_loc_*`。命令行：

```bash
kloc resolve L_00000001 --map out/sim.log.kloc.jsonl
kloc context L_00000001 --map out/sim.log.kloc.jsonl --before 5 --after 5
kloc stats out/sim.log --top 20
kloc annotate out/sim.log --map out/sim.log.kloc.jsonl
```

## 工作流

1. 整段日志先 `stats` 找热点。
2. 对关键 loc_id 用 `resolve`。
3. 需要源码证据再用 `context`。
4. 回答引用 `loc_id + file:line + msg_id`。

## 排障

- map 通常是 `<log>.kloc.jsonl`。
- `resolve/context` 必须有 map。
- loc_id not found：检查是否拿错 sidecar map。
- 源码文件缺失：仍可引用 map 中 file/line，但不能展示上下文。
