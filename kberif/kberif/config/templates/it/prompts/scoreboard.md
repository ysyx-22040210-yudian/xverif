总结这个 IP Test 环境的 Scoreboard Structure。

重点关注：

1. scoreboard/checker 名称、expected path、actual path、compare point。
2. compare key、ordering assumption、out-of-order compare。
3. pending/expected/actual queue 或 table，reset 行为。
4. mismatch 报错格式、RM/monitor 连接和 debug 入口。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

输出要求：

- 不要编造项目名、模块名、目录名、命令、信号、类、testcase 或目录结构。
- 所有具体事实都必须能从当前项目文件中找到 evidence。
- 如果只能从目录或命名推断，confidence 只能是 low。
- 如果信息不明确，把缺失项写入 unknowns，不要用经验补全。
- summary 应该短而明确，概括该 topic 的结论；更完整的结构、路径、条件、验证影响和 debug 信息写入 detail markdown。
- key_items 只保留 card 中最关键的少量摘要点，每项使用 one_line 和 evidence。
- detail markdown 应展开结构路径、条件、验证影响、debug 提示、关联 topic、unknowns 和 evidence。
