"""Host-side PCIe BAR request/completion reference for future real RTL tests.

This is a checking oracle, NOT a PCIe Endpoint, PHY, TLP-AXI bridge or VIP.
The agent must pair it with pinned upstream real RTL and cocotbext-pcie.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Bar:
    number: int
    base: int
    size: int

    def __post_init__(self):
        if self.number not in range(6) or self.size < 4096 or self.size & (self.size - 1):
            raise ValueError("invalid BAR number/size")
        if self.base < 0 or self.base % self.size:
            raise ValueError("BAR base is not size aligned")


@dataclass(frozen=True)
class Request:
    tag: int
    address: int
    length: int
    write: bool
    first_be: int = 0xf
    last_be: int = 0xf

    def __post_init__(self):
        if not 0 <= self.tag < 256 or self.length <= 0 or self.length > 4096:
            raise ValueError("invalid tag/length")
        if self.address < 0 or self.address % 4 or self.length % 4:
            raise ValueError("unaligned TLP request")
        if not 0 <= self.first_be <= 15 or not 0 <= self.last_be <= 15:
            raise ValueError("invalid dword byte enable")


def decode_bar(bars, request):
    hits = [bar for bar in bars if request.address >= bar.base
            and request.address + request.length <= bar.base + bar.size]
    if len(hits) != 1:
        raise ValueError("TLP must resolve to exactly one complete BAR aperture")
    return hits[0], request.address - hits[0].base


class CompletionTracker:
    """Fail closed on unknown/duplicate tags and partial completion errors."""

    def __init__(self):
        self.pending = {}

    def issue(self, request):
        if request.write:
            raise ValueError("posted writes must not expect read completions")
        if request.tag in self.pending:
            raise ValueError("duplicate outstanding PCIe tag")
        self.pending[request.tag] = request.length

    def complete(self, tag, payload, *, success=True):
        if tag not in self.pending:
            raise ValueError("completion for unknown or already retired tag")
        if not success:
            del self.pending[tag]
            raise ValueError("PCIe completion reported error")
        remaining = self.pending[tag]
        if not payload or len(payload) > remaining:
            raise ValueError("invalid completion length")
        remaining -= len(payload)
        if remaining:
            self.pending[tag] = remaining
            return False
        del self.pending[tag]
        return True

    def assert_drained(self):
        if self.pending:
            raise AssertionError(f"uncompleted PCIe read tags: {sorted(self.pending)}")
