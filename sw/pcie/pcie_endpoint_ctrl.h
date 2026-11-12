/* CPU0-side PCIe endpoint DBI frontdoor, not the host's Type-0 config space.
 * All offsets/bit masks and absolute SoC base come from the SINGLE
 * SystemRDL-generated soc_pcie_ep_prelink_regs.h header. Do not copy numbers.
 *
 * This API is prepared for the opt-in real Config-NoC/PeakRDL variant.
 * It is not yet linked into actual CPU0 firmware or an AXI frontdoor.
 * The host alone owns the assigned bus BAR0 and COMMAND.MSE values.
 */
#ifndef SOC_PCIE_ENDPOINT_CTRL_H_
#define SOC_PCIE_ENDPOINT_CTRL_H_
#include <stdbool.h>
#include <stdint.h>
#include "soc_pcie_ep_prelink_regs.h"

typedef struct {
    uint32_t host_bar0_bus_base;
    bool host_memory_space_enabled;
    uint32_t link_status;
} soc_pcie_ep_host_state;

static inline void soc_pcie_ep_mmio_fence(void) {
#if defined(__riscv)
    __asm__ volatile("fence iorw, iorw" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}

static inline volatile uint32_t *soc_pcie_ep_dbi(void) {
    return (volatile uint32_t *)(uintptr_t)SOC_PCIE_EP_CTRL_BASE;
}

static inline uint32_t soc_pcie_ep_read_status(volatile uint32_t *regs) {
    return regs[SOC_PCIE_EP_STATUS_OFFSET / 4u];
}

/* Poll only actual CPU Config-NoC frontdoor reads, not a backdoor deposit.
 * Hardware checks SRAM bounds, aperture alignment and freeze on COMMIT.
 * Return false on any reported violation or exhausted poll budget.
 */
static inline bool soc_pcie_ep_configure(volatile uint32_t *regs,
                                         uint32_t aperture_bytes,
                                         uint32_t local_target,
                                         uint32_t max_polls) {
    if (!regs || !max_polls || aperture_bytes < 4096u ||
        aperture_bytes > 1048576u ||
        (aperture_bytes & (aperture_bytes - 1u)) != 0u ||
        (local_target & (aperture_bytes - 1u)) != 0u)
        return false;
    regs[SOC_PCIE_EP_BAR0_APERTURE_OFFSET / 4u] = aperture_bytes;
    regs[SOC_PCIE_EP_BAR0_TARGET_OFFSET / 4u] = local_target;
    soc_pcie_ep_mmio_fence();
    regs[SOC_PCIE_EP_CONTROL_OFFSET / 4u] =
        SOC_PCIE_EP_CONTROL_COMMIT_MASK;
    soc_pcie_ep_mmio_fence();
    bool committed = false;
    for (uint32_t i = 0; i < max_polls; ++i) {
        uint32_t status = soc_pcie_ep_read_status(regs);
        if (status & SOC_PCIE_EP_STATUS_VIOLATION_MASK) return false;
        if (status & SOC_PCIE_EP_STATUS_COMMITTED_MASK) {
            committed = true;
            break;
        }
    }
    if (!committed) return false;
    regs[SOC_PCIE_EP_CONTROL_OFFSET / 4u] =
        SOC_PCIE_EP_CONTROL_START_MASK;
    soc_pcie_ep_mmio_fence();
    for (uint32_t i = 0; i < max_polls; ++i) {
        uint32_t status = soc_pcie_ep_read_status(regs);
        if (status & SOC_PCIE_EP_STATUS_VIOLATION_MASK) return false;
        if (status & SOC_PCIE_EP_STATUS_LTSSM_ALLOWED_MASK) return true;
    }
    return false;
}

/* Direct read-only DBI aliases of the ORIGINAL host-initiated PCIe config
 * state, not a separate C-programmable BAR0 or memory-enable register.
 * Call after the host's real PCIe configuration sequence has completed.
 */
static inline soc_pcie_ep_host_state
soc_pcie_ep_read_host_state(volatile uint32_t *regs) {
    soc_pcie_ep_host_state result = {0};
    if (!regs) return result;
    result.host_bar0_bus_base =
        regs[SOC_PCIE_EP_HOST_BAR0_OFFSET / 4u] &
        SOC_PCIE_EP_HOST_BAR0_PCI_BUS_BASE_MASK;
    result.host_memory_space_enabled =
        (regs[SOC_PCIE_EP_HOST_COMMAND_OFFSET / 4u] &
         SOC_PCIE_EP_HOST_COMMAND_MEMORY_SPACE_ENABLE_MASK) != 0;
    result.link_status = regs[SOC_PCIE_EP_LINK_STATUS_OFFSET / 4u];
    return result;
}
#endif /* SOC_PCIE_ENDPOINT_CTRL_H_ */
