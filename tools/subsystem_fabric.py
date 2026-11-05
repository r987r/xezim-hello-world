"""Fail-closed reusable peripheral NoC plugin: independent of IP instance names.

The generic emitter exposes two local FlooNoCs plus bounded SRAM and one
reserved management register aperture. A peripheral without attached active
IP drives no AXI transactions; the reserved CSR returns explicit error.
"""
from __future__ import annotations

from subsystem_plugin_contract import IDENT, Port, Registry, SubsystemContract


def peripherals(doc):
    instances = [sub for sub in doc["subsystems"] if sub["type"] == "peripheral"]
    if not instances:
        return []
    spec = doc["subsystem_types"].get("peripheral")
    required = {"local_data_fabric": "local_data",
                "local_config_fabric": "local_config", "sram_count": 1}
    if spec != required:
        raise ValueError("peripheral type requires exactly one local SRAM and separate local data/config FlooNoCs")
    registry = Registry()
    registry.register(SubsystemContract(
        kind="peripheral", clock_domains=("soc",), emitter="passive_local_noc",
        ports=(Port("data", "axi4", "output", "initiator",
                    doc["buses"]["data"]["data_bits"], "soc"),
               Port("config", "axi4_lite", "output", "initiator",
                    doc["buses"]["config"]["data_bits"], "soc"))))
    registry.resolve("peripheral")
    data = {x["name"]: x for x in doc["address_map"]["data"]}
    config = {x["name"]: x for x in doc["address_map"]["config"]}
    for sub in instances:
        name = sub["name"]
        required_keys = {"name", "type", "ip", "data_initiator",
                         "config_initiator", "clock_domain"}
        if set(sub) != required_keys:
            raise ValueError(f"{name}: missing or unknown peripheral properties")
        if not IDENT.fullmatch(name) or not IDENT.fullmatch(sub["ip"]):
            raise ValueError(f"{name}: invalid name/IP")
        for key in ("data_initiator", "config_initiator"):
            endpoint = sub[key]
            if not IDENT.fullmatch(endpoint) or endpoint in {
                    "global_in", "global_out", "sram", "controller_regs"}:
                raise ValueError(f"{name}: illegal {key} endpoint")
        if sub["clock_domain"] != "soc":
            raise ValueError(f"{name}: missing CDC for external clock")
        if name + ".sram" not in data or name + ".ctrl" not in config:
            raise ValueError(f"{name}: missing required SRAM/controller CSR windows")
        if int(data[name + ".sram"]["size"], 0) < doc["boot"]["simulation_sram_bytes"]:
            raise ValueError(f"{name}: SRAM window smaller than physical SRAM model")
    return instances
