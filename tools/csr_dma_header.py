#!/usr/bin/env python3
"""Generate *software-only* C header from the existing DMA shim RDL.

Never export or replace RTL for PULP iDMA or our APB staging shim.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from systemrdl import RDLCompiler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "csr/rdl/soc_dma_shim.rdl"
HEADER = ROOT / "sw/generated/soc_dma_shim_regs.h"
CATALOG = ROOT / "csr/generated/soc_dma_shim.json"
EXPECTED = {"head_lo":0, "head_hi":4, "command":8, "status":12}

def compile_contract(source: Path):
    c = RDLCompiler()
    c.compile_file(str(source))
    root = c.elaborate(top_def_name="soc_dma_shim")
    rows = []
    for reg in root.top.registers(unroll=True):
        fields=[]
        for f in reg.fields():
            mask=((1<<(int(f.msb)-int(f.lsb)+1))-1)<<int(f.lsb)
            fields.append({"name":f.inst_name, "lsb":int(f.lsb), "msb":int(f.msb),
                           "mask":mask,"access":str(f.get_property("sw")).split(".")[-1].lower()})
        rows.append({"name":reg.inst_name,"offset":reg.absolute_address,
                     "width_bits":int(reg.get_property("regwidth")), "fields":fields})
    if {r["name"]:r["offset"] for r in rows} != EXPECTED:
        raise ValueError("DMA shim CSR offset ABI mismatch")
    if any(r["width_bits"]!=32 for r in rows):
        raise ValueError("DMA shim requires 32-bit registers")
    masks={(r["name"],f["name"]):f["mask"] for r in rows for f in r["fields"]}
    expected_masks={("command","submit"):1,("command","irq_ack"):2,
                    ("status","apb_busy"):1,("status","irq"):2,
                    ("status","apb_error"):4,("status","raw_irq"):8}
    for key,value in expected_masks.items():
        if masks.get(key)!=value:
            raise ValueError(f"DMA shim bit-level ABI mismatch: {key}")
    return rows

def render(rows):
    result=["/* GENERATED from csr/rdl/soc_dma_shim.rdl. Never edit by hand. */",
            "#ifndef SOC_DMA_SHIM_REGS_H", "#define SOC_DMA_SHIM_REGS_H",
            "#include <stdint.h>", ""]
    for r in rows:
        stem="SOC_DMA_"+r["name"].upper()
        result.append(f"#define {stem}_OFFSET UINT32_C(0x{r['offset']:02x})")
        for f in r["fields"]:
            result.append(f"#define {stem}_{f['name'].upper()}_SHIFT {f['lsb']}u")
            result.append(f"#define {stem}_{f['name'].upper()}_MASK UINT32_C(0x{f['mask']:08x})")
    result.extend(["","#endif /* SOC_DMA_SHIM_REGS_H */",""])
    return "\n".join(result)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--check",action="store_true")
    args=p.parse_args()
    rows=compile_contract(SOURCE)
    contents={
        HEADER:render(rows),
        CATALOG:json.dumps({"schema_version":1,"source":"csr/rdl/soc_dma_shim.rdl",
            "rtl_owner":"rtl/adapters/soc_dma_regs.sv","rtl_replaced":False,
            "registers":rows},sort_keys=True,indent=2)+"\n",
    }
    if args.check:
        for path,content in contents.items():
            if not path.is_file() or path.read_text()!=content:
                raise SystemExit(f"Stale generated CSR artifact: {path}")
        print("PASS: software-only DMA shim RDL ABI / generated C header exact")
    else:
        for path,content in contents.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content)
        print("Generated software-only DMA CSR header + catalog")

if __name__=="__main__":
    main()
