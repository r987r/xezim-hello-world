"""Single canonical regression identity; legacy target paths remain stable.

The logical test is declared ONCE in config/regression.yaml. Simulator and
configuration are derived from the selected execution configuration, not from
a redundant vendor/test registry. An identity is source-selected metadata,
NEVER hardware completion evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
RUN = re.compile(r"(?:ci-[0-9]+-a[0-9]+|local)-[a-f0-9]{12}\Z")
ENGINE_SIMULATOR = {
    "xezim": "xezim",
    "xezim-compile": "xezim",
    "verilator-lint": "verilator",
    "cocotb-verilator": "verilator",
}
SCHEMA = 1

# Keep provenance rooted in existing dependency and interface source files.
# These are inputs, not a second IP inventory or a substitute for Git SHA.
SOURCE_LOCKS = (
    "config/interface_contracts.yaml",
    "config/ip.lock.yaml",
    "Bender.yml",
    "Bender.lock",
)
OPTIONAL_SOURCE_LOCKS = ("rtl/memory/ddr4/toolchain.lock.yml",)


class IdentityError(ValueError):
    pass


def encoded(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def slug(value, key):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise IdentityError(f"{key} must be a lowercase vendor-neutral slug")
    return value


def simulator(test):
    try:
        return ENGINE_SIMULATOR[test["engine"]]
    except (KeyError, TypeError) as exc:
        raise IdentityError("unsupported simulator engine") from exc


def config_target(test):
    """Label the actual *selected* variant without a second profile registry."""
    source = slug(test.get("source_target", test["sources"]).replace("_", "-"), "sources")
    top = test.get("top", "")
    family = "soc" if top in ("full_chip_tb", "full_chip_dma_tb") else source
    qualifiers = []
    if test.get("firmware_mode"):
        qualifiers.append(slug(test["firmware_mode"].replace("_", "-"), "firmware_mode"))
    if test.get("memory_config"):
        path = test["memory_config"]
        if (not isinstance(path, str) or not re.fullmatch(
                r"config/examples/[a-z0-9-]+\.yaml", path)):
            raise IdentityError("memory configuration must be a checked-in source")
        qualifiers.append(Path(path).stem)
    if test.get("boot_relocate"):
        qualifiers.append("relocated")
    if "SYNTHESIS" in test.get("args", []):
        qualifiers.append("synthesis")
    name = "-".join((family, *(qualifiers or ["default"])))
    return slug(name, "config_target")


def neutral_testname(value):
    """Reject implementation names from the existing pinned IP/tool sources.

    This is an enforced naming policy, not a second authoritative IP catalog.
    AXI, SRAM, DDR and CPU are behavioral/protocol words and stay allowed.
    """
    slug(value, "logical_test")
    import yaml
    locked=yaml.safe_load((ROOT/"config/ip.lock.yaml").read_text())
    pinned=set(locked["third_party"])
    forbidden={item.replace("_","-") for item in pinned}
    # Repeated package prefixes reflect the same upstream vendor (PULP).
    heads={key.split("_",1)[0] for key in pinned if "_" in key}
    forbidden.update(h for h in heads if sum(k.startswith(h+"_") for k in pinned)>1)
    req=(ROOT/"csr/requirements.txt").read_text().lower()
    if "peakrdl" in req:
        forbidden.add("peakrdl")
    forbidden.update(ENGINE_SIMULATOR.values())
    for provider in forbidden:
        if value==provider or value.startswith(provider+"-") or value.endswith("-"+provider) or "-"+provider+"-" in value:
            raise IdentityError(f"logical_test cannot embed IP vendor or simulator: {provider}")
    return value


def catalog(tests):
    """Detect collisions between regression YAML entries before CI."""
    if not isinstance(tests, dict) or not tests:
        raise IdentityError("no configured regressions")
    found = {}
    for legacy, test in tests.items():
        slug(legacy, "legacy target")
        name = neutral_testname(test.get("logical_test"))
        key = (simulator(test), config_target(test), name)
        if key in found:
            raise IdentityError(f"duplicate canonical identity: {found[key]} and {legacy} -> {key}")
        found[key] = legacy
    return found


def declared_selection(plan):
    """Exactly the selected fields carried by the original execution plan."""
    return {
        "sources": plan.get("source_target", plan.get("sources")),
        "top": plan.get("top"),
        "firmware_mode": plan.get("firmware_mode"),
        "memory_config": plan.get("memory_config"),
        "boot_relocate": plan.get("boot_relocate"),
        "bender_targets": plan.get("bender_targets", []),
        "report_address_map": (plan.get("report") or {}).get("address_map"),
    }


def selected(name, plan, *, filelist=None, run_id=None, env=None, root=ROOT):
    """Select immutable metadata once per invocation before simulator launch."""
    root = Path(root)
    test_name = neutral_testname(plan.get("logical_test"))
    if run_id is None:
        e = os.environ if env is None else env
        run = e.get("GITHUB_RUN_ID")
        attempt = e.get("GITHUB_RUN_ATTEMPT", "1")
        if run is not None and (not str(run).isdigit() or not str(attempt).isdigit()):
            raise IdentityError("invalid CI execution provenance")
        prefix = f"ci-{run}-a{attempt}" if run is not None else "local"
        run_id = prefix + "-" + uuid.uuid4().hex[:12]
    if not RUN.fullmatch(run_id):
        raise IdentityError("invalid execution ID")
    soc = root / "config/soc.yaml"
    if not soc.is_file():
        raise IdentityError("missing authoritative SoC configuration")
    # Filelist paths alone do not change when a pinned upstream revision or
    # native AXI budget changes. Fingerprint the original authority as well.
    pins = {}
    for name in SOURCE_LOCKS:
        source = root / name
        if not source.is_file():
            raise IdentityError(f"missing authoritative source lock: {name}")
        pins[name] = sha(source.read_bytes())
    for name in OPTIONAL_SOURCE_LOCKS:
        source = root / name
        pins[name] = sha(source.read_bytes()) if source.is_file() else None
    selection = {
        **declared_selection(plan),
        "soc_sha256": sha(soc.read_bytes()),
        "source_lock_sha256": pins,
        "filelist_sha256": sha(Path(filelist).read_bytes()) if filelist is not None else None,
    }
    value = {
        "schema_version": SCHEMA,
        "legacy_target": slug(name, "legacy target"),
        "simulator": simulator(plan),
        "engine": plan["engine"],
        "config_target": config_target(plan),
        "testname": test_name,
        "run_id": run_id,
        "config_sha256": sha(encoded(selection)),
        "selection": selection,
        "seed": plan.get("seed"),
        "evidence_kind": "run_identity_not_execution_or_dut_proof",
    }
    return {**value, "identity_sha256": sha(encoded(value))}


def validate(value, *, target=None, plan=None):
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        raise IdentityError("unsupported or missing run identity")
    if set(value) != {
        "schema_version", "legacy_target", "simulator", "engine",
        "config_target", "testname", "run_id", "config_sha256",
        "selection", "seed", "evidence_kind", "identity_sha256",
    }:
        raise IdentityError("invalid run identity fields")
    for key in ("legacy_target", "simulator", "config_target", "testname"):
        slug(value[key], key)
    if not isinstance(value["run_id"], str) or not RUN.fullmatch(value["run_id"]):
        raise IdentityError("invalid run ID")
    if value["evidence_kind"] != "run_identity_not_execution_or_dut_proof":
        raise IdentityError("identity asserts unobserved hardware execution")
    if (not isinstance(value["selection"], dict)
            or sha(encoded(value["selection"])) != value["config_sha256"]):
        raise IdentityError("identity configuration fingerprint mismatch")
    if sha(encoded({k:v for k,v in value.items() if k!="identity_sha256"})) != value["identity_sha256"]:
        raise IdentityError("run identity digest mismatch")
    if target is not None and value["legacy_target"] != target:
        raise IdentityError("foreign run identity target")
    if plan is not None and (value["engine"] != plan.get("engine")
            or value["simulator"] != simulator(plan)
            or value["config_target"] != config_target(plan)
            or value["testname"] != plan.get("logical_test")
            or value["seed"] != plan.get("seed")):
        raise IdentityError("run identity differs from selected plan")
    if plan is not None and any(
        value["selection"].get(key) != selected_value
        for key, selected_value in declared_selection(plan).items()
    ):
        raise IdentityError("run identity source selection differs from plan")
    return value


def relative_path(value):
    validate(value)
    return Path(value["simulator"]) / value["config_target"] / value["testname"] / value["run_id"]


def save(path, value):
    validate(value)
    path = Path(path)
    if path.is_symlink():
        raise IdentityError("refusing symlink run identity")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load(path, *, target=None, plan=None):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise IdentityError("missing or unsafe run identity")
    return validate(json.loads(path.read_text()), target=target, plan=plan)
