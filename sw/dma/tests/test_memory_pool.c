#include "../../common/memory_pool.h"
#include "../../common/sram_pool.h"
#include "../dma/dma.h"
#include <assert.h>
#include <stdio.h>
#include <stdint.h>

static _Alignas(64) unsigned char local_sram[8192];
int main(void) {
    soc_mem_region_t src, ddr, hbm;
    soc_mem_allocation_t a={0}, b={0}, c={0}, reused={0};
    assert(soc_mem_region_init(&src, "compute0.payload", SOC_MEM_SRAM,
                               0x10002000u, sizeof(local_sram), local_sram));
    assert(soc_mem_region_init(&ddr, "memory0.ddr0", SOC_MEM_DDR,
                               0x140000100ull, 65536u-256u, NULL));
    assert(soc_mem_region_init(&hbm, "memory0.hbm0", SOC_MEM_HBM,
                               0x100000100ull, 65536u-256u, NULL));
    assert(!soc_mem_region_init(&hbm, "invalid", SOC_MEM_HBM, 0, 1024, local_sram));
    assert(soc_mem_region_init(&hbm, "memory0.hbm0", SOC_MEM_HBM,
                               0x100000100ull, 65536u-256u, NULL));
    assert(soc_mem_alloc(&src, 64, 64, &a));
    assert(a.cpu_ptr == local_sram && a.phys == 0x10002000u);
    assert(soc_mem_alloc(&ddr, 64, 64, &b));
    assert(b.cpu_ptr == NULL && b.phys == 0x140000100ull);
    assert(soc_mem_alloc(&hbm, 64, 64, &c));
    assert(c.cpu_ptr == NULL && c.phys == 0x100000100ull);
    assert(!soc_mem_alloc(&ddr, 32, 3, &reused)); /* alignment power of two */
    assert(!soc_mem_alloc(&ddr, 65536, 64, &reused)); /* model cap */
    assert(soc_mem_alloc(&ddr, 32, 64, &reused));
    assert(reused.phys == 0x140000140ull);
    assert(!soc_mem_release(&ddr, &b, true)); /* not top-of-stack */
    assert(!soc_mem_release(&ddr, &reused, false)); /* DMA still running */
    assert(soc_mem_release(&ddr, &reused, true));
    assert(!soc_mem_release(&ddr, &reused, true)); /* double-free */
    assert(soc_mem_alloc(&ddr, 32, 64, &reused)); /* same address; new token */
    assert(reused.phys == 0x140000140ull);
    assert(soc_mem_release(&ddr, &reused, true));
    assert(soc_mem_release(&ddr, &b, true));
    assert(!soc_mem_release(&ddr, &b, true));
    assert(!soc_mem_reset(&src, false));
    assert(soc_mem_reset(&src, true));
    assert(!soc_mem_release(&src, &a, true)); /* old generation */
    assert(soc_mem_alloc(&src, 64, 64, &a));
    assert(!soc_mem_alloc(&src, UINT64_MAX, 64, &reused));
    assert(!soc_mem_region_init(&ddr, "overflow", SOC_MEM_DDR,
                                UINT64_MAX-7, 16, NULL));
    assert(!soc_mem_region_init(&ddr, "", SOC_MEM_DDR, 0, 16, NULL));
    assert(!soc_mem_region_init(&ddr, "bad", (soc_mem_kind_t)9, 0, 16, NULL));
    assert(soc_mem_release(&hbm, &c, true));

    /* The existing DMA descriptor ABI also consumes the common allocator. */
    soc_sram_pool_t desc;
    soc_dma_chain_t chain={0};
    soc_dma_copy_t op={0x10002000u, 0x140000100ull, 64};
    assert(soc_sram_pool_init(&desc, local_sram, 0x10001000u, sizeof(local_sram)));
    assert(soc_dma_chain_build(&desc, &op, 1, true, &chain));
    assert(chain.head_phys == 0x10001000u);
    assert(chain.cpu_descs[0].dst_addr == b.phys);
    assert(!soc_dma_arena_reset(&desc, false));
    assert(soc_dma_arena_reset(&desc, true));
    puts("PASS unified SRAM DDR HBM physical allocation and lifetime");
    return 0;
}
