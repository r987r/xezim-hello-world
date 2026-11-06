"""Compile shared SoC stimulus intent; never treat a plan as RTL evidence.

Schema v1 uses explicit action-instance IDs and a dependency DAG. Physical
addresses are *predicted* by the existing memory planner; real CPU/NoC results
must be independently captured and checked by execution adapters/reporters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any

from tools.memory_plan import configured_regions

SCHEMA_VERSION = 1
RANDOM_ALGORITHM = "sha256-rejection-v1"
PHASES = ("init", "run", "check")
KINDS = frozenset(("memory.allocate", "memory.initialize", "memory.check",
                   "memory.release", "dma.configure", "dma.copy", "dma.wait_idle"))
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
PATTERNS = frozenset(("constant", "counter8", "address_xor"))
POLICIES = frozenset(("strict", "fast", "hybrid", "auto"))
U32 = (1 << 32) - 1


class ScenarioError(ValueError):
    """Invalid or ambiguous verification intent, before RTL execution."""


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ScenarioError(f"{label}: invalid name {value!r}")
    return value


def _int(value: Any, label: str, *, low: int = 0, high: int = (1 << 64) - 1) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ScenarioError(f"{label}: expected integer in [{low}, {high}]")
    return value


def _fields(obj: Any, required: set[str], optional: set[str], label: str) -> dict:
    if not isinstance(obj, dict) or set(obj) - required - optional or required - set(obj):
        raise ScenarioError(f"{label}: required {sorted(required)}, allowed {sorted(required | optional)}")
    return obj


def _canonical(obj: Any) -> bytes:
    try:
        return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ScenarioError(f"non-JSON scenario value: {exc}") from exc


def canonical_json(obj: Any) -> str:
    """Stable JSON serialization; no run-time timestamps or random object IDs."""
    return _canonical(obj).decode("ascii")


def _digest(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _draw(seed: int, action_id: str, path: str, count: int) -> int:
    if count < 1 or count > (1 << 256):
        raise ScenarioError("random domain outside supported range")
    ceiling = ((1 << 256) // count) * count
    for nonce in range(256):
        payload = _canonical(["soc-scenario-random-v1", seed, action_id, path, nonce])
        candidate = int.from_bytes(hashlib.sha256(payload).digest(), "big")
        if candidate < ceiling:
            return candidate % count
    raise ScenarioError("random rejection limit exceeded")


def _resolve_choices(value: Any, seed: int, action: str, path: str) -> Any:
    if isinstance(value, dict):
        if "choose" in value:
            _fields(value, {"choose"}, set(), f"{action}/{path}")
            choices = value["choose"]
            if not isinstance(choices, list) or not choices:
                raise ScenarioError(f"{action}/{path}: choose requires nonempty list")
            idx = _draw(seed, action, path, len(choices))
            selected = choices[idx]
            if isinstance(selected, dict) and ("choose" in selected or "randint" in selected):
                raise ScenarioError(f"{action}/{path}: nested random choice not supported")
            return _resolve_choices(selected, seed, action, path + "/selected")
        if "randint" in value:
            _fields(value, {"randint"}, set(), f"{action}/{path}")
            bounds = _fields(value["randint"], {"min", "max"}, {"step"}, f"{action}/{path}/randint")
            low = _int(bounds["min"], f"{action}/{path}/min")
            high = _int(bounds["max"], f"{action}/{path}/max")
            step = _int(bounds.get("step", 1), f"{action}/{path}/step", low=1)
            if high < low or (high - low) % step:
                raise ScenarioError(f"{action}/{path}: invalid randint bounds/step")
            return low + step * _draw(seed, action, path, (high - low) // step + 1)
        return {k: _resolve_choices(v, seed, action, path + "/" + k)
                for k, v in sorted(value.items()) if isinstance(k, str)} if all(
                    isinstance(k, str) for k in value) else _invalid_key(action, path)
    if isinstance(value, list):
        return [_resolve_choices(v, seed, action, f"{path}/{i}") for i, v in enumerate(value)]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ScenarioError(f"{action}/{path}: unsupported value {value!r}")


def _invalid_key(action: str, path: str) -> Any:
    raise ScenarioError(f"{action}/{path}: argument keys must be strings")


@dataclass(frozen=True)
class Action:
    action_instance_id: str
    kind: str
    actor: str
    phase: str
    args: dict[str, Any]
    depends_on: tuple[str, ...] = ()
    parent_action_id: str | None = None
    expected_result_id: str | None = None

    def as_dict(self) -> dict:
        item = dict(action_instance_id=self.action_instance_id, kind=self.kind,
                    actor=self.actor, phase=self.phase, args=self.args,
                    depends_on=list(self.depends_on))
        if self.parent_action_id is not None:
            item["parent_action_id"] = self.parent_action_id
        if self.expected_result_id is not None:
            item["expected_result_id"] = self.expected_result_id
        return item


@dataclass
class Scenario:
    scenario_id: str
    actors: tuple[str, ...]
    seed: int
    variant: str = "boot_live"
    actions: list[Action] = field(default_factory=list)

    def add(self, action_instance_id: str, kind: str, actor: str, phase: str,
            args: dict[str, Any], *, depends_on: tuple[str, ...] = (),
            parent_action_id: str | None = None,
            expected_result_id: str | None = None) -> "Scenario":
        self.actions.append(Action(action_instance_id, kind, actor, phase, args,
                                   tuple(depends_on), parent_action_id, expected_result_id))
        return self

    def as_dict(self) -> dict:
        return dict(schema_version=SCHEMA_VERSION, scenario_id=self.scenario_id,
                    actors=list(self.actors), seed=self.seed, variant=self.variant,
                    actions=[a.as_dict() for a in self.actions])


def _ordered_actions(spec: dict, seed: int) -> tuple[list[dict], dict[str, set[str]]]:
    originals = spec["actions"]
    if not isinstance(originals, list) or not originals:
        raise ScenarioError("scenario needs nonempty actions list")
    by_id: dict[str, dict] = {}
    for item in originals:
        a = _fields(item, {"action_instance_id", "kind", "actor", "phase", "args"},
                    {"depends_on", "parent_action_id", "expected_result_id"}, "action")
        aid = _name(a["action_instance_id"], "action_instance_id")
        if aid in by_id:
            raise ScenarioError(f"duplicate action_instance_id {aid}")
        if not isinstance(a["kind"], str) or a["kind"] not in KINDS:
            raise ScenarioError(f"{aid}: unsupported action kind {a['kind']!r}")
        if a["phase"] not in PHASES:
            raise ScenarioError(f"{aid}: unknown phase {a['phase']!r}")
        _name(a["actor"], f"{aid}.actor")
        deps = a.get("depends_on", [])
        if not isinstance(deps, (list, tuple)) or any(
                not isinstance(d, str) for d in deps) or len(deps) != len(set(deps)):
            raise ScenarioError(f"{aid}: invalid/duplicate dependencies")
        parent = a.get("parent_action_id")
        if parent is not None:
            _name(parent, f"{aid}.parent_action_id")
        expected = a.get("expected_result_id")
        if expected is not None:
            _name(expected, f"{aid}.expected_result_id")
        if not isinstance(a["args"], dict):
            raise ScenarioError(f"{aid}: args must be an object")
        by_id[aid] = dict(action_instance_id=aid, kind=a["kind"],
                          actor=a["actor"], phase=a["phase"],
                          args=_resolve_choices(a["args"], seed, aid, "args"),
                          depends_on=sorted(deps), parent_action_id=parent,
                          expected_result_id=expected or f"expect.{aid}")
    expected_ids = [a["expected_result_id"] for a in by_id.values()]
    if len(expected_ids) != len(set(expected_ids)):
        raise ScenarioError("duplicate expected_result_id")
    for a in by_id.values():
        aid = a["action_instance_id"]
        if a["parent_action_id"] is not None and (a["parent_action_id"] not in by_id or a["parent_action_id"] == aid):
            raise ScenarioError(f"{aid}: unknown/self parent action")
        for dep in a["depends_on"]:
            if dep not in by_id:
                raise ScenarioError(f"{aid}: missing dependency {dep}")
            if PHASES.index(by_id[dep]["phase"]) > PHASES.index(a["phase"]):
                raise ScenarioError(f"{aid}: dependency crosses phase backwards: {dep}")

    visiting: set[str] = set()
    ancestors: dict[str, set[str]] = {}
    ordered: list[dict] = []

    def visit(aid: str) -> None:
        if aid in visiting:
            raise ScenarioError(f"cyclic action dependencies involving {aid}")
        if aid in ancestors:
            return
        visiting.add(aid)
        ancestors_here: set[str] = set()
        for dep in by_id[aid]["depends_on"]:
            visit(dep)
            ancestors_here.add(dep)
            ancestors_here.update(ancestors[dep])
        visiting.remove(aid)
        ancestors[aid] = ancestors_here
        ordered.append(by_id[aid])

    for aid in sorted(by_id):
        visit(aid)
    return ordered, ancestors


def _range(args: dict, *, allowed: set[str], label: str,
           capacity: int, default_length: int | None = None) -> tuple[int, int]:
    _fields(args, {"buffer"}, allowed, label)
    off = _int(args.get("offset", 0), f"{label}.offset")
    length = _int(args.get("length", default_length), f"{label}.length", low=1)
    if off + length > capacity:
        raise ScenarioError(f"{label}: buffer range exceeds modeled allocation")
    return off, off + length


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return max(a[0], b[0]) < min(a[1], b[1])


def _covered(segment: tuple[int, int], ranges: list[tuple[int, int]]) -> bool:
    pos = segment[0]
    for start, end in sorted(ranges):
        if start <= pos:
            pos = max(pos, end)
        if pos >= segment[1]:
            return True
    return False


def _validate_memory(ordered: list[dict], ancestors: dict[str, set[str]],
                     regions: dict, config: dict) -> list[dict]:
    available_engines = {x["name"] for x in config["address_map"]["config"]
                         if x["name"].endswith(".dma")}
    buffers: dict[str, dict] = {}
    writes: dict[str, list[tuple[str, tuple[int, int]]]] = {}
    reads: dict[str, list[tuple[str, tuple[int, int]]]] = {}
    accesses: dict[str, set[str]] = {}
    last_region_alloc: dict[str, str] = {}
    releases: dict[str, str] = {}

    def use(buffer: str, aid: str, *, offset: int = 0,
            length: int | None = None, write: bool = False, read: bool = False) -> tuple[int, int]:
        if not isinstance(buffer, str) or buffer not in buffers:
            raise ScenarioError(f"{aid}: unknown/stale buffer {buffer!r}")
        allocation = buffers[buffer]
        if allocation["allocated_by"] not in ancestors[aid]:
            raise ScenarioError(f"{aid}: missing allocation dependency for {buffer}")
        if buffer in releases:
            raise ScenarioError(f"{aid}: use-after-release for {buffer}")
        size = allocation["size"]
        start = _int(offset, f"{aid}.offset")
        nbytes = _int(length if length is not None else size - start,
                      f"{aid}.length", low=1)
        if start + nbytes > size:
            raise ScenarioError(f"{aid}: {buffer} out of bounds")
        interval = (start, start + nbytes)
        accesses[buffer].add(aid)
        if read:
            reads[buffer].append((aid, interval))
        if write:
            writes[buffer].append((aid, interval))
        return interval

    for a in ordered:
        aid, kind, args = a["action_instance_id"], a["kind"], a["args"]
        phase = a["phase"]
        if kind == "memory.allocate":
            if phase == "check":
                raise ScenarioError(f"{aid}: allocation cannot start in CHECK")
            _fields(args, {"buffer", "region", "size", "alignment"}, {"phys"}, aid)
            buffer = _name(args["buffer"], f"{aid}.buffer")
            region = args["region"]
            if buffer in buffers:
                raise ScenarioError(f"{aid}: duplicate/reused buffer handle {buffer}")
            if region not in regions:
                raise ScenarioError(f"{aid}: unknown region {region!r}")
            prior = last_region_alloc.get(region)
            if prior is not None and prior not in ancestors[aid]:
                raise ScenarioError(f"{aid}: unordered allocations in {region}; declare dependency for deterministic C addresses")
            size = _int(args["size"], f"{aid}.size", low=1)
            alignment = _int(args["alignment"], f"{aid}.alignment", low=1)
            try:
                allocation = regions[region].allocate(size, alignment, owner=a["actor"], phase=phase)
            except (ValueError, MemoryError) as exc:
                raise ScenarioError(f"{aid}: {exc}") from exc
            if "phys" in args and _int(args["phys"], f"{aid}.phys") != allocation.phys:
                raise ScenarioError(f"{aid}: requested physical address disagrees with allocator (possible overlap/reservation misuse)")
            a["allocation"] = allocation.as_dict()
            buffers[buffer] = {**allocation.as_dict(), "buffer": buffer,
                               "allocated_by": aid, "released_by": None,
                               "state": "planned_only"}
            last_region_alloc[region] = aid
            writes[buffer], reads[buffer], accesses[buffer] = [], [], set()
        elif kind in ("memory.initialize", "memory.check"):
            if (kind == "memory.initialize" and phase == "check") or (kind == "memory.check" and phase != "check"):
                raise ScenarioError(f"{aid}: invalid phase for {kind}")
            _fields(args, {"buffer", "length", "pattern", "policy"},
                    {"offset", "expected_from"} if kind == "memory.check" else {"offset"}, aid)
            buffer = args["buffer"]
            data = buffers.get(buffer)
            if data is None:
                raise ScenarioError(f"{aid}: unknown buffer {buffer!r}")
            start, end = _range(args, allowed={"offset", "length", "pattern", "policy", "expected_from"},
                                label=aid, capacity=data["size"])
            pat = _fields(args["pattern"], {"kind", "seed"}, set(), aid + ".pattern")
            if pat["kind"] not in PATTERNS:
                raise ScenarioError(f"{aid}: unsupported pattern")
            _int(pat["seed"], f"{aid}.pattern.seed", high=U32)
            if args["policy"] not in POLICIES:
                raise ScenarioError(f"{aid}: invalid memory policy")
            if a["actor"].startswith("cpu") and not regions[data["region"]].cpu_visible:
                raise ScenarioError(f"{aid}: 32-bit CPU cannot directly initialize/check DDR or HBM")
            # For moved DMA payloads the recipe is based on the ORIGINAL
            # source address, not the destination address. This is an
            # immutable golden reference, not another hardware read.
            if kind == "memory.check" and "expected_from" in args:
                reference = args["expected_from"]
                if reference not in buffers:
                    raise ScenarioError(f"{aid}: unknown expected_from buffer {reference!r}")
                source = buffers[reference]
                if source["allocated_by"] not in ancestors[aid] or end > source["size"]:
                    raise ScenarioError(f"{aid}: expected_from allocation/range not causally available")
                initialized = [
                    (int(item["args"].get("offset", 0)),
                     int(item["args"].get("offset", 0)) + item["args"]["length"])
                    for item in ordered
                    if item["kind"] == "memory.initialize"
                    and item["args"].get("buffer") == reference
                    and item["args"].get("pattern") == args["pattern"]
                    and item["action_instance_id"] in ancestors[aid]
                ]
                if not _covered((start, end), initialized):
                    raise ScenarioError(f"{aid}: expected_from recipe has no matching causal initialization")
            use(buffer, aid, offset=start, length=end - start,
                write=kind == "memory.initialize", read=kind == "memory.check")
        elif kind == "dma.configure":
            if phase == "check":
                raise ScenarioError(f"{aid}: DMA configure in CHECK")
            _fields(args, {"engine", "descriptor_buffer"}, set(), aid)
            if args["engine"] not in available_engines:
                raise ScenarioError(f"{aid}: unknown DMA engine")
            use(args["descriptor_buffer"], aid, read=True)
        elif kind == "dma.copy":
            if phase != "run":
                raise ScenarioError(f"{aid}: DMA copy outside RUN")
            _fields(args, {"engine", "src", "dst", "length"},
                    {"src_offset", "dst_offset"}, aid)
            if args["engine"] not in available_engines:
                raise ScenarioError(f"{aid}: unknown DMA engine")
            nbytes = _int(args["length"], f"{aid}.length", low=1, high=U32)
            if args["src"] == args["dst"]:
                raise ScenarioError(f"{aid}: in-place DMA copy unsupported by v1 intent")
            use(args["src"], aid, offset=args.get("src_offset", 0), length=nbytes, read=True)
            use(args["dst"], aid, offset=args.get("dst_offset", 0), length=nbytes, write=True)
        elif kind == "dma.wait_idle":
            if phase not in ("run", "check"):
                raise ScenarioError(f"{aid}: DMA idle wait outside RUN/CHECK")
            _fields(args, {"engine"}, set(), aid)
            if args["engine"] not in available_engines:
                raise ScenarioError(f"{aid}: unknown DMA engine")
        elif kind == "memory.release":
            if phase not in ("run", "check"):
                raise ScenarioError(f"{aid}: release outside RUN/CHECK")
            _fields(args, {"buffer", "consumers_quiesced"}, set(), aid)
            buffer = args["buffer"]
            if buffer not in buffers or buffer in releases:
                raise ScenarioError(f"{aid}: stale/double release {buffer!r}")
            if args["consumers_quiesced"] is not True:
                raise ScenarioError(f"{aid}: explicit quiescence precondition required (not hardware proof)")
            info = buffers[buffer]
            if info["allocated_by"] not in ancestors[aid]:
                raise ScenarioError(f"{aid}: release does not depend on allocation")
            try:
                regions[info["region"]].release(
                    _allocation_from_info(info), consumers_quiesced=True)
            except RuntimeError as exc:
                raise ScenarioError(f"{aid}: {exc}") from exc
            info["released_by"] = aid
            releases[buffer] = aid

    # The real C allocator is LIFO. A sorted topological walk alone does not
    # establish an execution-order guarantee for independent actor lanes.
    by_region: dict[str, list[dict]] = {}
    for item in buffers.values():
        by_region.setdefault(item["region"], []).append(item)
    for region, items in by_region.items():
        for index, earlier in enumerate(items):
            earlier_release = earlier["released_by"]
            if earlier_release is None:
                continue
            for later in items[index + 1:]:
                # Either the previous allocation is fully retired before a
                # subsequent allocation, or that subsequent allocation must
                # be retired first (explicit causal dependency).
                if earlier_release in ancestors[later["allocated_by"]]:
                    continue
                later_release = later["released_by"]
                if later_release is None or later_release not in ancestors[earlier_release]:
                    raise ScenarioError(
                        f"{earlier_release}: missing LIFO release dependency on {later['buffer']} in {region}")

    # Inspect the complete dependency graph, not just the sorted plan traversal:
    # independent actors can be concurrent even when their JSON rows are adjacent.
    for buffer, info in buffers.items():
        for read_id, segment in reads[buffer]:
            prior_writes = [interval for write_id, interval in writes[buffer]
                            if write_id in ancestors[read_id]]
            if not _covered(segment, prior_writes):
                raise ScenarioError(f"{read_id}: uninitialized read/check of {buffer}")
            for write_id, interval in writes[buffer]:
                if write_id != read_id and _overlap(segment, interval) and (
                        write_id not in ancestors[read_id] and read_id not in ancestors[write_id]):
                    raise ScenarioError(f"{read_id}: unordered read/write race on {buffer} with {write_id}")
        for i, (first, segment) in enumerate(writes[buffer]):
            for second, other in writes[buffer][i + 1:]:
                if _overlap(segment, other) and first not in ancestors[second] and second not in ancestors[first]:
                    raise ScenarioError(f"{first}/{second}: unordered overlapping writes to {buffer}")
        release_id = info["released_by"]
        if release_id is not None:
            for user in accesses[buffer]:
                if user not in ancestors[release_id]:
                    raise ScenarioError(f"{release_id}: missing dependency on in-flight consumer {user} of {buffer}")
    return [buffers[k] for k in sorted(buffers)]


def _allocation_from_info(info: dict):
    # Rebuild only the exact planner handle, never simulate a new allocation.
    from tools.memory_plan import VirtualAllocation
    return VirtualAllocation(**{key: info[key] for key in (
        "region", "phys", "size", "token", "previous_used", "previous_token",
        "generation", "owner", "phase")})


def resolve_scenario(spec: Scenario | dict, config: dict, *,
                     source_revision: str | None = None) -> dict:
    """Resolve a valid typed intent into canonical, source-neutral JSON data.

    The returned plan has *no observed execution* and must never count as a
    passing hardware check. source_revision identifies an actual source
    revision only when the caller provides it.
    """
    if isinstance(spec, Scenario):
        spec = spec.as_dict()
    _fields(spec, {"schema_version", "scenario_id", "actors", "seed", "variant", "actions"},
            set(), "scenario")
    if spec["schema_version"] != SCHEMA_VERSION:
        raise ScenarioError("unsupported scenario schema version")
    scenario_id = _name(spec["scenario_id"], "scenario_id")
    seed = _int(spec["seed"], "seed", high=U32)
    if spec["variant"] not in ("boot_live", "dma_only"):
        raise ScenarioError("unknown allocation variant")
    actors = spec["actors"]
    if not isinstance(actors, list) or not actors or any(
            not isinstance(actor, str) for actor in actors) or len(actors) != len(set(actors)):
        raise ScenarioError("actors must be a nonempty unique list")
    for actor in actors:
        _name(actor, "actor")
    if source_revision is not None and (not isinstance(source_revision, str) or
                                        not re.fullmatch(r"[0-9a-f]{40}", source_revision)):
        raise ScenarioError("source_revision must be a full 40-character lowercase SHA")
    ordered, ancestors = _ordered_actions(spec, seed)
    for a in ordered:
        if a["actor"] not in actors:
            raise ScenarioError(f"{a['action_instance_id']}: undeclared actor {a['actor']}")
    try:
        regions = configured_regions(config, profile=spec["variant"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ScenarioError(f"invalid SoC memory configuration: {exc}") from exc
    allocations = _validate_memory(ordered, ancestors, regions, config)
    for action in ordered:
        action["depends_on"] = list(action["depends_on"])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "soc_scenario_intent_only",
        "scenario_id": scenario_id,
        "seed": seed,
        "variant": spec["variant"],
        "actors": sorted(actors),
        "provenance": {
            "resolver_version": 1,
            "random_algorithm": RANDOM_ALGORITHM,
            "spec_sha256": _digest(spec),
            "soc_config_sha256": _digest(config),
            "source_revision": source_revision,
            "simulator": None,
        },
        "regions": [{"name": r.name, "kind": r.kind, "base": r.base,
                     "modeled_bytes": r.capacity, "cpu_visible": r.cpu_visible}
                    for r in sorted(regions.values(), key=lambda r: r.name)],
        "allocations": allocations,
        "actions": ordered,
        "execution_evidence": None,
    }
