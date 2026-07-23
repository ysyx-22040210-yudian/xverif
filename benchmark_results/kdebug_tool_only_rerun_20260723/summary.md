# KDebug XiangShan Benchmark 汇总

## 本次运行范围

- 实际模型：gpt-5.5, qwen3.6-35b。
- 实际工具组：使用 KDebug。
- 有效结果：32 个 model/group/case 任务。
- 未运行模型：glm-4.7；按本轮用户指定的运行范围跳过，不纳入统计。
- 未运行工具组：不使用 KDebug；按本轮用户指定的运行范围不执行，没有生成结果，不应解读为缺失或失败。
本汇总按模型、工具组、bug 域和 benchmark 层级统计。`no_patch`、`build_fail`、`run_fail`、`judge_fail` 只作为 repair loop 的中间反馈；模型可以继续修改并重新 build/run，只有在 3600 秒内仍未让原 fail workload 通过时，才记为 `TIMEOUT`。API 限流、接口无响应等单次尝试先记为 `RETRY_LATER`；但同一模型、工具组、case 的多次 `RETRY_LATER` 累计耗时超过 3600 秒后，也按预算耗尽记为 `TIMEOUT`。runner 崩溃、脚本兼容性等仍属于基础设施问题，不计入有效模型失败率。

## 模型与工具组

| model_id | group | Trial 数 | PASS | 未修通（TIMEOUT） | 证据缺失 | 证据无效 | 规则违规 | 限流待重试 | 基础设施异常 | 有效成功率 | PASS 中位耗时 | Token 中位数 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-5.5 | with_kdebug | 16 | 14 | 2 | 0 | 0 | 0 | 0 | 0 | 87.5% | 38.82s | 21464 |
| qwen3.6-35b | with_kdebug | 16 | 6 | 10 | 0 | 0 | 0 | 0 | 0 | 37.5% | 61.88s | 7696654 |

## 按 bug 域拆分

| bug_domain | model_id | group | Trial 数 | PASS | 未修通（TIMEOUT） | 证据缺失 | 证据无效 | 规则违规 | 限流待重试 | 基础设施异常 | 有效成功率 | PASS 中位耗时 | Token 中位数 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| env | gpt-5.5 | with_kdebug | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100.0% | 41.62s | 5434 |
| env | qwen3.6-35b | with_kdebug | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 66.7% | 15.50s | 6356 |
| mixed | gpt-5.5 | with_kdebug | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 66.7% | 344.31s | 96158 |
| mixed | qwen3.6-35b | with_kdebug | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0.0% |  | 9243889 |
| rtl | gpt-5.5 | with_kdebug | 10 | 9 | 1 | 0 | 0 | 0 | 0 | 0 | 90.0% | 36.01s | 29210 |
| rtl | qwen3.6-35b | with_kdebug | 10 | 4 | 6 | 0 | 0 | 0 | 0 | 0 | 40.0% | 148.63s | 8760354 |

## 按 benchmark 层拆分

| benchmark_layer | model_id | group | Trial 数 | PASS | 未修通（TIMEOUT） | 证据缺失 | 证据无效 | 规则违规 | 限流待重试 | 基础设施异常 | 有效成功率 | PASS 中位耗时 | Token 中位数 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fullchip | gpt-5.5 | with_kdebug | 9 | 7 | 2 | 0 | 0 | 0 | 0 | 0 | 77.8% | 212.07s | 42122 |
| fullchip | qwen3.6-35b | with_kdebug | 9 | 2 | 7 | 0 | 0 | 0 | 0 | 0 | 22.2% | 116.98s | 9243889 |
| generated_wrapper | gpt-5.5 | with_kdebug | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100.0% | 33.38s | 18708 |
| generated_wrapper | qwen3.6-35b | with_kdebug | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 50.0% | 50.63s | 6905740 |
| real_rtl_it | gpt-5.5 | with_kdebug | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 100.0% | 29.67s | 18410 |
| real_rtl_it | qwen3.6-35b | with_kdebug | 4 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 50.0% | 211.71s | 2518622 |
| real_rtl_ut | gpt-5.5 | with_kdebug | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100.0% | 41.62s | 15315 |
| real_rtl_ut | qwen3.6-35b | with_kdebug | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100.0% | 21.18s | 6356 |

## 逐 Case 结果

| Case | Bug 域 | 层级 | 子系统 | 模型 | 使用 KDebug |
|---|---|---|---|---|---|
| case_001 | rtl | generated_wrapper | axi | gpt-5.5 | 通过, 30.96s, iter=1, token=18856, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_001 | rtl | generated_wrapper | axi | qwen3.6-35b | 通过, 50.63s, iter=2, token=58174, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_002 | rtl | generated_wrapper | axi | gpt-5.5 | 通过, 35.79s, iter=1, token=18560, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_002 | rtl | generated_wrapper | axi | qwen3.6-35b | 未修通（1 小时超时）, 3600.00s, iter=464, token=13753305, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_003 | rtl | real_rtl_it | memory | gpt-5.5 | 通过, 28.26s, iter=1, token=18983, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_003 | rtl | real_rtl_it | memory | qwen3.6-35b | 通过, 73.12s, iter=1, token=26161, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_004 | rtl | real_rtl_it | peripheral | gpt-5.5 | 通过, 25.89s, iter=1, token=17257, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_004 | rtl | real_rtl_it | peripheral | qwen3.6-35b | 通过, 350.29s, iter=2, token=39453, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_005 | rtl | real_rtl_it | peripheral | gpt-5.5 | 通过, 36.01s, iter=1, token=17838, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_005 | rtl | real_rtl_it | peripheral | qwen3.6-35b | 未修通（1 小时超时）, 3600.00s, iter=620, token=17362242, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_006 | rtl | fullchip | pipeline | gpt-5.5 | 通过, 2650.92s, iter=2, token=40084, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_006 | rtl | fullchip | pipeline | qwen3.6-35b | 未修通（1 小时超时）, 3599.51s, iter=436, token=16094422, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_007 | rtl | fullchip | control | gpt-5.5 | 通过, 205.79s, iter=2, token=39437, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_007 | rtl | fullchip | control | qwen3.6-35b | 未修通（1 小时超时）, 3600.00s, iter=142, token=6611841, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_008 | rtl | fullchip | lsu_cache | gpt-5.5 | 通过, 212.07s, iter=2, token=42122, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_008 | rtl | fullchip | lsu_cache | qwen3.6-35b | 通过, 224.14s, iter=2, token=56567, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_009 | rtl | fullchip | branch_redirect | gpt-5.5 | 通过, 261.06s, iter=2, token=42654, repair=rtl_only, evidence_present=true, evidence_valid=true |
| case_009 | rtl | fullchip | branch_redirect | qwen3.6-35b | 未修通（1 小时超时）, 3600.00s, iter=343, token=13209851, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_010 | rtl | fullchip | memory_subsystem | gpt-5.5 | 未修通（1 小时超时）, 3600.00s, iter=32, token=950294, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_010 | rtl | fullchip | memory_subsystem | qwen3.6-35b | 未修通（1 小时超时）, 3599.57s, iter=272, token=10908868, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_011 | env | fullchip | difftest | gpt-5.5 | 通过, 49.82s, iter=1, token=5434, repair=env_only, evidence_present=true, evidence_valid=true |
| case_011 | env | fullchip | difftest | qwen3.6-35b | 未修通（1 小时超时）, 3600.00s, iter=488, token=8781467, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_012 | env | real_rtl_ut | axi | gpt-5.5 | 通过, 41.62s, iter=2, token=15315, repair=env_only, evidence_present=true, evidence_valid=true |
| case_012 | env | real_rtl_ut | axi | qwen3.6-35b | 通过, 21.18s, iter=1, token=6356, repair=env_only, evidence_present=true, evidence_valid=true |
| case_013 | env | fullchip | build_cache | gpt-5.5 | 通过, 13.02s, iter=1, token=4214, repair=env_only, evidence_present=true, evidence_valid=true |
| case_013 | env | fullchip | build_cache | qwen3.6-35b | 通过, 9.83s, iter=1, token=4583, repair=env_only, evidence_present=true, evidence_valid=true |
| case_014 | mixed | real_rtl_it | memory | gpt-5.5 | 通过, 31.08s, iter=1, token=23944, repair=mixed, evidence_present=true, evidence_valid=true |
| case_014 | mixed | real_rtl_it | memory | qwen3.6-35b | 未修通（1 小时超时）, 3599.28s, iter=112, token=4997791, repair=mixed, evidence_present=true, evidence_valid=true |
| case_015 | mixed | fullchip | branch_redirect | gpt-5.5 | 通过, 657.54s, iter=4, token=96158, repair=mixed, evidence_present=true, evidence_valid=true |
| case_015 | mixed | fullchip | branch_redirect | qwen3.6-35b | 未修通（1 小时超时）, 3599.27s, iter=229, token=9243889, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_016 | mixed | fullchip | lsu_cache | gpt-5.5 | 未修通（1 小时超时）, 3600.00s, iter=29, token=776217, repair=no_effective_patch, evidence_present=true, evidence_valid=true |
| case_016 | mixed | fullchip | lsu_cache | qwen3.6-35b | 未修通（1 小时超时）, 3599.12s, iter=254, token=10264667, repair=env_only, evidence_present=true, evidence_valid=true |
