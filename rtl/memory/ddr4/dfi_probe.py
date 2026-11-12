"""Read-only measured DDR4 DFI/BankModel event stream.

The controller and DFI logic are actual generated LiteDRAM RTL. PHY and
storage are upstream behavioral SDRAMPHYModel/BankModel. No physical DDR4
device, pad, training, analog delays, or full-chip NoC is modeled here.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

try:
    from .dfi_probe_contract import PHASES, BANKS, DFI_FIELDS, BANK_FIELDS
except ImportError:
    from dfi_probe_contract import PHASES, BANKS, DFI_FIELDS, BANK_FIELDS


class DFIProbe:
    def __init__(self, directory: Path, *, scope='standalone_litedram_dfi_sim'):
        self.directory = Path(directory)
        self.events_path = self.directory / "ddr4_dfi_events.jsonl"
        self.summary_path = self.directory / "ddr4_dfi_summary.json"
        self.file = self.events_path.open("w", encoding="utf-8", buffering=1)
        self.counters = Counter()
        self.samples = 0
        self.last_time_ps = None
        self.closed = False
        self.scope = scope
        self.file.write(json.dumps({"kind": "probe_start",
                                    "scope": scope,
                                    "physical_phy": "not_modeled",
                                    "physical_dram": "not_modeled"}) + "\n")

    def record(self, time_ps: int, phases: list[dict], banks: list[dict],
               phase_name: str, period_ps: int):
        if self.closed:
            raise AssertionError("DFI probe was stopped mid-simulation")
        if type(time_ps) is not int or time_ps < 0:
            raise AssertionError("invalid DFI probe timestamp")
        if self.last_time_ps is not None and time_ps - self.last_time_ps != period_ps:
            raise AssertionError("DFI probe missed one or more clock cycles")
        if len(phases) != PHASES or len(banks) != BANKS:
            raise AssertionError("incomplete generated DFI/BankModel probe")
        self.samples += 1
        self.last_time_ps = time_ps

        def emit(kind: str, **fields):
            self.counters[kind] += 1
            self.file.write(json.dumps({
                "kind": kind, "time_ps": time_ps, "cycle": self.samples,
                "test_phase": phase_name, **fields
            }, sort_keys=True, separators=(",", ":")) + "\n")

        for i, p in enumerate(phases):
            if not p["cs_n"]:
                # Classic DFI ACT = !RAS_N && CAS_N && WE_N.
                # MRS = !RAS_N && !CAS_N && !WE_N; decode first, since
                # an ACT_N alias may be low on other commands in sim PHYs.
                classic_act = (not p["ras_n"] and p["cas_n"] and p["we_n"])
                if not p["ras_n"] and not p["cas_n"] and not p["we_n"]:
                    emit("dfi_mrs", dfi_phase=i, bank=p["bank"],
                         address=p["address"], command="MRS")
                elif not p["act_n"] or classic_act:
                    emit("dfi_activate", dfi_phase=i, bank=p["bank"],
                         address=p["address"],
                         decode="ddr4_act_n" if not p["act_n"] else "litedram_classic_dfi")
                elif p["ras_n"] and not p["cas_n"]:
                    operation = "dfi_write" if not p["we_n"] else "dfi_read"
                    emit(operation, dfi_phase=i, bank=p["bank"],
                         address=p["address"])
                elif not p["ras_n"] and p["cas_n"] and not p["we_n"]:
                    emit("dfi_precharge", dfi_phase=i, bank=p["bank"])
                elif not p["ras_n"] and not p["cas_n"] and p["we_n"]:
                    emit("dfi_refresh", dfi_phase=i)
            for signal, kind in (
                ("rddata_en", "dfi_rddata_en"),
                ("rddata_valid", "dfi_rddata_valid"),
                ("wrdata_en", "dfi_wrdata_en"),
            ):
                if p[signal]:
                    emit(kind, dfi_phase=i)
        for i, b in enumerate(banks):
            if b["read"]:
                emit("bankmodel_read", bank=i)
            if b["write_port_we"]:
                # Actual simulation-model storage write-enable, not AXI B.
                emit("bankmodel_storage_write", bank=i,
                     enabled_bytes=int(b["write_port_we"]).bit_count())
        if self.samples % 10000 == 0:
            emit("probe_heartbeat")

    def assert_alive(self, task):
        if self.closed or self.samples < 1 or task.done():
            if task.done():
                task.result()
            raise AssertionError("DFI probe not active for the full simulation")

    def finish(self, status: str, error: str | None = None):
        if self.closed:
            raise AssertionError("DFI probe finalized twice")
        self.file.write(json.dumps({
            "kind": "probe_end", "status": status, "error": error,
            "sampled_cycles": self.samples
        }) + "\n")
        self.file.close()
        self.closed = True
        result = {"status": status, "error": error, "sampled_cycles": self.samples,
                  "period_source": "configured_and_observed_standalone_clk",
                  "counters": dict(self.counters),
                  "models": {
                      "controller": "generated LiteDRAM RTL",
                      "dfi_phy": "SDRAMPHYModel (behavioral)",
                      "dram_storage": "BankModel dense memory (behavioral)",
                      "physical_phy": "not_modeled",
                      "physical_dram": "not_modeled",
                      "full_chip": "connected" if self.scope=="fullchip_litedram_dfi_sim" else "not_connected",
                  }}
        self.summary_path.write_text(json.dumps(result, indent=2) + "\n")
        return result


def get_internal_pins(dut, *, fullchip_aliases=False):
    """Read exactly the validated 72 DFI/BankModel pins, never storage."""
    phases=[]
    for i in range(PHASES):
        phases.append({
            name:int(getattr(
                dut,
                f"dfi_obs_p{i}_{name}" if fullchip_aliases else
                f"soc_ddrphy_dfi_p{i}_{name}"
            ).value)
            for name in DFI_FIELDS
        })
    banks=[]
    for i in range(BANKS):
        banks.append({
            name:int(getattr(
                dut,
                f"dfi_obs_bank{i}_{name}" if fullchip_aliases else
                f"soc_ddrphy_bankmodel{i}_{name}"
            ).value)
            for name in BANK_FIELDS
        })
    return phases,banks


async def observe_dfi(dut, observer: DFIProbe, axi_observer, period_ps: int,
                      *, pins_dut=None, fullchip_aliases=False):
    from cocotb.triggers import RisingEdge, ReadOnly
    from cocotb.utils import get_sim_time
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        # Cocotb handles can be falsey even when valid; never use `or`.
        phases,banks=get_internal_pins(pins_dut if pins_dut is not None else dut,
                                      fullchip_aliases=fullchip_aliases)
        observer.record(int(get_sim_time(units="ps")),phases,banks,
                        axi_observer.phase,period_ps)
