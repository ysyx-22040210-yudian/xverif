# KDebug XiangShan Benchmark 汇总

本汇总按模型、工具组、bug 域和 benchmark 层级统计。`no_patch`、`build_fail`、`run_fail`、`judge_fail` 只作为 repair loop 的中间反馈；模型可以继续修改并重新 build/run，只有在 3600 秒内仍未让原 fail workload 通过时，才记为 `TIMEOUT`。API 限流、接口无响应等单次尝试先记为 `RETRY_LATER`；但同一模型、工具组、case 的多次 `RETRY_LATER` 累计耗时超过 3600 秒后，也按预算耗尽记为 `TIMEOUT`。runner 崩溃、脚本兼容性等仍属于基础设施问题，不计入有效模型失败率。

品牌迁移说明：本报告的工具组、命令、目录和文件名已统一使用 `kverif/kdebug` 新名称。内嵌历史运行截图保留采集时的原始像素，仅作为更名前同一测试版本的证据；实际调用请以当前 `kdebug` 命令为准。

补测口径说明：glm-4.7 的剩余未完成项已按用户要求停止补测，保留既有历史结果，不再补跑；这些 GLM 未完成项不作为本次 qwen3.6-35b 剩余项统计。qwen3.6-35b 本轮剩余项已全部跑到终态。

## 模型与工具组

| model_id | group | Trial 数 | PASS | 未修通（TIMEOUT） | 证据缺失 | 规则违规 | 限流待重试 | 基础设施异常 | 有效成功率 | PASS 中位耗时 | Token 中位数 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glm-4.7 | with_kdebug | 18 | 0 | 6 | 0 | 0 | 12 | 0 | 0.0% |  | 0 |
| glm-4.7 | without_kdebug | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0.0% |  | 4251201 |
| gpt-5.5 | with_kdebug | 16 | 12 | 4 | 0 | 0 | 0 | 0 | 75.0% | 202.47s | 73362 |
| gpt-5.5 | without_kdebug | 16 | 11 | 5 | 0 | 0 | 0 | 0 | 68.8% | 149.27s | 74984 |
| qwen3.6-35b | with_kdebug | 16 | 7 | 9 | 0 | 0 | 0 | 0 | 43.8% | 19.75s | 5281314 |
| qwen3.6-35b | without_kdebug | 16 | 5 | 11 | 0 | 0 | 0 | 0 | 31.2% | 16.20s | 6601624 |

## 按 bug 域拆分

| bug_domain | model_id | group | Trial 数 | PASS | 未修通（TIMEOUT） | 证据缺失 | 规则违规 | 限流待重试 | 基础设施异常 | 有效成功率 | PASS 中位耗时 | Token 中位数 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| env | gpt-5.5 | with_kdebug | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 100.0% | 37.43s | 12357 |
| env | gpt-5.5 | without_kdebug | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 100.0% | 37.20s | 12366 |
| env | qwen3.6-35b | with_kdebug | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 100.0% | 9.18s | 7430 |
| env | qwen3.6-35b | without_kdebug | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 100.0% | 7.86s | 4640 |
| mixed | gpt-5.5 | with_kdebug | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 66.7% | 277.75s | 66682 |
| mixed | gpt-5.5 | without_kdebug | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 66.7% | 212.74s | 56698 |
| mixed | qwen3.6-35b | with_kdebug | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0.0% |  | 11567509 |
| mixed | qwen3.6-35b | without_kdebug | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0.0% |  | 11244671 |
| rtl | glm-4.7 | with_kdebug | 18 | 0 | 6 | 0 | 0 | 12 | 0 | 0.0% |  | 0 |
| rtl | glm-4.7 | without_kdebug | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0.0% |  | 4251201 |
| rtl | gpt-5.5 | with_kdebug | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 70.0% | 240.16s | 182178 |
| rtl | gpt-5.5 | without_kdebug | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 60.0% | 142.34s | 242050 |
| rtl | qwen3.6-35b | with_kdebug | 10 | 4 | 6 | 0 | 0 | 0 | 0 | 40.0% | 25.66s | 5281314 |
| rtl | qwen3.6-35b | without_kdebug | 10 | 2 | 8 | 0 | 0 | 0 | 0 | 20.0% | 17.24s | 6645026 |

## 按 benchmark 层拆分

| benchmark_layer | model_id | group | Trial 数 | PASS | 未修通（TIMEOUT） | 证据缺失 | 规则违规 | 限流待重试 | 基础设施异常 | 有效成功率 | PASS 中位耗时 | Token 中位数 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fullchip | glm-4.7 | with_kdebug | 13 | 0 | 1 | 0 | 0 | 12 | 0 | 0.0% |  | 0 |
| fullchip | glm-4.7 | without_kdebug | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0.0% |  | 2471107 |
| fullchip | gpt-5.5 | with_kdebug | 9 | 5 | 4 | 0 | 0 | 0 | 0 | 55.6% | 240.16s | 66682 |
| fullchip | gpt-5.5 | without_kdebug | 9 | 4 | 5 | 0 | 0 | 0 | 0 | 44.4% | 277.18s | 295273 |
| fullchip | qwen3.6-35b | with_kdebug | 9 | 2 | 7 | 0 | 0 | 0 | 0 | 22.2% | 87.81s | 11422941 |
| fullchip | qwen3.6-35b | without_kdebug | 9 | 2 | 7 | 0 | 0 | 0 | 0 | 22.2% | 20.59s | 6634975 |
| generated_wrapper | glm-4.7 | with_kdebug | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0.0% |  | 5282960 |
| generated_wrapper | glm-4.7 | without_kdebug | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0.0% |  | 4731892 |
| generated_wrapper | gpt-5.5 | with_kdebug | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 100.0% | 199.31s | 155109 |
| generated_wrapper | gpt-5.5 | without_kdebug | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 100.0% | 118.51s | 103086 |
| generated_wrapper | qwen3.6-35b | with_kdebug | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 100.0% | 24.66s | 36770 |
| generated_wrapper | qwen3.6-35b | without_kdebug | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 50.0% | 16.20s | 6246088 |
| real_rtl_it | glm-4.7 | with_kdebug | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0.0% |  | 3743367 |
| real_rtl_it | glm-4.7 | without_kdebug | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0.0% |  | 4772098 |
| real_rtl_it | gpt-5.5 | with_kdebug | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 100.0% | 218.09s | 93960 |
| real_rtl_it | gpt-5.5 | without_kdebug | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 100.0% | 109.63s | 48134 |
| real_rtl_it | qwen3.6-35b | with_kdebug | 4 | 2 | 2 | 0 | 0 | 0 | 0 | 50.0% | 31.09s | 4544770 |
| real_rtl_it | qwen3.6-35b | without_kdebug | 4 | 1 | 3 | 0 | 0 | 0 | 0 | 25.0% | 18.28s | 6611675 |
| real_rtl_ut | gpt-5.5 | with_kdebug | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 100.0% | 37.43s | 17518 |
| real_rtl_ut | gpt-5.5 | without_kdebug | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 100.0% | 37.20s | 12366 |
| real_rtl_ut | qwen3.6-35b | with_kdebug | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 100.0% | 9.18s | 7430 |
| real_rtl_ut | qwen3.6-35b | without_kdebug | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 100.0% | 7.86s | 4640 |

## 逐 Case 结果

| Case | Bug 域 | 层级 | 子系统 | 模型 | 使用 kdebug | 不使用 kdebug |
|---|---|---|---|---|---|---|
| case_001 | rtl | generated_wrapper | axi | gpt-5.5 | 通过, 135.62s, iter=3, token=80041, repair=rtl_only, evidence=true | 通过, 22.34s, iter=1, token=17345, repair=rtl_only, evidence=false |
| case_001 | rtl | generated_wrapper | axi | glm-4.7 | 未修通（1 小时超时）, 3602.14s, iter=125, token=4076300, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3600.00s, iter=231, token=5900613, repair=no_effective_patch, evidence=false |
| case_001 | rtl | generated_wrapper | axi | qwen3.6-35b | 通过, 31.57s, iter=1, token=26388, repair=rtl_only, evidence=true | 通过, 16.20s, iter=1, token=20292, repair=rtl_only, evidence=false |
| case_002 | rtl | generated_wrapper | axi | gpt-5.5 | 通过, 262.99s, iter=8, token=230177, repair=rtl_only, evidence=true | 通过, 214.69s, iter=7, token=188827, repair=rtl_only, evidence=false |
| case_002 | rtl | generated_wrapper | axi | glm-4.7 | 未修通（1 小时超时）, 3604.00s, iter=246, token=6489620, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3609.09s, iter=111, token=3563171, repair=rtl_only, evidence=false |
| case_002 | rtl | generated_wrapper | axi | qwen3.6-35b | 通过, 17.74s, iter=2, token=47151, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3605.72s, iter=447, token=12471885, repair=no_effective_patch, evidence=false |
| case_003 | rtl | real_rtl_it | memory | gpt-5.5 | 通过, 34.10s, iter=2, token=42301, repair=rtl_only, evidence=true | 通过, 20.82s, iter=1, token=17338, repair=rtl_only, evidence=false |
| case_003 | rtl | real_rtl_it | memory | glm-4.7 | 未修通（1 小时超时）, 3606.00s, iter=117, token=3743367, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 6254.00s, iter=296, token=7762547, repair=no_effective_patch, evidence=False |
| case_003 | rtl | real_rtl_it | memory | qwen3.6-35b | 未修通（1 小时超时）, 3600.00s, iter=268, token=9038198, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3602.00s, iter=209, token=6655078, repair=no_effective_patch, evidence=false |
| case_004 | rtl | real_rtl_it | peripheral | gpt-5.5 | 通过, 320.55s, iter=19, token=527264, repair=rtl_only, evidence=true | 通过, 432.43s, iter=28, token=732701, repair=rtl_only, evidence=false |
| case_004 | rtl | real_rtl_it | peripheral | glm-4.7 | 未修通（1 小时超时）, 3600.78s, iter=83, token=2458603, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3600.36s, iter=177, token=4772098, repair=no_effective_patch, evidence=false |
| case_004 | rtl | real_rtl_it | peripheral | qwen3.6-35b | 通过, 19.75s, iter=1, token=20535, repair=rtl_only, evidence=true | 通过, 18.28s, iter=1, token=18116, repair=rtl_only, evidence=false |
| case_005 | rtl | real_rtl_it | peripheral | gpt-5.5 | 通过, 164.78s, iter=5, token=134179, repair=rtl_only, evidence=true | 通过, 69.98s, iter=2, token=43533, repair=rtl_only, evidence=false |
| case_005 | rtl | real_rtl_it | peripheral | glm-4.7 | 未修通（1 小时超时）, 3614.39s, iter=199, token=5144909, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3606.42s, iter=118, token=3730304, repair=rtl_only, evidence=false |
| case_005 | rtl | real_rtl_it | peripheral | qwen3.6-35b | 通过, 42.42s, iter=2, token=51343, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3600.00s, iter=220, token=6568272, repair=no_effective_patch, evidence=false |
| case_006 | rtl | fullchip | pipeline | gpt-5.5 | 通过, 2643.84s, iter=2, token=43121, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 9395.39s, iter=74, token=2130085, repair=rtl_only, evidence=False |
| case_006 | rtl | fullchip | pipeline | glm-4.7 | 未修通（1 小时超时）, 3601.00s, iter=56, token=1932818, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3599.77s, iter=76, token=2471107, repair=rtl_only, evidence=false |
| case_006 | rtl | fullchip | pipeline | qwen3.6-35b | 未修通（1 小时超时）, 3607.51s, iter=273, token=11422941, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3599.57s, iter=20, token=798059, repair=rtl_only, evidence=false |
| case_007 | rtl | fullchip | control | gpt-5.5 | 未修通（1 小时超时）, 3600.28s, iter=20, token=518764, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3603.45s, iter=17, token=442375, repair=rtl_only, evidence=false |
| case_007 | rtl | fullchip | control | glm-4.7 | 限流/接口异常，待重试, 124.87s, iter=0, token=0, repair=no_effective_patch, evidence=True | 缺失 |
| case_007 | rtl | fullchip | control | qwen3.6-35b | 未修通（1 小时超时）, 3607.79s, iter=278, token=11875500, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3601.63s, iter=243, token=9469595, repair=no_effective_patch, evidence=false |
| case_008 | rtl | fullchip | lsu_cache | gpt-5.5 | 未修通（1 小时超时）, 3600.04s, iter=27, token=816602, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3599.91s, iter=37, token=901373, repair=rtl_only, evidence=false |
| case_008 | rtl | fullchip | lsu_cache | qwen3.6-35b | 未修通（1 小时超时）, 3625.86s, iter=161, token=7263399, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3614.93s, iter=177, token=7735006, repair=rtl_only, evidence=false |
| case_009 | rtl | fullchip | branch_redirect | gpt-5.5 | 通过, 240.16s, iter=2, token=43597, repair=rtl_only, evidence=true | 通过, 278.16s, iter=2, token=38667, repair=rtl_only, evidence=false |
| case_009 | rtl | fullchip | branch_redirect | qwen3.6-35b | 未修通（1 小时超时）, 3602.66s, iter=404, token=18680689, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3608.20s, iter=260, token=10805985, repair=no_effective_patch, evidence=false |
| case_010 | rtl | fullchip | memory_subsystem | gpt-5.5 | 未修通（1 小时超时）, 3600.67s, iter=22, token=647723, repair=rtl_only, evidence=true | 未修通（1 小时超时）, 3687.99s, iter=11, token=295273, repair=rtl_only, evidence=false |
| case_010 | rtl | fullchip | memory_subsystem | qwen3.6-35b | 未修通（1 小时超时）, 3623.53s, iter=72, token=3299228, repair=rtl_only, evidence=True | 未修通（1 小时超时）, 3599.25s, iter=177, token=6634975, repair=rtl_only, evidence=false |
| case_011 | env | fullchip | difftest | gpt-5.5 | 通过, 56.94s, iter=2, token=12357, repair=env_only, evidence=true | 通过, 295.06s, iter=10, token=93270, repair=env_only, evidence=false |
| case_011 | env | fullchip | difftest | qwen3.6-35b | 通过, 169.82s, iter=5, token=42622, repair=env_only, evidence=true | 通过, 34.96s, iter=4, token=41545, repair=env_only, evidence=false |
| case_012 | env | real_rtl_ut | axi | gpt-5.5 | 通过, 37.43s, iter=2, token=17518, repair=env_only, evidence=true | 通过, 37.20s, iter=2, token=12366, repair=env_only, evidence=false |
| case_012 | env | real_rtl_ut | axi | qwen3.6-35b | 通过, 9.18s, iter=1, token=7430, repair=env_only, evidence=true | 通过, 7.86s, iter=1, token=4640, repair=env_only, evidence=false |
| case_013 | env | fullchip | build_cache | gpt-5.5 | 通过, 11.33s, iter=1, token=3224, repair=env_only, evidence=true | 通过, 8.70s, iter=1, token=2872, repair=env_only, evidence=false |
| case_013 | env | fullchip | build_cache | qwen3.6-35b | 通过, 5.79s, iter=1, token=3535, repair=env_only, evidence=true | 通过, 6.21s, iter=1, token=3258, repair=env_only, evidence=false |
| case_014 | mixed | real_rtl_it | memory | gpt-5.5 | 通过, 271.40s, iter=2, token=53741, repair=mixed, evidence=true | 通过, 149.27s, iter=2, token=52735, repair=mixed, evidence=false |
| case_014 | mixed | real_rtl_it | memory | qwen3.6-35b | 未修通（1 小时超时）, 3604.90s, iter=281, token=10714207, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3610.97s, iter=298, token=11244671, repair=mixed, evidence=false |
| case_015 | mixed | fullchip | branch_redirect | gpt-5.5 | 通过, 284.10s, iter=3, token=66682, repair=mixed, evidence=true | 通过, 276.20s, iter=3, token=56698, repair=mixed, evidence=false |
| case_015 | mixed | fullchip | branch_redirect | qwen3.6-35b | 未修通（1 小时超时）, 3600.49s, iter=281, token=11567509, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3599.48s, iter=467, token=17508359, repair=no_effective_patch, evidence=false |
| case_016 | mixed | fullchip | lsu_cache | gpt-5.5 | 未修通（1 小时超时）, 3630.05s, iter=23, token=769982, repair=mixed, evidence=True | 未修通（1 小时超时）, 3601.67s, iter=14, token=429534, repair=mixed, evidence=False |
| case_016 | mixed | fullchip | lsu_cache | qwen3.6-35b | 未修通（1 小时超时）, 3599.44s, iter=297, token=12379710, repair=no_effective_patch, evidence=true | 未修通（1 小时超时）, 3600.00s, iter=15, token=606529, repair=no_effective_patch, evidence=false |
