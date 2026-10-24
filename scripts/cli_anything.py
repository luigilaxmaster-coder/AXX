#!/usr/bin/env python3
"""Inspect UIA capabilities or emit a typed proposal for Axx's command API.
No standalone execution/approval path. See docs/COMMAND-EXTENSIONS.md.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.actions.cli_anything_engine import ENGINE
from backend.actions.windows_automation import list_windows


def main():
    parser = argparse.ArgumentParser(description='Descubrimiento UIA y propuestas tipadas de Axx')
    parser.add_argument('--json', action='store_true')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    sub.add_parser('active')
    scan = sub.add_parser('scan')
    scan.add_argument('target', help='HWND hexadecimal, PID único o título exacto')
    catalog = sub.add_parser('commands')
    catalog.add_argument('target', help='HWND hexadecimal, PID único o título exacto')
    prepare = sub.add_parser('prepare')
    prepare.add_argument('target')
    prepare.add_argument('command', choices=['inspect', 'read', 'focus', 'type'])
    prepare.add_argument('--args', default='{}', help='Objeto JSON; type requiere control_id y text')
    args = parser.parse_args()
    try:
        if args.action == 'list':
            result = list_windows()
        elif args.action == 'commands':
            result = ENGINE.list_commands(args.target)
        elif args.action == 'prepare':
            result = ENGINE.propose(args.target, args.command, json.loads(args.args))
        else:
            app = ENGINE.resolve(None if args.action == 'active' else args.target)
            if not args.json:
                print(app.generate_cli_help())
                return
            result = app.to_dict()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
