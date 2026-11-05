"""Fail-closed adapter for an *eventual* simulator-provided RTL memory hook.

Never discovers hierarchical paths, modifies SRAM or claims a valid backdoor.
The agent must bind real simulator read/write callbacks to an actual mapped
RTL array, then validate using existing CombinedMemoryProvider plus AXI.
"""
from tools.memory_service import MemoryAccessError


class RtlMemoryWindow:
    """Backdoor-only view over an explicitly injected async simulator API."""

    def __init__(self, base, size, *, read_hook=None, write_hook=None,
                 quiescent=None, implementation="not_bound"):
        if type(base) is not int or type(size) is not int or base < 0 or size < 1 or base + size > 1 << 64:
            raise ValueError("invalid 64-bit physical memory aperture")
        self.base = base
        self.size = size
        self.read_hook = read_hook
        self.write_hook = write_hook
        self.quiescent = quiescent
        self.implementation = implementation
        self.frontdoor_available = False
        self.validated_backdoor = False

    def _range(self, phys, size):
        if type(phys) is not int or type(size) is not int or size < 0 or phys < self.base:
            raise MemoryAccessError("invalid RTL backdoor range")
        off = phys - self.base
        if off > self.size or size > self.size - off:
            raise MemoryAccessError("RTL backdoor crosses modeled memory window")
        if self.read_hook is None or self.write_hook is None or self.quiescent is None:
            raise MemoryAccessError("RTL simulator hooks not bound")
        if not self.quiescent():
            raise MemoryAccessError("RTL memory not quiescent: unsafe backdoor operation")
        return off

    async def backdoor_read(self, phys, length):
        off = self._range(phys, length)
        data = await self.read_hook(off, length)
        if not isinstance(data, (bytes, bytearray)) or len(data) != length:
            raise MemoryAccessError("RTL backdoor read returned incomplete byte count")
        return bytes(data)

    async def backdoor_write(self, phys, data):
        if not isinstance(data, bytes):
            raise MemoryAccessError("RTL backdoor expects bytes")
        off = self._range(phys, len(data))
        await self.write_hook(off, data)

    async def frontdoor_read(self, phys, length):
        raise MemoryAccessError("RTL memory hooks are not an AXI frontdoor")

    async def frontdoor_write(self, phys, data):
        raise MemoryAccessError("RTL memory hooks are not an AXI frontdoor")
