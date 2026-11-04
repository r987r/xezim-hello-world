#include "sram_pool.h"

/* Legacy API delegates to the common multi-space physical allocator. */
bool soc_sram_pool_init(soc_sram_pool_t *pool, void *cpu_base,
                        uint64_t phys_base, size_t capacity) {
    if (!cpu_base) return false;
    return soc_mem_region_init(pool, "sram", SOC_MEM_SRAM,
                               phys_base, capacity, cpu_base);
}
bool soc_sram_pool_alloc(soc_sram_pool_t *pool, size_t bytes, size_t alignment,
                         void **cpu_out, uint64_t *phys_out) {
    soc_mem_allocation_t a = {0};
    if (!cpu_out || !phys_out || !pool || !pool->cpu_base ||
        !soc_mem_alloc(pool, bytes, alignment, &a))
        return false;
    *cpu_out = a.cpu_ptr;
    *phys_out = a.phys;
    return true;
}
bool soc_sram_pool_reset(soc_sram_pool_t *pool, bool users_quiesced) {
    return pool && pool->cpu_base && soc_mem_reset(pool, users_quiesced);
}
bool soc_sram_pool_reclaim_boot_scratch(soc_sram_pool_t *pool,
                                        bool boot_check_complete,
                                        bool users_quiesced) {
    return boot_check_complete && soc_sram_pool_reset(pool, users_quiesced);
}
