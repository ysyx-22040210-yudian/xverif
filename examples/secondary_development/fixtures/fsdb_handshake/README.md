# FSDB Handshake Fixture

这个目录提供二次开发示例可以直接使用的完整波形输入，不需要用户先准备自己的设计：

| 文件 | 内容 |
| --- | --- |
| `rtl/kverif_handshake_dut.sv` | 可综合的 valid/ready 握手 DUT RTL |
| `tb/tb_kverif_handshake.sv` | 产生四次有效握手、stall 和 response 的 testbench |
| `waves.fsdb` | 由上述源码使用 VCS/Verdi 2018 真实生成的 FSDB |
| `signal_manifest.json` | FSDB 中已验证存在的层级信号、位宽、含义和采样检查点 |
| `SHA256SUMS` | 预生成 FSDB 的完整性校验值 |
| `build_vcs.sh` | 重新编译 RTL 并在 `build/` 生成 FSDB 和 `simv.daidir` |

## 直接查询

在仓库根目录执行：

```bash
export KVERIF_HOME="$PWD"
FSDB="$KVERIF_HOME/examples/secondary_development/fixtures/fsdb_handshake/waves.fsdb"

"$KVERIF_HOME/tools/kdebug" --json action signal.scan \
  --fsdb "$FSDB" \
  --arg signal=tb_kverif_handshake.dut.accepted_count \
  --arg begin=0ns --arg end=125ns --arg format=hex \
  --max-rows 100

"$KVERIF_HOME/tools/kdebug" --json value-batch \
  --fsdb "$FSDB" \
  --signal tb_kverif_handshake.dut.req_fire \
  --signal tb_kverif_handshake.dut.rsp_data \
  --signal tb_kverif_handshake.dut.accepted_count \
  --time 95ns --format hex
```

`signal_manifest.json` 中的名字来自 FSDB 实际 scope，不是占位符。最常用的信号是：

```text
tb_kverif_handshake.dut.req_valid
tb_kverif_handshake.dut.req_ready
tb_kverif_handshake.dut.req_fire
tb_kverif_handshake.dut.req_data
tb_kverif_handshake.dut.rsp_valid
tb_kverif_handshake.dut.rsp_data
tb_kverif_handshake.dut.accepted_count
tb_kverif_handshake.dut.state_q
tb_kverif_handshake.dut.last_accepted_q
```

预生成文件由 VM 普通用户 `host` 使用 VCS `O-2018.09-1_Full64` 和 Verdi FSDB dumper
`Verdi_O-2018.09-SP2` 生成。文件大小、SHA-256、每个信号的变化次数以及四个采样点的
期望值都记录在 `signal_manifest.json` 中。重新生成的 FSDB 可能因内嵌路径或时间元数据
而具有不同 SHA-256，应按 manifest 的信号和值验证功能一致性。

完整真实后端回归会逐个查询 manifest 信号，再执行 Bash、Perl、Python 和可用时的 csh
示例：

```bash
KVERIF_HOME=/home/host/kverif \
KDEBUG_BIN=/home/host/kverif/tools/kdebug \
bash /home/host/kverif/examples/secondary_development/tests/run_real_fsdb.sh
```

在仓库根目录也可以运行：

```bash
make secondary-examples-real-test
```

## 使用 VCS/Verdi 2018 重新生成

先配置站点自己的 Synopsys 环境和 license，再执行：

```bash
cd "$KVERIF_HOME/examples/secondary_development/fixtures/fsdb_handshake"
export VCS_TARGET_ARCH=linux64
bash ./build_vcs.sh
```

生成文件位于：

```text
build/simv
build/simv.daidir/
build/waves.fsdb
build/compile.log
build/run.log
```

预生成的 `waves.fsdb` 用于开箱即用的波形查询。`simv.daidir` 与本机 VCS/Verdi 版本、
编译路径和平台相关，因此不提交；需要 design driver/load/graph 或 active-driver 联合查询时，
应在目标设备重新运行 `build_vcs.sh`，并把 `--daidir` 指向本机生成的 `build/simv.daidir`。

`SHA256SUMS` 用于校验仓库内预生成文件没有损坏，不要求重建 FSDB 字节级一致。

使用重建 KDB 做 active-driver：

```bash
bash "$KVERIF_HOME/examples/secondary_development/sh/waveform_window.sh" \
  --fsdb "$FIXTURE/waves.fsdb" \
  --daidir "$FIXTURE/build/simv.daidir" \
  --signal tb_kverif_handshake.dut.req_valid \
  --signal tb_kverif_handshake.dut.rsp_data \
  --begin 0ns --end 125ns --time 95ns \
  --active-signal tb_kverif_handshake.dut.rsp_data --active-time 95ns \
  --require-complete --out /tmp/kverif-fsdb-handshake
```

在 Verdi 2018 实测中，active-driver 将 `rsp_data` 解析到
`rtl/kverif_handshake_dut.sv` 的赋值 `rsp_data <= req_data ^ 8'h5a`，并返回
`rst_n`、`clk`、`req_fire` 三类控制条件。
