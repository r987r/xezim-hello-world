#!/usr/bin/env python3
"""Fetch immutable public RTL IP into ignored .tools/; never rebuild Xezim."""
import argparse
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]


def hydrate_submodules(out: Path, paths: list[str]) -> None:
    """Hydrate root-commit-pinned submodule gitlinks only when declared.

    No implicit optional repository checkout, silent tracking of latest, or
    global recursive fetch for unrelated IPs. Root commit pins every gitlink.
    """
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ValueError("submodule paths must be declared as a list")
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate pinned submodule path")
    for name in paths:
        path = Path(name)
        if name in ("", ".", "..") or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe pinned submodule path {name!r}")
    if not paths:
        return
    subprocess.run(['git', '-C', str(out), 'submodule', 'sync', '--recursive'],
                   check=True)
    subprocess.run(['git', '-C', str(out), 'submodule', 'update', '--init',
                    '--recursive', '--', *paths], check=True)
    status = subprocess.run(
        ['git', '-C', str(out), 'submodule', 'status', '--recursive', '--', *paths],
        capture_output=True, text=True, check=True).stdout.splitlines()
    if not status or any(not line or line[0] in "-+U" for line in status):
        raise ValueError("missing or changed pinned submodule gitlink")
    for name in paths:
        if not (out / name).is_dir() or not any((out / name).iterdir()):
            raise ValueError(f"missing checked-out pinned submodule {name}")


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
    hydrate_submodules(out, entry.get('submodules', []))
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
