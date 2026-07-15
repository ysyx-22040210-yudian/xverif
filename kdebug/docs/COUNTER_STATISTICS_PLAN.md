# counter.statistics implementation plan

## Goals

- Change multi-bit `signal.statistics` clock-sampled min/max reporting to use
  exact bit-string value objects instead of integer-only fields.
- Add a waveform-only `counter.statistics` action for clock-sampled counter
  statistics over an explicit time window.
- Keep the public action catalog, schemas, examples, docs, MCP smoke list, and
  tests synchronized.

## License and sandbox rule

Any operation that needs NPI, Verdi, FSDB access, waveform simulation, or a
license must be run outside the sandbox, as requested by the user. This includes
building or regenerating waveform fixtures and running real waveform regression
commands. Schema-only and non-license contract checks can run normally.

## Public API

`counter.statistics` is a stable waveform action.

Required args:

- `clock`: clock signal path.
- `time_range`: object with `begin`/`end` or `from`/`to`; values may be absolute
  time specs or cursor specs such as `@mark`, `@mark+10ns`, or cycle offsets.
- `vld`: either a signal path string, or an object with `expr` and `signals`.
- `cnt`: either a signal path string, or a restricted concat string such as
  `{top.hi,top.lo}`.

Optional args:

- `sampling`: `posedge` by default; `negedge` selects negative edges.
- `max_samples`: default `1000000`.

Output:

- `sample_count`: clock edges visited.
- `valid_count`: samples where `vld` is true and `cnt` is known.
- `valid_false_count`: samples where `vld` is false.
- `unknown_count`: samples skipped because `vld` or `cnt` is unknown.
- `min_value` / `max_value`: exact decimal string for the sampled counter.
- `average_value`: decimal average across valid samples.
- `min_count` / `max_count`: occurrence counts.
- `min_first_time` / `max_first_time`: first occurrence times.
- `truncated`: true when `max_samples` stops scanning.

`cnt` concat is deliberately narrow: comma-separated signal paths only, no
literals, repeat syntax, nested concat, slices, arithmetic, or expressions. The
combined bit width must be at most 64 bits.

## Implementation outline

1. Add exact bit-string helpers near waveform signal analysis code:
   normalize binary values, compare same-width bit strings, convert up to 64
   bits to `uint64_t`, and render exact value objects.
2. Update `signal.statistics` clock mode to keep `first/final/min/max` as
   value objects based on normalized binary strings.
3. Add `ai_counter_statistics()` and route it through waveform query dispatch,
   engine forwarding, runtime action registry, and waveform action registry.
4. Add action-specific schemas and basic examples.
5. Update action inventory, README/help, payload compact docs, JSON API docs,
   and MCP smoke action lists.

## Tests

- Add a targeted standalone waveform test for `counter.statistics`.
- Cover signal-path `vld`, expression `vld`, concat `cnt`, cursor time windows,
  min/max/average/count/first-time fields, X/Z behavior, malformed concat, and
  over-64-bit rejection.
- Update existing waveform statistics coverage to assert multi-bit
  `signal.statistics` value-object min/max.
- Run schema and contract checks, then run license-requiring waveform tests
  outside the sandbox.
