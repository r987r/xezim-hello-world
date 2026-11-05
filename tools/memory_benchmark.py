#!/usr/bin/env python3
"""Small synthetic benchmark baseline for shared memory INIT/CHECK contracts.

This does NOT benchmark Verilator, RTL SRAM, DDR4, AXI, host DPI, or CPU.
Providers must be validated independently with real AXI before replacing
this synthetic store for an actual simulation-speedup benchmark.
"""
import argparse
import asyncio
import json
from pathlib import Path
from statistics import median

from tools.memory_plan import VirtualRegion
from tools.memory_service import MemoryService, Pattern


class SyntheticMemoryProvider:
    """Same reference bytes through both access methods; no simulated bus."""
    validated_backdoor = True
    frontdoor_available = True

    def __init__(self, base, capacity):
        self.base = base
        self.data = bytearray(capacity)

    async def backdoor_write(self, phys, data):
        start = phys - self.base
        self.data[start:start + len(data)] = data

    async def backdoor_read(self, phys, length):
        start = phys - self.base
        return bytes(self.data[start:start + length])

    async def frontdoor_write(self, phys, data):
        await self.backdoor_write(phys, data)

    async def frontdoor_read(self, phys, length):
        return await self.backdoor_read(phys, length)


async def run_trial(size: int, mode: str, *, seed=1234, chunk_bytes=4096):
    base = 0x140000100
    region = VirtualRegion("memory0.ddr0", "ddr", base, size + 4096, False)
    service = MemoryService({region.name: region}, chunk_bytes=chunk_bytes)
    service.register(region.name, SyntheticMemoryProvider(base, region.capacity))
    allocation = service.allocate(region.name, size, 64,
                                  owner="benchmark", phase="run")
    recipe = Pattern("address_xor", seed)
    init = await service.initialize(allocation, recipe, policy=mode)
    check = await service.check(allocation, recipe, policy=mode)
    service.release(allocation, consumers_quiesced=True)
    return {
        "source": "synthetic_bytes_not_rtl",
        "size_bytes": size, "policy": mode,
        "seed": seed, "init_method": init.method,
        "check_method": check.method,
        "init_wall_ns": init.wall_ns, "check_wall_ns": check.wall_ns,
        "total_wall_ns": init.wall_ns + check.wall_ns,
        "simulated_cycles": None, "axi_transactions": None,
        "note": "Only checks the benchmark harness; not a measured RTL speedup",
    }


async def sweep(sizes, policies, repeats=3):
    if not isinstance(repeats, int) or repeats < 1:
        raise ValueError("repeat count must be positive")
    all_runs = []
    summary = []
    for size in sizes:
        if not isinstance(size, int) or size <= 0 or size > 1 << 22:
            raise ValueError("synthetic benchmark sizes must be 1..4 MiB")
        for policy in policies:
            if policy not in ("strict", "hybrid", "fast"):
                raise ValueError(f"invalid benchmark policy {policy}")
            trials = [await run_trial(size, policy) for _ in range(repeats)]
            all_runs.extend(trials)
            summary.append({
                "size_bytes": size, "policy": policy, "repeats": repeats,
                "median_init_ns": int(median(t["init_wall_ns"] for t in trials)),
                "median_check_ns": int(median(t["check_wall_ns"] for t in trials)),
                "median_total_ns": int(median(t["total_wall_ns"] for t in trials)),
                "source": "synthetic_bytes_not_rtl",
            })
    baseline = {r["size_bytes"]: r["median_total_ns"] for r in summary
                if r["policy"] == "strict"}
    for entry in summary:
        ref = baseline.get(entry["size_bytes"])
        entry["relative_to_strict"] = (
            round(ref / entry["median_total_ns"], 3)
            if ref is not None and entry["median_total_ns"] > 0 else None)
    return {"schema_version": 1, "source": "synthetic_bytes_not_rtl",
            "runs": all_runs, "summary": summary}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", type=int, nargs="+", default=[64, 4096, 65536])
    p.add_argument("--policies", nargs="+", default=["strict", "hybrid", "fast"])
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    result = asyncio.run(sweep(args.sizes, args.policies, args.repeats))
    data = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data)
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
