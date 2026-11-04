"""NoC implementation plugin interface. Architecture is independent of vendors.

A backend consumes the normalized fabric connectivity/address-map IR and emits
implementation-specific RTL and source lists. Only verilog_axi memory crossbar
has an executable backend in this milestone; other selections are preserved
in the IR so their generators can be plugged in without changing soc.yaml.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FabricImplementation:
    name: str
    module: str
    source: str
    executable: bool
    comment: str


BACKENDS = {
    "verilog_axi": FabricImplementation("verilog_axi", "axi_crossbar", "alexforencich/verilog-axi", True, "AXI4 crossbar"),
    "pulp_axi": FabricImplementation("pulp_axi", "axi_xbar", "pulp-platform/axi", False, "Requires PULP package/typedef generation"),
    "floonoc": FabricImplementation("floonoc", "floo_noc", "pulp-platform/FlooNoC", False, "Shared NoC/BFM and CPU boot-configuration emitters exist; general SoC/iDMA/controller integration remains pending"),
}


class BackendError(ValueError):
    pass


def get_backend(name: str, *, require_executable: bool = False) -> FabricImplementation:
    try:
        backend = BACKENDS[name]
    except KeyError as exc:
        raise BackendError(f"unknown NoC backend: {name}") from exc
    if require_executable and not backend.executable:
        raise BackendError(f"No RTL generator implemented yet for backend '{name}': {backend.comment}")
    return backend


def emit_memory_crossbar_parameters(name: str, parameters: list[str]) -> tuple[str, list[str]]:
    """Backend-specific crossbar instantiation; bus wiring is vendor-neutral."""
    impl = get_backend(name, require_executable=True)
    if impl.name != "verilog_axi":
        raise BackendError(f"backend '{name}' needs an emitter")
    return impl.module, parameters
