"""Prepare only pinned upstream PULP iDMA AXI RTL for a real DMA test.

Use the upstream iDMA/MARIO and PeakRDL generators, never copied backend or
register implementations. Do not resolve a second incompatible AXI Bender
dependency graph; the same FlooNoC-locked AXI package serves the DUT.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT/'.tools/pulp_idma'
GEN = VENDOR/'target/rtl'


def generate():
    import ip_fetch
    ip_fetch.fetch('pulp_idma')
    targets = [
        GEN/'idma_transport_layer_rw_axi.sv',
        GEN/'idma_legalizer_rw_axi.sv',
        GEN/'idma_backend_rw_axi.sv',
        GEN/'idma_desc64_reg_top.sv',
        GEN/'include/idma/compute.svh',
    ]
    command = ['make', '-f', str(VENDOR/'idma.mk'),
               f'IDMA_ROOT={VENDOR}', f'PYTHON={sys.executable}', 'PEAKRDL=peakrdl',
               *map(str,targets)]
    # Upstream's default PEAKRDL invokes `uv run --locked`; our CI pins
    # and installs the same PeakRDL tools directly in the host Python env.
    subprocess.run(command, cwd=ROOT, check=True)
    for target in targets:
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f'upstream iDMA generation missing: {target}')
    # Explicit, ordered list from the pinned upstream Bender.yml's rtl source
    # levels, limited to modules used by the AXI->AXI backend and desc64 FE.
    names = [
        'src/idma_pkg.sv', 'src/idma_float_pkg.sv',
        'src/backend/idma_axi_read.sv',
        'src/backend/idma_axi_write.sv',
        'src/backend/idma_channel_coupler.sv',
        'src/backend/idma_dataflow_element.sv',
        'src/backend/idma_error_handler.sv',
        'src/backend/idma_legalizer_page_splitter.sv',
        'src/backend/idma_legalizer_pow2_splitter.sv',
        'src/backend/idma_otf_transpose.sv',
        'src/backend/idma_otf_mxquant.sv',
        'src/backend/idma_otf_mxdequant.sv',
        'src/backend/idma_otf_compute.sv',
        'target/rtl/idma_transport_layer_rw_axi.sv',
        'target/rtl/idma_legalizer_rw_axi.sv',
        'target/rtl/idma_backend_rw_axi.sv',
        'target/rtl/idma_desc64_reg_pkg.sv',
        'target/rtl/idma_desc64_addrmap_pkg.sv',
        'target/rtl/idma_desc64_reg_top.sv',
        'src/frontend/desc64/idma_desc64_ar_gen.sv',
        'src/frontend/desc64/idma_desc64_ar_gen_prefetch.sv',
        'src/frontend/desc64/idma_desc64_reader.sv',
        'src/frontend/desc64/idma_desc64_reader_gater.sv',
        'src/frontend/desc64/idma_desc64_reshaper.sv',
        'src/frontend/desc64/idma_desc64_reg_wrapper.sv',
        'src/frontend/desc64/idma_desc64_top.sv',
    ]
    sources = [str((VENDOR/name).resolve()) for name in names]
    missing = [p for p in sources if not Path(p).is_file()]
    if missing:
        raise RuntimeError(f'missing generated iDMA RTL: {missing}')
    return sources, [str(VENDOR/'src/include'), str(GEN/'include')]


if __name__ == '__main__':
    sources, includes = generate()
    print(f'PASS pinned PULP iDMA: {len(sources)} RTL sources; {includes}')
