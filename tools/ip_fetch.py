#!/usr/bin/env python3
"""Fetch immutable public RTL IP into ignored .tools/; never rebuild Xezim."""
import argparse
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]


def fetch(name: str) -> Path:
    entry = yaml.safe_load((ROOT / 'config/ip.lock.yaml').read_text())['third_party'][name]
    if 'commit' not in entry:
        raise ValueError(f'IP {name} has no immutable commit pin')
    out = ROOT / '.tools' / name
    out.parent.mkdir(exist_ok=True)
    if not (out / '.git').is_dir():
        subprocess.run(['git','init','-q',str(out)],check=True)
        subprocess.run(['git','-C',str(out),'remote','add','origin',entry['git']],check=True)
    old = subprocess.run(['git','-C',str(out),'rev-parse','HEAD'],capture_output=True,text=True)
    if old.returncode != 0 or old.stdout.strip() != entry['commit']:
        subprocess.run(['git','-C',str(out),'fetch','-q','--depth','1','origin',entry['commit']],check=True)
        subprocess.run(['git','-C',str(out),'checkout','-q','--detach',entry['commit']],check=True)
    for relative in entry.get('modules', []):
        if not (out / relative).is_file():
            raise ValueError(f'{name}: missing upstream source {relative}')
    print(f'{name} @ {entry["commit"][:12]}')
    return out


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('names',nargs='+')
    args=cli.parse_args()
    for name in args.names: fetch(name)
