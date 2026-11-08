#ifndef SOC_PCIE_REQUESTER_H_
#define SOC_PCIE_REQUESTER_H_
#include <stdbool.h>
#include <stdint.h>

/* Pinned PCIe outbound requester: CPU Config-NoC frontdoor only.
 * The host must publish the Root Complex DMA address (IOVA), not a BAR
 * or CPU physical address, into the agreed PCIe SRAM handshake words.
 * No direct Cocotb descriptor wire is part of this interface.
 */
enum {
    SOC_PCIE_WR_HOST_LO = 0x00, SOC_PCIE_WR_HOST_HI = 0x04,
    SOC_PCIE_WR_RAM = 0x08, SOC_PCIE_WR_LEN = 0x0c,
    SOC_PCIE_WR_TAG = 0x10, SOC_PCIE_WR_COMMAND = 0x14,
    SOC_PCIE_WR_STATUS = 0x18,
    SOC_PCIE_RD_HOST_LO = 0x20, SOC_PCIE_RD_HOST_HI = 0x24,
    SOC_PCIE_RD_RAM = 0x28, SOC_PCIE_RD_LEN = 0x2c,
    SOC_PCIE_RD_TAG = 0x30, SOC_PCIE_RD_COMMAND = 0x34,
    SOC_PCIE_RD_STATUS = 0x38, SOC_PCIE_VERSION = 0x3c
};
#define SOC_PCIE_STATUS_DONE  1u
#define SOC_PCIE_STATUS_BUSY  2u
#define SOC_PCIE_STATUS_ERROR 4u
#define SOC_PCIE_HOST_IOVA_LO_OFF 0x820u
#define SOC_PCIE_HOST_IOVA_HI_OFF 0x824u
#define SOC_PCIE_HOST_IOVA_VALID_OFF 0x828u
#define SOC_PCIE_IOVA_VALID 0x50434945u

static inline void soc_pcie_fence(void) {
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

static inline bool soc_pcie_transfer(volatile uint32_t *csr, bool read,
                                     uint64_t host_addr, uint32_t sram_offset,
                                     uint32_t length, uint32_t tag,
                                     uint32_t max_polls) {
    const unsigned base = read ? SOC_PCIE_RD_HOST_LO : SOC_PCIE_WR_HOST_LO;
    const unsigned command = read ? SOC_PCIE_RD_COMMAND : SOC_PCIE_WR_COMMAND;
    const unsigned status = read ? SOC_PCIE_RD_STATUS : SOC_PCIE_WR_STATUS;
    if (!host_addr || !length || length > 16384u ||
        sram_offset >= 16384u || length > 16384u-sram_offset ||
        tag > 255u || max_polls == 0u ||
        csr[SOC_PCIE_VERSION/4u] != 0x00760001u ||
        (csr[status/4u] & SOC_PCIE_STATUS_BUSY)) return false;

    csr[(base+0x00)/4u] = (uint32_t)host_addr;
    csr[(base+0x04)/4u] = (uint32_t)(host_addr>>32);
    csr[(base+0x08)/4u] = sram_offset;
    csr[(base+0x0c)/4u] = length;
    csr[(base+0x10)/4u] = tag;
    soc_pcie_fence();
    csr[command/4u] = 1u; /* real 32-bit MMIO doorbell over Config NoC */
    soc_pcie_fence();

    for (uint32_t i=0; i<max_polls; ++i) {
        uint32_t value = csr[status/4u];
        if (value & SOC_PCIE_STATUS_ERROR) return false;
        if ((value & (SOC_PCIE_STATUS_DONE|SOC_PCIE_STATUS_BUSY)) ==
            SOC_PCIE_STATUS_DONE)
            return ((value>>8)&255u) == tag && ((value>>16)&15u) == 0u;
    }
    return false;
}
#endif
