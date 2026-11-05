#ifndef SOC_SRAM_POOL_H_
#define SOC_SRAM_POOL_H_
#include "memory_pool.h"

/* Compatibility spelling for the existing boot/DMA code. All allocations,
 * including SRAM, share the same soc_mem_* algorithm and ownership model.
 */
typedef soc_mem_region_t soc_sram_pool_t;

bool soc_sram_pool_init(soc_sram_pool_t *pool, void *cpu_base,
                        uint64_t phys_base, size_t capacity);
bool soc_sram_pool_alloc(soc_sram_pool_t *pool, size_t bytes, size_t alignment,
                         void **cpu_out, uint64_t *phys_out);
bool soc_sram_pool_reset(soc_sram_pool_t *pool, bool users_quiesced);
bool soc_sram_pool_reclaim_boot_scratch(soc_sram_pool_t *pool,
                                        bool boot_check_complete,
                                        bool users_quiesced);
#endif
