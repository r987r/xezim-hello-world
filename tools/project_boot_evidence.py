"""Validate project-owned native boot evidence for the existing Pages collector."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from project_smoke import ProjectSmokeError, check_native_boot_log

WORKFLOW = "project-compile.yml"
RESULT = "boot-result.json"
LOGS = ("native-build.log", "native-sim.log")
FILES = {RESULT, *LOGS}
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")


def validate(folder, project, run, artifact_name):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    result = json.loads((folder / RESULT).read_text())
    require(isinstance(result, dict), "native boot result must be an object")
    pid = project["id"]
    run_id, attempt = run["id"], run.get("run_attempt", 1)
    cores = len(project["compute"])
    require(artifact_name == f"project-boot-{pid}-{run_id}-{attempt}",
            "project boot artifact name/attempt mismatch")
    require(project["qualification"] != "source_contract_only", "project has no boot job")
    require(result.get("project_id") == pid and result.get("source_config") == project["config"]
            and result.get("source_config_sha256") == project["config_sha256"],
            "project boot config identity mismatch")
    require(result.get("schema_version") == 1
            and result.get("engine") == "verilator-native"
            and result.get("test") == "native-selected-real-cpu-cold-boot"
            and type(result.get("cpu_count")) is int and result["cpu_count"] == cores
            and all(result.get(key) is False for key in
                    ("ddr_data_qualified", "pcie_qualified", "ethernet_qualified"))
            and HEX64.fullmatch(str(result.get("filelist_sha256"))),
            "invalid native boot scope/selected filelist")
    require(result.get("workflow_run_id") == str(run_id)
            and result.get("workflow_attempt") == str(attempt)
            and HEX40.fullmatch(str(result.get("tested_sha"))),
            "project boot run/attempt identity mismatch")
    require(run.get("status") == "completed"
            and run.get("conclusion") in ("success", "failure"),
            "native boot run is incomplete or inconclusive")
    recorded = result.get("status")
    require(recorded in ("passed", "failed"), "invalid native boot outcome")
    require(recorded != "failed" or run.get("conclusion") == "failure",
            "native boot outcome contradicts workflow")
    logs = result.get("log_sha256")
    require(isinstance(logs, dict) and set(logs).issubset(LOGS),
            "native boot log hashes missing or invalid")
    for name in LOGS:
        path = folder / name
        if path.is_file():
            require(hashlib.sha256(path.read_bytes()).hexdigest() == logs.get(name),
                    "native boot log digest mismatch")
        else:
            require(name not in logs, "missing claimed native boot log")
    if recorded == "passed":
        require(set(logs) == set(LOGS) and result.get("simulation_returncode") == 0,
                "passing native boot requires original logs and simulator success")
        try:
            observed = check_native_boot_log((folder / LOGS[1]).read_text(), cores)
        except ProjectSmokeError as exc:
            raise ValueError(str(exc)) from exc
        require(observed == result.get("observations"), "native boot observations mismatch")
    return result


def publish(evidence, output, site_sha):
    """Copy only verified run-owned logs; prefer same-source over historical."""
    records = {}
    for file in sorted(evidence.glob("*/project-boot-*/verified-boot.json")):
        record = json.loads(file.read_text())
        if not isinstance(record, dict):
            raise ValueError("invalid verified project boot record")
        pid = record["project_id"]
        run_id, attempt = record["run_id"], record["attempt"]
        if (not re.fullmatch(r"[a-z][a-z0-9_]*", pid)
                or type(run_id) is not int or type(attempt) is not int
                or run_id < 1 or attempt < 1):
            raise ValueError("invalid verified boot publication path")
        relative = Path("boot") / f"{run_id}-{attempt}"
        destination = output / "projects" / pid / relative
        destination.mkdir(parents=True, exist_ok=True)
        logs = {}
        for name in LOGS:
            if (file.parent / name).is_file():
                shutil.copyfile(file.parent / name, destination / name)
                logs[name] = (relative / name).as_posix()
        record.update(logs=logs, current_source=(
            record["tested_sha"] == site_sha or record.get("equivalent_site_sha") == site_sha))
        records.setdefault(pid, []).append(record)
    return {pid: max(items, key=lambda r: (r["current_source"], r["run_id"], r["attempt"]))
            for pid, items in records.items()}
