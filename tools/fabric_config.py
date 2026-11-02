"""Validate backend-native fabric knobs and AXI4 memory reachability.

No RTL is implemented here: this module translates named YAML endpoints into
parameters of the *upstream* verilog-axi crossbar. Other NoC emitters remain
explicitly unavailable until integrated and verified.
"""
from __future__ import annotations


class FabricConfigError(ValueError):
    pass


# Verilog-AXI axi_crossbar parameters; counts/address map/ID widths are derived
# from the architecture and deliberately cannot be overridden by these knobs.
# Each parameter can be a scalar, ordered list, or a map keyed by port name.
# Values are packed with port 0 in the least significant field.
S_PARAMETER_WIDTHS = {
    "S_THREADS": (32, 1, 256),
    "S_ACCEPT": (32, 1, 256),
    "S_AW_REG_TYPE": (2, 0, 2),
    "S_W_REG_TYPE": (2, 0, 2),
    "S_B_REG_TYPE": (2, 0, 2),
    "S_AR_REG_TYPE": (2, 0, 2),
    "S_R_REG_TYPE": (2, 0, 2),
}
M_PARAMETER_WIDTHS = {
    "M_ISSUE": (32, 1, 256),
    "M_AW_REG_TYPE": (2, 0, 2),
    "M_W_REG_TYPE": (2, 0, 2),
    "M_B_REG_TYPE": (2, 0, 2),
    "M_AR_REG_TYPE": (2, 0, 2),
    "M_R_REG_TYPE": (2, 0, 2),
}


def _int(value, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise FabricConfigError(f"{label} must be an integer in [{low}, {high}]")
    return value


def _port_values(value, names: list[str], name: str, lo: int, hi: int) -> list[int]:
    if type(value) is int:
        vals = [value] * len(names)
    elif isinstance(value, list):
        if len(value) != len(names):
            raise FabricConfigError(f"{name}: expected {len(names)} ordered port values")
        vals = value
    elif isinstance(value, dict):
        if set(value) != set(names):
            raise FabricConfigError(
                f"{name}: per-port keys must be exactly {names}; "
                f"missing={sorted(set(names)-set(value))}, unknown={sorted(set(value)-set(names))}"
            )
        vals = [value[k] for k in names]
    else:
        raise FabricConfigError(f"{name}: expected integer, list, or port-name map")
    return [_int(v, name, lo, hi) for v in vals]


def memory_parameters(raw: object, ingress: list[str], targets: list[str]) -> dict[str, list[int]]:
    """Normalize only supported upstream axi_crossbar knobs."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FabricConfigError("memory_data.parameters must be a map")
    unknown = set(raw) - set(S_PARAMETER_WIDTHS) - set(M_PARAMETER_WIDTHS)
    if unknown:
        raise FabricConfigError(f"unsupported verilog_axi parameters: {sorted(unknown)}")
    result = {}
    for key, val in raw.items():
        if key in S_PARAMETER_WIDTHS:
            _, lo, hi = S_PARAMETER_WIDTHS[key]
            result[key] = _port_values(val, ingress, key, lo, hi)
        else:
            _, lo, hi = M_PARAMETER_WIDTHS[key]
            result[key] = _port_values(val, targets, key, lo, hi)
    return dict(sorted(result.items()))


def memory_connectivity(raw: object, ingress: list[str], targets: list[str]) -> dict | None:
    """Canonical read/write reachability for axi_crossbar and its testbench.

    Masks: M_CONNECT_* use target-major bit order (target * N_IN + source).
    Agent masks use source-major bit order (source * N_MEM + target).
    Existing DV does coupled write+readback, so asymmetric access is rejected
    rather than silently skipping a test or inventing extra BFM behavior.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"read", "write"}:
        raise FabricConfigError("memory_data.connectivity requires read and write maps")
    directions = {}
    for direction in ("read", "write"):
        matrix = raw[direction]
        if not isinstance(matrix, dict) or set(matrix) != set(ingress):
            raise FabricConfigError(f"memory_data.connectivity.{direction} needs exactly these ingress names: {ingress}")
        rows = {}
        for name in ingress:
            destinations = matrix[name]
            if not isinstance(destinations, list) or not destinations:
                raise FabricConfigError(f"{direction}.{name}: nonempty target list required")
            if any(not isinstance(t, str) or t not in targets for t in destinations):
                raise FabricConfigError(f"{direction}.{name}: unknown memory target")
            if len(set(destinations)) != len(destinations):
                raise FabricConfigError(f"{direction}.{name}: duplicate memory target")
            rows[name] = [t for t in targets if t in destinations]
        if any(not any(t in row for row in rows.values()) for t in targets):
            raise FabricConfigError(f"{direction}: each memory target must be reachable")
        directions[direction] = rows
    if directions["read"] != directions["write"]:
        raise FabricConfigError("asymmetric read/write routing needs a separate DV agent; not supported yet")
    native = 0
    agent = 0
    for i, name in enumerate(ingress):
        for j, target in enumerate(targets):
            if target in directions["read"][name]:
                native |= 1 << (j * len(ingress) + i)
                agent |= 1 << (i * len(targets) + j)
    return {"read": directions["read"], "write": directions["write"],
            "native_read_mask": native, "native_write_mask": native,
            "agent_mask": agent}


def parameter_packed_literal(name: str, values: list[int]) -> str:
    """Upstream vector parameter with the first port in least-significant bits."""
    schema = S_PARAMETER_WIDTHS if name in S_PARAMETER_WIDTHS else M_PARAMETER_WIDTHS
    if name not in schema:
        raise FabricConfigError(f"unsupported crossbar parameter: {name}")
    width = schema[name][0]
    return "{" + ", ".join(f"{width}'d{x}" for x in reversed(values)) + "}"
