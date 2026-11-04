"""Generated LiteDRAM AXI/control port contract; memory-subsystem-only."""
import re

CORE_NAME = "soc_ddr4_sim"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


AXI_SIGNALS = {
    "awvalid": 1, "awready": 1, "awburst": 2, "awlen": 8,
    "awsize": 3, "awid": 4,
    "wvalid": 1, "wready": 1, "wlast": 1, "wstrb": 8, "wdata": 64,
    "bvalid": 1, "bready": 1, "bresp": 2, "bid": 4,
    "arvalid": 1, "arready": 1, "arburst": 2, "arlen": 8,
    "arsize": 3, "arid": 4,
    "rvalid": 1, "rready": 1, "rlast": 1, "rresp": 2,
    "rdata": 64, "rid": 4,
}

# Direction is from the perspective of the generated LiteDRAM module.
# Check each AXI channel's ready/valid polarity rather than accepting any
# declaration with a matching name and width.
AXI_OUTPUT_SIGNALS = frozenset((
    "awready", "wready", "bvalid", "bresp", "bid", "arready",
    "rvalid", "rlast", "rresp", "rdata", "rid",
))


# Controls/initialization are explicit: cpu:null exposes Wishbone to
# an external test master and does not autonomously initialize the controller.
# Names/directions follow pinned LiteX Wishbone Interface.get_ios/connect_to_pads.
CONTROL_SIGNALS = {
    "clk": ("input", 1),
    "init_done": ("output", 1), "init_error": ("output", 1),
    "wb_ctrl_cyc": ("input", 1), "wb_ctrl_stb": ("input", 1),
    "wb_ctrl_we": ("input", 1), "wb_ctrl_ack": ("output", 1),
    "wb_ctrl_adr": ("input", None),
    "wb_ctrl_dat_w": ("input", 32),
    "wb_ctrl_dat_r": ("output", 32),
    "wb_ctrl_sel": ("input", 4),
    "wb_ctrl_cti": ("input", 3),
    "wb_ctrl_bte": ("input", 2),
    "wb_ctrl_err": ("output", 1),
    "user_clk": ("output", 1),
    "user_rst": ("output", 1),
}


def _generated_port(header: str, name: str) -> tuple[str, int]:
    # Migen emits ANSI top-level ports; do not search the entire Verilog file
    # (internal wires can otherwise conceal a missing module port).
    match = re.search(
        r"\b(?P<direction>input|output|inout)\s+"
        r"(?:(?:wire|reg|logic|signed)\s+)*"
        r"(?:\[\s*(?P<upper>\d+)\s*:\s*(?P<lower>\d+)\s*\]\s+)?"
        + re.escape(name) + r"\b", header,
    )
    require(match is not None, f"missing generated port {name}")
    upper, lower = match.group("upper", "lower")
    width = abs(int(upper) - int(lower)) + 1 if upper is not None else 1
    return match.group("direction"), width


def emitted_port_widths(verilog: str, module: str = CORE_NAME,
                        expected_address_bits: int | None = None) -> dict[str, int]:
    start = re.search(r"\bmodule\s+" + re.escape(module) + r"\s*\(", verilog)
    require(start is not None, f"missing generated top module: {module}")
    end = verilog.find(");", start.end())
    require(end >= 0, f"incomplete Verilog port header: {module}")
    header = verilog[start.end():end]
    found: dict[str, int] = {}
    for short, expected_width in AXI_SIGNALS.items():
        name = f"user_port_axi_0_{short}"
        direction, width = _generated_port(header, name)
        expected_dir = "output" if short in AXI_OUTPUT_SIGNALS else "input"
        require(direction == expected_dir,
                f"{name}: expected {expected_dir}, generated {direction}")
        require(width == expected_width,
                f"{name}: expected {expected_width}-bit pin, generated {width}-bit pin")
        found[name] = width
    address_widths = []
    for short in ("awaddr", "araddr"):
        name = f"user_port_axi_0_{short}"
        direction, width = _generated_port(header, name)
        require(direction == "input", f"{name}: expected input, generated {direction}")
        require(1 <= width <= 64, f"generated {name} has invalid width {width}")
        address_widths.append(width)
        found[name] = width
    require(address_widths[0] == address_widths[1],
            "read and write AXI addresses have different widths")
    if expected_address_bits is not None:
        require(address_widths[0] == expected_address_bits,
                f"LiteDRAM local AXI address width: expected {expected_address_bits}, "
                f"generated {address_widths[0]}")
    for name, (direction, width) in CONTROL_SIGNALS.items():
        actual_dir, actual_width = _generated_port(header, name)
        require(actual_dir == direction,
                f"{name}: expected {direction}, generated {actual_dir}")
        if width is not None:
            require(actual_width == width,
                    f"{name}: expected {width}-bit control pin, generated {actual_width}")
        found[name] = actual_width
    # LiteDRAM's --sim CRG is clock-only and does not consume the physical
    # pad "rst"; Migen therefore drops that input from the generated top.
    # Keep the exported user_rst and PHY init handshake mandatory above.
    if re.search(r"\b(?:input|output|inout)\s+(?:(?:wire|reg|logic)\s+)*rst\b", header):
        actual_dir, actual_width = _generated_port(header, "rst")
        require((actual_dir, actual_width) == ("input", 1),
                f"rst: unexpected simulation reset port {actual_dir}[{actual_width}]")
        found["rst"] = actual_width
    return found
