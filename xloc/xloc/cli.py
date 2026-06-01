import argparse
import sys

from .resolver import cmd_resolve, cmd_context
from .stats import cmd_stats
from .annotate import cmd_annotate


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='xloc',
        description='LLM-friendly UVM source-location mapper'
    )
    sub = parser.add_subparsers(dest='command')

    # resolve
    p_resolve = sub.add_parser('resolve', help='resolve a loc_id to file + line')
    p_resolve.add_argument('loc_id', help='loc_id to resolve (e.g. L_00000001)')
    p_resolve.add_argument('--map', dest='map_path',
                           required=True,
                           help='path to sidecar JSONL map file')

    # context
    p_ctx = sub.add_parser('context', help='resolve a loc_id and show surrounding source')
    p_ctx.add_argument('loc_id', help='loc_id to resolve')
    p_ctx.add_argument('--map', dest='map_path',
                        required=True,
                        help='path to sidecar JSONL map file')
    p_ctx.add_argument('--before', type=int, default=20,
                        help='lines before target (default: 20)')
    p_ctx.add_argument('--after', type=int, default=20,
                        help='lines after target (default: 20)')

    # stats
    p_stats = sub.add_parser('stats', help='count loc_id frequency in a log')
    p_stats.add_argument('log', help='path to simulation log')
    p_stats.add_argument('--map', dest='map_path',
                          help='path to sidecar JSONL map file')
    p_stats.add_argument('--top', type=int, default=20,
                          help='show top N locations (default: 20)')

    # annotate
    p_ann = sub.add_parser('annotate', help='insert location hints into a log')
    p_ann.add_argument('log', help='path to simulation log')
    p_ann.add_argument('--map', dest='map_path',
                        help='path to sidecar JSONL map file')

    args = parser.parse_args()

    if args.command == 'resolve':
        cmd_resolve(args.loc_id, args.map_path)
    elif args.command == 'context':
        cmd_context(args.loc_id, args.map_path, args.before, args.after)
    elif args.command == 'stats':
        cmd_stats(args.log, args.map_path, args.top)
    elif args.command == 'annotate':
        cmd_annotate(args.log, args.map_path)
    else:
        parser.print_help()
        sys.exit(1)
