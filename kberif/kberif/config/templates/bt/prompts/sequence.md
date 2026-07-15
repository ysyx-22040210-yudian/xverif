总结这个 Block Test 环境的 Block Sequence / Stimulus Structure。

重点关注：

1. base/derived/directed/random/error/corner/stress sequence。
2. sequence item、字段、rand constraint、knob/config。
3. sequence 启动点、target sequencer、driver 连接、transaction 发送到 DUT 的路径。
4. virtual sequence、多 agent 协同、scoreboard/checker/RM 关系和扩展点。

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
