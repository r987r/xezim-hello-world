#include "../dma.h"
#include <assert.h>
#include <stdio.h>

static _Alignas(32) unsigned char pool[4096];

int main(void) {
    soc_dma_arena_t arena = {0};
    soc_dma_chain_t chain = {0};
    soc_dma_copy_t ops[3] = {
        {0x10002000u, 0x140000100ull, 64},
        {0x10002040u, 0x140000140ull, 17},
        {0x10002080u, 0x140000180ull, 1},
    };
    assert(soc_dma_arena_init(&arena, pool, 0x10001000, sizeof(pool)));
    assert(soc_dma_chain_build(&arena, ops, 3, true, &chain));
    assert(chain.count == 3 && chain.head_phys == 0x10001000);
    assert(arena.used == 96);
    assert(chain.cpu_descs[0].length == 64 && chain.cpu_descs[0].flags == 0xau);
    assert(chain.cpu_descs[0].next == 0x10001020);
    assert(chain.cpu_descs[2].flags == 0xbu);
    assert(chain.cpu_descs[2].next == SOC_DMA_CHAIN_END);
    assert(!soc_dma_chain_build(&arena, ops, 0, true, &chain));
    soc_dma_copy_t bad[] = {{UINT64_MAX, 0, 2}};
    assert(!soc_dma_chain_build(&arena, bad, 1, false, &chain));
    soc_dma_copy_t big_ops[129];
    for (size_t i = 0; i < 129; ++i) big_ops[i] = ops[0];
    assert(!soc_dma_chain_build(&arena, big_ops, 129, true, &chain));
    assert(arena.used == 96);
    soc_dma_publish();
    assert(!soc_dma_arena_reset(&arena, false));
    assert(soc_dma_arena_reset(&arena, true));
    assert(soc_dma_chain_build(&arena, ops, 3, false, &chain));
    assert(chain.cpu_descs[2].flags == 0xau);
    soc_sram_pool_t scratch = {0};
    assert(soc_sram_pool_init(&scratch, pool+512, 0x10001200, 512));
    void *scratch_cpu = 0;
    uint64_t scratch_phys = 0;
    assert(soc_sram_pool_alloc(&scratch, 64, 32, &scratch_cpu, &scratch_phys));
    assert(scratch_phys == 0x10001200);
    assert(!soc_sram_pool_reclaim_boot_scratch(&scratch, false, true));
    assert(!soc_sram_pool_reclaim_boot_scratch(&scratch, true, false));
    assert(soc_sram_pool_reclaim_boot_scratch(&scratch, true, true));
    assert(scratch.used == 0);
    /* Hosted fake CSR registers validate firmware MMIO access ordering and
     * basic error handling. Real CSR RTL is verified separately in chip-dma. */
    volatile uint32_t regs[4] = {0};
    assert(soc_dma_mmio_submit(regs, 0x140001000ull));
    assert(regs[SOC_DMA_REG_HEAD_LO/4u] == 0x40001000u);
    assert(regs[SOC_DMA_REG_HEAD_HI/4u] == 1u);
    assert(regs[SOC_DMA_REG_COMMAND/4u] == SOC_DMA_CMD_SUBMIT);
    assert(!soc_dma_mmio_submit(regs, 0x140001001ull));
    regs[SOC_DMA_REG_STATUS/4u] = SOC_DMA_STATUS_APB_BUSY;
    assert(!soc_dma_mmio_submit(regs, 0x140001020ull));
    regs[SOC_DMA_REG_STATUS/4u] = 0;
    uint32_t status = UINT32_MAX;
    assert(!soc_dma_mmio_wait_irq(regs, 0, &status));
    assert(status == UINT32_MAX);
    assert(!soc_dma_mmio_wait_irq(regs, 3, &status));
    assert(status == 0);
    regs[SOC_DMA_REG_STATUS/4u] = SOC_DMA_STATUS_IRQ;
    assert(!soc_dma_mmio_submit(regs, 0x140001020ull));
    assert(soc_dma_mmio_wait_irq(regs, 1, &status));
    assert(status == SOC_DMA_STATUS_IRQ);
    soc_dma_mmio_ack_irq(regs);
    assert(regs[SOC_DMA_REG_COMMAND/4u] == SOC_DMA_CMD_IRQ_ACK);
    regs[SOC_DMA_REG_STATUS/4u] = SOC_DMA_STATUS_APB_ERROR | SOC_DMA_STATUS_IRQ;
    assert(!soc_dma_mmio_wait_irq(regs, 1, &status));
    assert(status & SOC_DMA_STATUS_APB_ERROR);
    assert(!soc_dma_mmio_submit(NULL, 0x140001000ull));
    assert(!soc_dma_mmio_wait_irq(NULL, 1, &status));
    soc_dma_mmio_ack_irq(NULL);
    puts("PASS dma C descriptor allocator, chain ABI and CPU CSR driver");
    return 0;
}
