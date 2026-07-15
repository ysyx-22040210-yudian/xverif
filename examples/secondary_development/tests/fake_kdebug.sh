#!/usr/bin/env bash
set -euo pipefail

args=" $* "
if [[ "$args" == *" signal.scan "* ]]; then
  printf '%s\n' '{"api_version":"kdebug.v1","action":"signal.scan","ok":true,"summary":{"change_count":4,"unknown_count":0,"truncated":false},"data":{"changes":[]}}'
elif [[ "$args" == *" trace-driver "* ]]; then
  printf '%s\n' '{"api_version":"kdebug.v1","action":"trace.driver","ok":true,"summary":{"edge_count":2,"status":"ok"},"data":{"dependency_edges":[]}}'
elif [[ "$args" == *" trace.load "* ]]; then
  printf '%s\n' '{"api_version":"kdebug.v1","action":"trace.load","ok":true,"summary":{"edge_count":1,"status":"ok"},"data":{"dependency_edges":[]}}'
elif [[ "$args" == *" trace-graph "* ]]; then
  printf '%s\n' '{"api_version":"kdebug.v1","action":"trace.graph","ok":true,"summary":{"node_count":3,"edge_count":2,"truncated":false},"data":{"dependency_edges":[]}}'
else
  printf '%s\n' '{"api_version":"kdebug.v1","ok":true,"summary":{"fake":true},"data":{"rows":[]}}'
fi
