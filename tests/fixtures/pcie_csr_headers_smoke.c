/* Compile against the actual PeakRDL/SystemRDL-generated PCIe CPU CSR header.
 * This is an ABI/type check, not proof of a CPU/Config-NoC register access.
 */
#include "soc_pcie_ep_prelink_regs.h"

_Static_assert(SOC_PCIE_EP_CTRL_BASE == UINT32_C(0x40040000), "bad CPU Config NoC base");
_Static_assert(SOC_PCIE_EP_BAR0_APERTURE_OFFSET == UINT32_C(0x1000), "reserved requester overlap");
_Static_assert(SOC_PCIE_EP_BAR0_TARGET_OFFSET == UINT32_C(0x1004), "target offset");
_Static_assert(SOC_PCIE_EP_CONTROL_OFFSET == UINT32_C(0x1008), "control offset");
_Static_assert(SOC_PCIE_EP_STATUS_OFFSET == UINT32_C(0x100c), "status offset");
_Static_assert(SOC_PCIE_EP_CONTROL_COMMIT_MASK == UINT32_C(1), "commit field");
_Static_assert(SOC_PCIE_EP_CONTROL_START_MASK == UINT32_C(2), "start field");
_Static_assert(SOC_PCIE_EP_STATUS_MEM_READY_MASK == UINT32_C(4), "memory-ready field");
_Static_assert(SOC_PCIE_EP_STATUS_VIOLATION_MASK == UINT32_C(8), "violation field");

/* For real RV32I firmware: use volatile 32-bit frontdoor MMIO, never
 * a simulation backdoor; CPU0 firmware and Config-NoC attachment still TODO.
 */
static inline volatile uint32_t *pcie_ep_csr(void) {
    return (volatile uint32_t *)(uintptr_t)SOC_PCIE_EP_CTRL_BASE;
}
uint32_t soc_pcie_ep_stub_read_status(void) {
    return pcie_ep_csr()[SOC_PCIE_EP_STATUS_OFFSET / 4u];
}
