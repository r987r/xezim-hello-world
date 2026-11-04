"""Continuous, independent, read-only AXI/Wishbone observer for isolated DDR4.

Starts before the first simulation clock and remains active through teardown.
Never drives DUT inputs or supplies AXI responses. This complements, rather
than replaces, cocotbext-axi's protocol-aware request/response monitors.

A full line-buffered JSONL stream records *every accepted handshake* with
bounded storage (overflow FAILS CLOSED), periodic heartbeat and test phases.
A separate summary enables CI to reject partial/disabled monitoring.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

PHASES = ("pre_init", "initialization", "traffic", "post_traffic")
CHANNELS = ("aw", "w", "b", "ar", "r")
PAYLOAD = {
    "aw": ("addr", "id", "len", "size", "burst"),
    "w": ("data", "strb", "last"),
    "b": ("id", "resp"),
    "ar": ("addr", "id", "len", "size", "burst"),
    "r": ("data", "id", "resp", "last"),
}


class TrafficObserver:
    def __init__(self, directory: Path, max_events: int = 50000,
                 heartbeat_cycles: int = 10000):
        if type(max_events) is not int or max_events < 10:
            raise ValueError("max_events must be at least 10")
        if type(heartbeat_cycles) is not int or heartbeat_cycles <= 0:
            raise ValueError("heartbeat interval must be positive")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events_path = self.directory / "ddr4_traffic_events.jsonl"
        self.summary_path = self.directory / "ddr4_traffic_summary.json"
        self.log = self.events_path.open("w", encoding="utf-8", buffering=1)
        self.max_events = max_events
        self.heartbeat_cycles = heartbeat_cycles
        self.phase = PHASES[0]
        self.phase_cycles = Counter({p: 0 for p in PHASES})
        self.channels = Counter({c: 0 for c in CHANNELS})
        self.wishbone = Counter()
        self.rlast_count = 0
        self.samples = 0
        self.event_count = 0
        self.closed = False
        self.overflows = 0
        self.last_state = None
        self.last_by_channel = {}
        self._emit({"kind": "capture_start", "phase": self.phase,
                    "channels": list(CHANNELS),
                    "policy": "all clocks; every AW/W/B/AR/R + Wishbone ACK"})

    def _emit(self, event: dict):
        if self.closed:
            raise AssertionError("traffic observer stopped unexpectedly")
        if self.event_count >= self.max_events:
            self.overflows += 1
            raise AssertionError("DDR4 passive AXI/Wishbone event limit reached: capture incomplete")
        event["cycle"] = self.samples
        event.setdefault("phase", self.phase)
        self.log.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
        self.event_count += 1

    def next_phase(self, phase: str):
        if phase not in PHASES:
            raise AssertionError(f"unknown monitor phase: {phase}")
        from_index = PHASES.index(self.phase)
        if PHASES.index(phase) != from_index + 1:
            raise AssertionError(f"monitor phase cannot skip/repeat: {self.phase} -> {phase}")
        if self.phase_cycles[self.phase] == 0:
            raise AssertionError(f"monitor never sampled previous phase {self.phase}")
        self.phase = phase
        self._emit({"kind": "phase_start"})

    def sample(self, sample: dict):
        """Ingest one full input pin snapshot taken at the simulated clock edge."""
        if self.closed:
            raise AssertionError("traffic sampling after capture end")
        self.samples += 1
        self.phase_cycles[self.phase] += 1
        state = (int(sample["init_done"]), int(sample["init_error"]),
                 int(sample["user_rst"]))
        if state != self.last_state:
            self._emit({"kind": "status", "init_done": state[0],
                        "init_error": state[1], "user_rst": state[2]})
            self.last_state = state
        for channel in CHANNELS:
            port = sample[channel]
            if int(port["valid"]) and int(port["ready"]):
                self.channels[channel] += 1
                if channel == "r" and int(port["last"]):
                    self.rlast_count += 1
                payload = {k: int(port[k]) for k in PAYLOAD[channel]}
                self.last_by_channel[channel] = {"cycle": self.samples,
                                                 "phase": self.phase, **payload}
                self._emit({"kind": "axi_handshake", "channel": channel,
                            "fields": payload})
        wb = sample["wb"]
        if int(wb["cyc"]) and int(wb["stb"]) and int(wb["ack"]):
            self.wishbone["writes" if int(wb["we"]) else "reads"] += 1
            self._emit({"kind": "wishbone_handshake",
                        "address": int(wb["adr"]) * 4,
                        "write": int(wb["we"]),
                        "data": int(wb["dat_w"] if int(wb["we"]) else wb["dat_r"]),
                        "error": int(wb["err"])})
        if self.samples % self.heartbeat_cycles == 0:
            self._emit({"kind": "heartbeat",
                        "captured_cycles": self.samples,
                        "channel_handshakes": dict(self.channels)})

    def assert_health(self, task, min_samples: int = 1):
        if self.closed or self.samples < min_samples:
            raise AssertionError("DDR4 AXI/WB observer is not sampling the full test")
        if task.done():
            # If the monitor task exited early, do not let the test report PASS.
            task.result()
            raise AssertionError("DDR4 AXI/WB monitor exited before test teardown")

    def assert_complete(self):
        if self.closed:
            raise AssertionError("observer unexpectedly closed")
        for phase in PHASES:
            if self.phase_cycles[phase] < 1:
                raise AssertionError(f"DDR4 monitoring gap: no clock samples in {phase}")
        if not (self.wishbone["writes"] >= 1 and self.wishbone["reads"] >= 1):
            raise AssertionError("missing DDR4 initialization Wishbone monitoring")
        for channel in CHANNELS:
            if self.channels[channel] < 1:
                raise AssertionError(f"DDR4 traffic monitor missed {channel.upper()} handshakes")
        # Functional smoke finishes all transactions; every request must have
        # a completion. Do not silently accept unobserved terminal channels.
        if self.channels["aw"] != self.channels["b"]:
            raise AssertionError("AXI AW and B counts mismatch: incomplete write traffic")
        if self.channels["ar"] != self.rlast_count:
            raise AssertionError("AXI AR and RLAST counts mismatch: incomplete read traffic")
        if self.overflows:
            raise AssertionError("DDR4 passive capture overflowed")

    def finish(self, status: str, error: str | None = None):
        if self.closed:
            raise AssertionError("monitor finalized twice")
        if status not in ("pass", "fail"):
            raise ValueError("invalid monitor terminal status")
        self._emit({"kind": "capture_end", "status": status,
                    "error": error})
        summary = {
            "status": status, "error": error, "started_before_init": self.phase_cycles["pre_init"] > 0,
            "continuous_capture": all(self.phase_cycles[p] > 0 for p in PHASES),
            "sampled_cycles": self.samples, "phases": dict(self.phase_cycles),
            "channels": dict(self.channels), "rlast_count": self.rlast_count,
            "wishbone": dict(self.wishbone),
            "event_count": self.event_count, "overflows": self.overflows,
            "last_by_channel": self.last_by_channel,
            "events": self.events_path.name,
            "warning": "passive observations; cocotbext-axi remains protocol scoreboard",
        }
        self.log.flush()
        self.log.close()
        self.closed = True
        self.summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return summary


def read_pins(dut) -> dict:
    """One observer read per DUT rising edge; do not alter any signal."""
    def get(name):
        return int(getattr(dut, name).value)
    sample = {channel: {
        "valid": get(f"user_port_axi_0_{channel}valid"),
        "ready": get(f"user_port_axi_0_{channel}ready"),
    } for channel in CHANNELS}
    for channel in CHANNELS:
        if sample[channel]["valid"] and sample[channel]["ready"]:
            for field in PAYLOAD[channel]:
                sample[channel][field] = get(f"user_port_axi_0_{channel}{field}")
    sample["wb"] = {
        "cyc": get("wb_ctrl_cyc"), "stb": get("wb_ctrl_stb"),
        "ack": get("wb_ctrl_ack"), "we": get("wb_ctrl_we"),
    }
    if sample["wb"]["cyc"] and sample["wb"]["stb"] and sample["wb"]["ack"]:
        for field in ("adr", "dat_w", "dat_r", "err"):
            sample["wb"][field] = get(f"wb_ctrl_{field}")
    sample.update({"init_done": get("init_done"), "init_error": get("init_error"),
                   "user_rst": get("user_rst")})
    return sample


async def observe_forever(dut, observer: TrafficObserver):
    from cocotb.triggers import RisingEdge
    while True:
        # Same posedge sampling convention used by upstream cocotb AXI BFMs.
        # No signal drives, no traffic filtering by initialization status.
        await RisingEdge(dut.clk)
        observer.sample(read_pins(dut))
