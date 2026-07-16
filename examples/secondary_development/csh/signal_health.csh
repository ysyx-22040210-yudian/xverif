#!/usr/bin/env tcsh

set fsdb = ""
set signal = ""
set begin_time = ""
set end_time = ""
set out_dir = ""
set max_rows = 200
set min_changes = 1
set max_unknown = 0
set require_complete = false
set usage_rc = 2
set kdebug_override = ""
set json_python_override = ""
set json_helper_override = ""

while ( $#argv > 0 )
  switch ( "$argv[1]" )
    case "--fsdb":
      if ( $#argv < 2 ) goto usage_error
      set fsdb = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--signal":
      if ( $#argv < 2 ) goto usage_error
      set signal = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--begin":
    case "--start":
      if ( $#argv < 2 ) goto usage_error
      set begin_time = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--end":
    case "--stop":
      if ( $#argv < 2 ) goto usage_error
      set end_time = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--max-rows":
      if ( $#argv < 2 ) goto usage_error
      set max_rows = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--min-changes":
      if ( $#argv < 2 ) goto usage_error
      set min_changes = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--max-unknown":
      if ( $#argv < 2 ) goto usage_error
      set max_unknown = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--require-complete":
      set require_complete = true
      shift argv
      breaksw
    case "--kdebug-bin":
      if ( $#argv < 2 ) goto usage_error
      set kdebug_override = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--json-python":
      if ( $#argv < 2 ) goto usage_error
      set json_python_override = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--json-helper":
      if ( $#argv < 2 ) goto usage_error
      set json_helper_override = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "--out":
      if ( $#argv < 2 ) goto usage_error
      set out_dir = "$argv[2]"
      shift argv
      shift argv
      breaksw
    case "-h":
    case "--help":
      set usage_rc = 0
      goto usage_ok
    default:
      echo "ERROR: unknown argument: $argv[1]" >&2
      goto usage_error
  endsw
end

if ( "$fsdb" == "" || "$signal" == "" || "$begin_time" == "" || "$end_time" == "" || "$out_dir" == "" ) goto usage_error

echo "$max_rows" | grep -Eq '^[0-9]+$'
if ( $status != 0 ) goto numeric_error
echo "$min_changes" | grep -Eq '^[0-9]+$'
if ( $status != 0 ) goto numeric_error
echo "$max_unknown" | grep -Eq '^[0-9]+$'
if ( $status != 0 ) goto numeric_error

set script_dir = "$0:h"
set repo_tool = "$script_dir/../../../tools/kdebug"
if ( "$kdebug_override" != "" ) then
  set kdebug_bin = "$kdebug_override"
else if ( $?KDEBUG_BIN ) then
  set kdebug_bin = "$KDEBUG_BIN"
else
  set kdebug_bin = ""
  if ( $?KVERIF_HOME ) then
    if ( -x "$KVERIF_HOME/tools/kdebug" ) set kdebug_bin = "$KVERIF_HOME/tools/kdebug"
  endif
  if ( "$kdebug_bin" == "" && -x "$repo_tool" ) set kdebug_bin = "$repo_tool"
  if ( "$kdebug_bin" == "" ) set kdebug_bin = kdebug
endif

if ( "$json_python_override" != "" ) then
  set json_python = "$json_python_override"
else if ( $?KVERIF_JSON_PYTHON ) then
  set json_python = "$KVERIF_JSON_PYTHON"
else if ( $?PYTHON ) then
  set json_python = "$PYTHON"
else
  which python3 >& /dev/null
  if ( $status == 0 ) then
    set json_python = python3
  else
    set json_python = python
  endif
endif

set local_helper = "$script_dir/../json_response.py"
if ( "$json_helper_override" != "" ) then
  set json_helper = "$json_helper_override"
else if ( $?KVERIF_JSON_HELPER ) then
  set json_helper = "$KVERIF_JSON_HELPER"
else if ( -f "$local_helper" ) then
  set json_helper = "$local_helper"
else
  set json_helper = "$local_helper"
  if ( $?KVERIF_HOME ) then
    if ( -f "$KVERIF_HOME/examples/secondary_development/json_response.py" ) set json_helper = "$KVERIF_HOME/examples/secondary_development/json_response.py"
  endif
endif

set command_ok = 0
if ( -x "$kdebug_bin" ) set command_ok = 1
if ( $command_ok == 0 ) then
  which "$kdebug_bin" >& /dev/null
  if ( $status == 0 ) set command_ok = 1
endif
if ( $command_ok == 0 ) then
  echo "ERROR: kdebug is not executable: $kdebug_bin" >&2
  exit 2
endif

set command_ok = 0
if ( -x "$json_python" ) set command_ok = 1
if ( $command_ok == 0 ) then
  which "$json_python" >& /dev/null
  if ( $status == 0 ) set command_ok = 1
endif
if ( $command_ok == 0 ) then
  echo "ERROR: JSON Python is not executable: $json_python" >&2
  exit 2
endif
"$json_python" -c 'import json, sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >& /dev/null
if ( $status != 0 ) then
  echo "ERROR: JSON helper requires Python 3: $json_python" >&2
  exit 2
endif
if ( ! -f "$json_helper" ) then
  echo "ERROR: JSON helper is missing: $json_helper" >&2
  exit 2
endif

mkdir -p "$out_dir"
set response = "$out_dir/tool-response.json"
set report = "$out_dir/conclusion.json"

"$kdebug_bin" --json action signal.scan \
  --fsdb "$fsdb" --arg "signal=$signal" --arg "begin=$begin_time" --arg "end=$end_time" \
  --arg format=hex --max-rows "$max_rows" >! "$response"
set tool_rc = $status
if ( $tool_rc != 0 ) then
  echo "ERROR: kdebug failed with rc=$tool_rc; response: $response" >&2
  exit 1
endif

"$json_python" "$json_helper" check-ok "$response"
if ( $status != 0 ) exit 1
set stats = ( `"$json_python" "$json_helper" wave-stats "$response"` )
if ( $status != 0 || $#stats != 3 ) then
  echo "ERROR: cannot parse signal.scan summary" >&2
  exit 1
endif
set change_count = "$stats[1]"
set unknown_count = "$stats[2]"
set truncated = "$stats[3]"

set conclusion = HEALTHY
set reason = "signal activity satisfies all configured gates"
if ( "$require_complete" == "true" && "$truncated" == "true" ) then
  set conclusion = INCOMPLETE
  set reason = "signal.scan was truncated, so the complete window was not evaluated"
else if ( $unknown_count > $max_unknown ) then
  set conclusion = UNKNOWN_VALUES
  set reason = "unknown_count exceeds the configured maximum"
else if ( $change_count < $min_changes ) then
  set conclusion = INACTIVE
  set reason = "change_count is below the configured minimum"
endif

"$json_python" "$json_helper" signal-health-report \
  --output "$report" --language csh --signal "$signal" --response "$response" \
  --change-count "$change_count" --unknown-count "$unknown_count" --truncated "$truncated" \
  --min-changes "$min_changes" --max-unknown "$max_unknown" \
  --require-complete "$require_complete" --conclusion "$conclusion" --reason "$reason"
if ( $status != 0 ) exit 1

echo "signal health: $conclusion ($reason)"
echo "report: $report"
if ( "$conclusion" != "HEALTHY" ) exit 3
exit 0

numeric_error:
echo "ERROR: numeric options must be non-negative integers" >&2
exit 2

usage_error:
echo "ERROR: --fsdb, --signal, --begin, --end and --out are required" >&2
set usage_rc = 2
goto usage_print
usage_ok:
set usage_rc = 0
usage_print:
cat << EOF
Usage: signal_health.csh --fsdb FILE --signal NAME --begin TIME --end TIME
                         [--max-rows N] [--min-changes N]
                         [--max-unknown N] [--require-complete]
                         [--kdebug-bin CMD] [--json-python CMD]
                         [--json-helper FILE] --out DIR

The script invokes kdebug, parses signal.scan JSON, and emits conclusion.json.
Resolution: explicit option, environment, KVERIF_HOME/tools, repository, PATH.
EOF
exit $usage_rc
