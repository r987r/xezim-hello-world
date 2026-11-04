#!/usr/bin/env python3
"""Emit deterministic DMA-only SRAM preload image and expected-data manifest."""
import argparse
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dv.common.dma_vectors import build_dma_vector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"config/soc.yaml")
    parser.add_argument("--subsystem", default="compute0")
    parser.add_argument("--destination", default="memory0.ddr0")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--length", type=int, default=64)
    parser.add_argument("--out", type=Path, default=ROOT/".tools/dma-vectors")
    args = parser.parse_args()
    case = build_dma_vector(yaml.safe_load(args.config.read_text()),
                            subsystem=args.subsystem, destination=args.destination,
                            count=args.count, length=args.length)
    case.write(args.out)
    print(f'DMA-ONLY VECTOR: {args.count} descriptors; '
          f'head={case.manifest["descriptor_head"]:#x}; files={args.out}')


if __name__ == "__main__":
    main()
