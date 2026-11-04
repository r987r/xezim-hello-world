#include "sram_pool.h"
#include <stdint.h>

static bool power_of_two(size_t n) {
    return n && !(n & (n - 1));
}

bool soc_sram_pool_init(soc_sram_pool_t *pool, void *cpu_base,
                        uint64_t phys_base, size_t capacity) {
    if (!pool || !cpu_base || !capacity ||
        (uint64_t)capacity > UINT64_MAX-phys_base) return false;
    pool->cpu_base = (uint8_t *)cpu_base;
    pool->phys_base = phys_base;
    pool->capacity = capacity;
    pool->used = 0;
    return true;
}

bool soc_sram_pool_alloc(soc_sram_pool_t *pool, size_t bytes, size_t alignment,
                         void **cpu_out, uint64_t *phys_out) {
    if (!pool || !pool->cpu_base || !cpu_out || !phys_out || !bytes ||
        !power_of_two(alignment) || pool->used > pool->capacity) return false;
    if (((uintptr_t)pool->cpu_base & (alignment-1)) !=
        ((uintptr_t)pool->phys_base & (alignment-1))) return false;
    if ((uint64_t)pool->used > UINT64_MAX-pool->phys_base) return false;
    uint64_t current = pool->phys_base + (uint64_t)pool->used;
    uint64_t mask = (uint64_t)alignment - 1;
    if (current > UINT64_MAX-mask) return false;
    uint64_t aligned = (current+mask) & ~mask;
    if (aligned < pool->phys_base) return false;
    uint64_t offset = aligned - pool->phys_base;
    if (offset > pool->capacity || bytes > pool->capacity-(size_t)offset)
        return false;
    *cpu_out = pool->cpu_base+(size_t)offset;
    *phys_out = aligned;
    pool->used = (size_t)offset+bytes;
    return true;
}

bool soc_sram_pool_reset(soc_sram_pool_t *pool, bool users_quiesced) {
    if (!pool || !pool->cpu_base || !users_quiesced) return false;
    pool->used = 0;
    return true;
}

bool soc_sram_pool_reclaim_boot_scratch(soc_sram_pool_t *pool,
                                        bool boot_check_complete,
                                        bool users_quiesced) {
    return boot_check_complete && soc_sram_pool_reset(pool, users_quiesced);
}
