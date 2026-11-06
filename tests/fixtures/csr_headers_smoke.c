/* Compile-only RV32I contract check against the actual generated CSR headers.
 * Does not execute hardware accesses or substitute for CPU/NoC RTL tests.
 */
#include <stdint.h>
#include "soc_csr_bases.h"
#include "soc_boot_reset_ctrl_regs.h"

_Static_assert(SOC_CSR_BOOT_RESET_CTRL_BASE == UINT32_C(0x40020000),
               "reset control physical CSR base drift");
_Static_assert(SOC_BOOT_RESET_CTRL_CPU_RELEASE_OFFSET == UINT32_C(0),
               "CPU release ABI offset changed");
_Static_assert(SOC_BOOT_RESET_CTRL_SECONDARY_ACK_0_OFFSET == UINT32_C(4),
               "secondary firmware acknowledgement ABI offset changed");
_Static_assert(SOC_BOOT_RESET_CTRL_CPU_RELEASE_SECONDARY_RELEASE_MASK == UINT32_C(1),
               "two-core release bit drift");
_Static_assert(SOC_BOOT_RESET_CTRL_SECONDARY_ACK_0_ACK_MASK == UINT32_C(0xffffffff),
               "secondary acknowledgement should use a 32-bit word");

static inline volatile uint32_t *soc_reset_release_reg(void) {
    return (volatile uint32_t *)(uintptr_t)(
        SOC_CSR_BOOT_RESET_CTRL_BASE + SOC_BOOT_RESET_CTRL_CPU_RELEASE_OFFSET);
}

static inline volatile uint32_t *soc_reset_ack_reg(void) {
    return (volatile uint32_t *)(uintptr_t)(
        SOC_CSR_BOOT_RESET_CTRL_BASE + SOC_BOOT_RESET_CTRL_SECONDARY_ACK_0_OFFSET);
}

/* Only used routines generate code when referenced. */
uint32_t csr_generated_abi_smoke(void) {
    return (uint32_t)(uintptr_t)soc_reset_ack_reg()
         - (uint32_t)(uintptr_t)soc_reset_release_reg();
}
