#!/usr/bin/env python3
"""Source-qualified, replaceable PCIe digital-link provider configuration.

This module is a preflight / generated selection manifest, NOT a simulator,
host model, claimed LTSSM link-up, or a second regression/action dispatcher.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "config/pcie_link.yaml"
LOCK = "config/ip.lock.yaml"
REQUIRED_ENDPOINT = (
    "ip_lock", "top", "config_space_rdl", "tx_data", "tx_datak",
    "tx_valid", "tx_electrical_idle", "rx_data", "rx_datak",
    "rx_valid", "rx_electrical_idle", "ltssm_state", "link_up",
)
REQUIRED_HOST = (
    "ip_lock", "dependency_ip_lock", "top", "tx_data", "tx_datak",
    "rx_data", "rx_datak", "tx_electrical_idle", "rx_electrical_idle",
    "endpoint_parameter", "endpoint_parameter_value", "data_width_parameter",
)
CAPABILITY_FLAGS = ("trained_l0", "hardware_config_enumeration",
                    "bar0_hardware_decode")
HEX_SHA = re.compile(r"[0-9a-f]{40}\Z")


class PcieProviderError(ValueError):
    pass


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise PcieProviderError(f"invalid provider source document {path}")
    return value


def _required(data: dict, expected: tuple[str, ...], what: str):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise PcieProviderError(f"{what}: required provider fields missing or unexpected")
    for key in expected:
        value = data[key]
        if value is None or isinstance(value, str) and not value:
            raise PcieProviderError(f"{what}.{key}: missing field")


def selection(root: Path = ROOT) -> dict:
    root = Path(root)
    doc = _load(root / PROFILE)
    lock = _load(root / LOCK)
    if (doc.get("schema_version") != 1 or not isinstance(doc.get("profiles"), dict)
            or not isinstance(doc.get("selected_profile"), str)
            or doc["selected_profile"] not in doc["profiles"]
            or not isinstance(lock.get("third_party"), dict)):
        raise PcieProviderError("invalid selected PCIe provider profile or IP lock")
    label = doc["selected_profile"]
    p = doc["profiles"][label]
    if set(p) != {"endpoint", "host", "phy", "link"}:
        raise PcieProviderError("PCIe profile missing provider boundary")
    ep, host, phy, link = p["endpoint"], p["host"], p["phy"], p["link"]
    _required(ep, REQUIRED_ENDPOINT, "endpoint")
    _required(host, REQUIRED_HOST, "host")
    if (not isinstance(phy, dict)
            or set(phy) != {"adapter", "implementation", "status_driver"}
            or phy["implementation"] != "behavioral_digital_pipe_only"
            or phy["status_driver"] != "not_connected_yet"):
        raise PcieProviderError("PHY digital/status boundary cannot claim training")
    if (not isinstance(link, dict)
            or set(link) != {"generation", "lanes", "data_width_bits",
                             "datak_width_bits", "encoded_symbol_clock_mhz",
                             "pipe_parallel_clock_mhz", "qualifier",
                             *CAPABILITY_FLAGS}
            or type(link["generation"]) is not int or link["generation"] != 1
            or type(link["lanes"]) is not int or link["lanes"] != 1
            or type(link["data_width_bits"]) is not int
            or link["data_width_bits"] != 32
            or type(link["datak_width_bits"]) is not int
            or link["datak_width_bits"] != 4
            or link["encoded_symbol_clock_mhz"] != 250
            or link["pipe_parallel_clock_mhz"] != 62.5
            or link["qualifier"] != "source_and_adapter_preflight_only"
            or any(link.get(flag) is not False for flag in CAPABILITY_FLAGS)):
        raise PcieProviderError("unsupported x1 Gen1 physical clock/width or false qualification")
    if (type(host["endpoint_parameter_value"]) is not int
            or host["endpoint_parameter_value"] != 0
            or host["data_width_parameter"] != "DataWidth"):
        raise PcieProviderError("host must be a 32-bit root-complex provider")
    if ep["ip_lock"] == host["ip_lock"]:
        raise PcieProviderError("endpoint and independent host may not be the same model")
    providers = {}
    for role, key in (("endpoint", ep["ip_lock"]),
                      ("host", host["ip_lock"]),
                      ("host_support", host["dependency_ip_lock"])):
        entry = lock["third_party"].get(key)
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("git"), str)
                or not entry["git"].startswith("https://github.com/")
                or not isinstance(entry.get("commit"), str)
                or HEX_SHA.fullmatch(entry["commit"]) is None
                or not isinstance(entry.get("license"), str)
                or not isinstance(entry.get("modules"), list)
                or not entry["modules"]):
            raise PcieProviderError(f"{role}: missing pinned, licensed upstream source")
        providers[role] = {
            "ip_lock_key": key, "git": entry["git"],
            "commit": entry["commit"], "license": entry["license"],
            "modules": entry["modules"],
            "submodules": entry.get("submodules", []),
            "integration": entry.get("integration", "unspecified"),
        }
    if not providers["host"]["license"].startswith("GPL"):
        raise PcieProviderError("host license must be surfaced as GPL testbench-only")
    adapter_path = Path(phy["adapter"])
    if (adapter_path.is_absolute() or ".." in adapter_path.parts
            or adapter_path.suffix != ".sv"):
        raise PcieProviderError("unsafe PHY adapter source path")
    adapter = root / adapter_path
    if not adapter.is_file() or not adapter.read_text().lstrip().startswith(
            "`timescale 1ns/1ps"):
        raise PcieProviderError("no checked-in digital PHY adapter implementation")
    return {
        "schema_version": 1,
        "selection": label,
        "source": PROFILE,
        "source_sha256": digest((root / PROFILE).read_bytes()),
        "ip_lock_sha256": digest((root / LOCK).read_bytes()),
        "providers": providers,
        "ports": {"endpoint": ep, "host": host},
        "phy": {**phy, "adapter_sha256": digest(adapter.read_bytes())},
        "link": link,
        "capability": {
            "status": "source_declared_not_executed",
            "provider_interface_preflight": "not_elaborated",
            "l0_trained": False,
            "host_config_accepted_on_real_link": False,
            "bar0_decode_in_real_controller": False,
            "digital_phy_sideband_ready": False,
            "physical_serdes_implemented": False,
        },
        "evidence": "pinned_selected_sources_and_checked_in_digital_adapter_only",
    }


def validate_provider_sources(root: Path, result: dict) -> None:
    """Check original selected upstream source pins, never fabricate RTL elaboration."""
    root = Path(root)
    for role, mapping in result["ports"].items():
        entry = result["providers"][role]
        checked = root / ".tools" / entry["ip_lock_key"]
        if not checked.is_dir():
            raise PcieProviderError(f"{role}: missing fetched exact pinned source")
        candidates = list(checked.rglob("*.sv")) + list(checked.rglob("*.v"))
        top = mapping["top"]
        # Read only checked-in source with actual module name to avoid
        # interpreting a documentation string as a compiled port list.
        matches = [
            file for file in candidates
            if re.search(r"\bmodule\s+" + re.escape(top) + r"\b",
                         file.read_text(errors="replace"))
        ]
        if len(matches) != 1:
            raise PcieProviderError(f"{role}: missing/duplicate original top module {top}")
        source = matches[0].read_text(errors="replace")
        for label, wire in mapping.items():
            if label in ("ip_lock", "dependency_ip_lock", "top", "config_space_rdl",
                         "endpoint_parameter", "endpoint_parameter_value",
                         "data_width_parameter"):
                continue
            if not re.search(r"\b" + re.escape(wire) + r"\b", source):
                raise PcieProviderError(f"{role}: no original pin {wire}")
    ep = result["providers"]["endpoint"]
    rdl = root / ".tools" / ep["ip_lock_key"] / result["ports"]["endpoint"]["config_space_rdl"]
    if not rdl.is_file() or not re.search(r"@\s*0x10\s*;", rdl.read_text()):
        raise PcieProviderError("missing upstream PCIe config-space BAR0 SystemRDL")
    host = result["providers"]["host"]
    if not (root / ".tools" / host["ip_lock_key"] / "LICENSE").is_file():
        raise PcieProviderError("missing GPL testbench license at pinned host commit")


def generated_files(root: Path = ROOT) -> dict[str, str]:
    row = selection(root)
    payload = json.dumps(row, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ep = row["providers"]["endpoint"]
    host = row["providers"]["host"]
    readme = (
        "# Digital PCIe provider selection (generated)\n\n"
        "Do not edit. `make gen` regenerates from "
        "[config/pcie_link.yaml](../../config/pcie_link.yaml) and "
        "[config/ip.lock.yaml](../../config/ip.lock.yaml).\n\n"
        f"Endpoint: `{ep['ip_lock_key']}` @ `{ep['commit']}`\n\n"
        f"Host testbench: `{host['ip_lock_key']}` @ `{host['commit']}` "
        "(GPL-3.0; not SoC RTL).\n\n"
        f"Digital adapter: `{row['phy']['adapter']}`.\n\n"
        "The upstream PCIe configuration-space RDL is **source-owned by "
        "the endpoint IP**, separate from SoC Config-NoC requester CSR. "
        "Do not copy BAR0 into a second hand-maintained SoC register map.\n\n"
        "**NOT QUALIFIED:** LTSSM L0, PHY-status responder, host "
        "enumeration, programmable BAR0 decode and silicon SerDes. "
        "The existing `chip-pcie-host` remains TLP-bridge-only. "
        "Use original pinned RTL CI evidence before changing these labels.\n"
    )
    return {"selection.json": payload, "README.md": readme}


def emit(root: Path, out: Path) -> None:
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for name, content in generated_files(root).items():
        (target / name).write_text(content)


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--out", type=Path, default=ROOT / "gen/pcie_link")
    cli.add_argument("--check", action="store_true")
    cli.add_argument("--check-upstream", action="store_true")
    args = cli.parse_args()
    result = selection(args.root)
    if args.check_upstream:
        validate_provider_sources(args.root, result)
    contents = generated_files(args.root)
    if args.check:
        if any(not (args.out / name).is_file()
               or (args.out / name).read_text() != text
               for name, text in contents.items()):
            raise PcieProviderError("stale checked-in generated PCIe link selection")
        print("PASS: checked-in PCIe provider selection exact match (not trained)")
        return 0
    emit(args.root, args.out)
    print("Emitted pinned replaceable PCIe provider selection (NOT link-qualified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
