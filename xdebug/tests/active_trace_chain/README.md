# Active Trace Chain 可组合性实验

验证 xdebug 是否可以基于 **多次 native active trace** 构造完整因果链。

## 原理

```
signal@T0
  → trace.active_driver → source_1@T0 or T1
    → trace.active_driver → source_2@T1 or T2
      → ... → primary_input / force / limit
```

## 目录

```
p0_composability/       # P0 实验 case（7 个）
  p0_0_assign_chain/    # continuous assign chain
  p0_1_flop_boundary/   # flop temporal boundary
  p0_2_module_boundary/ # module port crossing
  p0_3_generate_for/    # generate for + module instance
  p0_4_interface_modport/   # interface + modport alias
  p0_5_mux_branch/      # mux branch handling
  p0_6_procedural_for/  # procedural for mux

common/                 # 共享脚本
  run_xdebug_chain.py   # 核心：反复调用 trace.active_driver
  verdict.py            # 比较 expected vs actual
  run_vcs.sh            # VCS 编译 + 仿真

expected/               # 期望输出
actual/                 # 实际输出（gitignore）
reports/                # 实验报告
```

## 使用

```bash
# 1. 编译所有 case 的 fixture（需要 VCS）
cd p0_0_assign_chain && make fixture

# 2. 打开 xdebug session
xdebug --json - <<'JSON'
{"api_version":"xdebug.v1","action":"session.open",
 "target":{"daidir":"out/simv.daidir","fsdb":"out/waves.fsdb"},
 "args":{"name":"p0_0","reopen":true}}
JSON

# 3. 运行链
python3 ../common/run_xdebug_chain.py p0_0 "top.out" "10ns" ../actual/p0_0_assign_chain

# 4. 判定
python3 ../common/verdict.py \
  ../expected/p0_0_assign_chain.json \
  ../actual/p0_0_assign_chain/trace_chain.json \
  ../actual/p0_0_assign_chain/verdict.json
```
