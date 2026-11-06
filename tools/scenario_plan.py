#!/usr/bin/env python3
"""Resolve a versioned SoC scenario spec to deterministic intent-only JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv.common.scenario import canonical_json, resolve_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True, type=Path,
                        help='versioned scenario authoring JSON file')
    parser.add_argument('--soc', type=Path, default=ROOT / 'config' / 'soc.yaml')
    parser.add_argument('--out', required=True, type=Path,
                        help='output scenario-plan.json path (intent only)')
    parser.add_argument('--seed', type=int, default=None,
                        help='optional explicit replay seed override')
    parser.add_argument('--source-revision', default=None,
                        help='optional exact tested full Git commit SHA')
    args = parser.parse_args(argv)
    try:
        spec = json.loads(args.scenario.read_text(encoding='utf-8'))
        cfg = yaml.safe_load(args.soc.read_text(encoding='utf-8'))
        if args.seed is not None:
            spec['seed'] = args.seed
        plan = resolve_scenario(spec, cfg, source_revision=args.source_revision)
        rendered = canonical_json(plan)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(f'invalid scenario: {exc}')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding='ascii')
    print(f"SCENARIO PLAN: {args.out} ({len(plan['actions'])} actions; intent_only; no RTL proof)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
