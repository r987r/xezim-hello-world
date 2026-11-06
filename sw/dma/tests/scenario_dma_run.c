/* SCN-2: real PicoRV32 C consumes generated scenario_dma_contract.h.
 * This file is selected ONLY by opt-in CPU scenario regressions; normal
 * CPU DMA / PCIe / Ethernet firmware remains completely unchanged.
 *
 * The same action-level physical addresses, byte recipe and length drive
 * the reset-isolated cocotb BFM executor through a separate adapter.
 */
#include "../dma.h"
#include "../../common/memory_pool.h"
#include "../../common/memory_pattern.h"
#include "../../common/test_flow.h"
#include "scenario_dma_contract.h"
#include <stdint.h>

#ifndef SOC_CPU0_SRAM
#error "SoC SRAM base missing"
#endif
#ifndef SOC_DDR_BASE
#error "SoC DDR base missing"
#endif
#ifndef SOC_DMA0_CSR
#error "SoC DMA CSR missing"
#endif
#ifndef SOC_MODEL_BYTES
#error "SoC model bound missing"
#endif
#ifndef SOC_MAILBOX
#error "SoC mailbox missing"
#endif

#define SOURCE_OFF 0x2000u
#define DESC_OFF 0x1000u
#define STATUS_OFFSET 0x40u
#define FLOW_OFFSET 0x5cu

static bool check_writeback(const soc_dma_chain_t *chain) {
    volatile const uint64_t *done =
        (volatile const uint64_t *)(const void *)&chain->cpu_descs[0];
    return *done == UINT64_MAX;
}

static bool acknowledge_ready(volatile uint32_t *csr) {
    soc_dma_mmio_ack_irq(csr);
    for (unsigned n=0; n<10000u; ++n) {
        if (!(csr[SOC_DMA_REG_STATUS/4u] &
            (SOC_DMA_STATUS_IRQ | SOC_DMA_STATUS_APB_BUSY))) return true;
    }
    return false;
}

__attribute__((used, noinline))
int cpu_dma_run(void) {
    volatile uint32_t * const evidence =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + STATUS_OFFSET);
    volatile uint32_t * const flow =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + FLOW_OFFSET);
    volatile uint32_t * const telemetry = evidence + 1;
    *evidence = 0xd0000000u;
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 101);
    soc_mem_region_t pool, ddr;
    soc_mem_allocation_t source={0}, returned={0}, dst={0};
    soc_dma_arena_t desc;
    if (!soc_mem_region_init(&pool, "compute0.sram.payload", SOC_MEM_SRAM,
            (uint64_t)SOC_SCN_SRC_POOL_PHYS, 0x2000u,
            (void *)(uintptr_t)SOC_SCN_SRC_POOL_PHYS) ||
        !soc_mem_region_init(&ddr, "memory0.ddr0", SOC_MEM_DDR,
            (uint64_t)SOC_SCN_DDR_POOL_PHYS,
            SOC_MODEL_BYTES - 0x100u, NULL) ||
        !soc_dma_arena_init(&desc,
            (void *)(uintptr_t)(SOC_CPU0_SRAM + DESC_OFF),
            (uint64_t)SOC_CPU0_SRAM + DESC_OFF, 4096u) ||
        !soc_mem_alloc(&pool, SOC_SCN_LENGTH, 64, &source) ||
        !soc_mem_alloc(&pool, SOC_SCN_LENGTH, 64, &returned) ||
        !soc_mem_alloc(&ddr, SOC_SCN_LENGTH, 64, &dst)) {
        *evidence = 0xd0000020u; return 32;
    }
    if (source.phys != SOC_SCN_SOURCE_PHYS ||
        returned.phys != SOC_SCN_RETURN_PHYS ||
        dst.phys != SOC_SCN_DDR_PHYS) {
        *evidence = 0xd0000021u; return 33;
    }
    /* These six stores are *actual CPU AXI* mailbox telemetry. */
    telemetry[0] = (uint32_t)source.phys;
    telemetry[1] = (uint32_t)returned.phys;
    telemetry[2] = (uint32_t)dst.phys;
    telemetry[3] = (uint32_t)(dst.phys >> 32);
    telemetry[4] = 0;
    telemetry[5] = 0;
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 101);
    /* Only a mapped CPU SRAM is initialized via real C stores. */
    soc_mem_fill_pattern(source.cpu_ptr, source.phys, SOC_SCN_LENGTH,
                         SOC_SCN_SEED, SOC_PATTERN_CONSTANT);
    /* Return SRAM is intentionally uninitialized until the real DMA writes it. */

    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 102);
    volatile uint32_t * const csr =
        (volatile uint32_t *)(uintptr_t)SOC_DMA0_CSR;
    soc_dma_copy_t ops[1] = {
        {source.phys, dst.phys, (uint32_t)SOC_SCN_LENGTH}
    };
    soc_dma_chain_t chain={0};
    uint32_t status=0;
    if (!soc_dma_chain_build(&desc, ops, 1, true, &chain) ||
        !soc_dma_mmio_submit(csr, chain.head_phys) ||
        !soc_dma_mmio_wait_irq(csr, 200000u, &status) ||
        !check_writeback(&chain) || !acknowledge_ready(csr)) {
        *evidence = 0xd0000022u; return 34;
    }
    soc_dma_copy_t reverse[1] = {
        {dst.phys, returned.phys, (uint32_t)SOC_SCN_LENGTH}
    };
    if (!soc_dma_chain_build(&desc, reverse, 1, true, &chain) ||
        !soc_dma_mmio_submit(csr, chain.head_phys) ||
        !soc_dma_mmio_wait_irq(csr, 200000u, &status) ||
        !check_writeback(&chain) || !acknowledge_ready(csr)) {
        *evidence = 0xd0000023u; return 35;
    }
    /* Checked against original source recipe, not a DDR-address recipe. */
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 103);
    if (soc_mem_check_pattern(returned.cpu_ptr, source.phys,
                              SOC_SCN_LENGTH, SOC_SCN_SEED,
                              SOC_PATTERN_CONSTANT) != SOC_SCN_LENGTH) {
        *evidence = 0xd0000024u; return 36;
    }
    /* Deliberately retain allocations after confirmed C completion;
     * no early free while the NoC could still have outstanding traffic.
     */
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 103);
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 102);
    *evidence = 0x600dc0deu;
    return 0;
}
