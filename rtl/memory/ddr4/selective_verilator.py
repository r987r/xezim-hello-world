"""Minimal pinned cocotb-test Verilator adapter: expose only selected VPI nets.

cocotb-test 0.2.6 adds --public-flat-rw unconditionally. Do not monkeypatch
upstream packages or emit an RTL fork; replace only that specific flag in the
compiler argument list and fail if the upstream command contract changes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path


def restrict_vpi_visibility(commands: list[list[str]], control_file: Path) -> list[list[str]]:
    """Check the *actual* command, not just the generated .vlt file."""
    if not commands or not commands[0]:
        raise ValueError("missing Verilator compiler invocation")
    cmd = list(commands[0])
    if cmd.count("--public-flat-rw") != 1 or cmd.count("--vpi") != 1:
        raise ValueError("unreviewed cocotb-test Verilator VPI invocation")
    if cmd.count(str(control_file)) != 1:
        raise ValueError("selective DDR4 Verilator control file was omitted")
    if any(arg in cmd for arg in ("--public", "--public-flat-rd", "--public-depth")):
        raise ValueError("unreviewed global Verilator VPI visibility")
    cmd.remove("--public-flat-rw")
    if "--public-flat-rw" in cmd:
        raise AssertionError("global VPI visibility still active")
    return [cmd, *commands[1:]]


def run_selective(control_file: Path, **kwargs):
    # Imported only for the actual simulation job, after CI installs cocotb.
    from cocotb_test.simulator import Verilator

    class DDR4Verilator(Verilator):
        async def _exec(self, cmds):
            # Exact pinned runner uses one Verilator compiler command, then
            # make and simulation. Record full compiler stderr separately
            # without incorrectly presenting every %Warning as ERROR cocotb.
            self._is_compiler = (len(cmds) > 2 and
                                 Path(cmds[1]).name == "verilator")
            try:
                await super()._exec(cmds)
            finally:
                self._is_compiler = False

        async def _log_pipe(self, level, stream):
            if not (getattr(self, "_is_compiler", False)
                    and level == logging.ERROR):
                return await super()._log_pipe(level, stream)
            # Preserve every original line; GitHub's console displays a
            # compact warning summary instead of 8,000 misleading errors.
            diagnostic = control_file.parent / "ddr4_simulation_compiler.log"
            with diagnostic.open("w", encoding="utf-8") as log:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    message = line.decode("utf-8", errors="replace").rstrip("\\n")
                    log.write(message + "\\n")
                    if message.startswith("%Error"):
                        self.logger.error(message)

        def build_command(self):
            commands = restrict_vpi_visibility(super().build_command(), control_file)
            # Persist the real command for after-the-fact review and tests.
            out = control_file.parent / "ddr4_compiler_command.json"
            out.write_text(json.dumps({"simulator": "verilator",
                                       "scope": "selected_top_ports_and_72_readonly_dfi_nets",
                                       "argv": commands[0],
                                       "global_public_flat_rw": False}, indent=2) + "\n")
            return commands

    simulation = DDR4Verilator(**kwargs)
    return simulation.run()
