#include "memory_pool.h"
#include <limits.h>

static bool power_of_two(uint64_t n) {
    return n && !(n & (n - 1u));
}

bool soc_mem_region_init(soc_mem_region_t *r, const char *name,
                         soc_mem_kind_t kind, uint64_t phys_base,
                         uint64_t capacity, void *cpu_base) {
    if (!r || !name || !*name || !capacity ||
        (kind != SOC_MEM_SRAM && kind != SOC_MEM_DDR && kind != SOC_MEM_HBM) ||
        capacity > UINT64_MAX - phys_base ||
        (cpu_base && capacity > SIZE_MAX))
        return false;
    *r = (soc_mem_region_t){name, kind, phys_base, capacity,
                            (uint8_t *)cpu_base, 0, 1};
    return true;
}

bool soc_mem_alloc(soc_mem_region_t *r, uint64_t bytes, uint64_t alignment,
                   soc_mem_allocation_t *out) {
    if (!r || !r->name || !r->capacity || !out || !bytes ||
        !power_of_two(alignment) || r->used > r->capacity ||
        alignment - 1u > UINT64_MAX - r->phys_base)
        return false;
    if (r->cpu_base &&
        (((uintptr_t)r->cpu_base ^ (uintptr_t)r->phys_base) &
         (uintptr_t)(alignment - 1u)))
        return false;
    uint64_t current = r->phys_base + r->used;
    if (current < r->phys_base || current > UINT64_MAX - (alignment - 1u))
        return false;
    uint64_t address = (current + alignment - 1u) & ~(alignment - 1u);
    uint64_t offset = address - r->phys_base;
    if (offset > r->capacity || bytes > r->capacity - offset)
        return false;
    if (r->cpu_base && (offset > SIZE_MAX || bytes > SIZE_MAX - (size_t)offset))
        return false;
    *out = (soc_mem_allocation_t){
        address, bytes, r->used,
        r->cpu_base ? r->cpu_base + (size_t)offset : NULL, r->generation
    };
    r->used = offset + bytes;
    return true;
}

bool soc_mem_release(soc_mem_region_t *r, const soc_mem_allocation_t *a,
                     bool consumers_quiesced) {
    if (!r || !a || !consumers_quiesced || a->generation != r->generation ||
        !a->bytes || a->phys < r->phys_base || a->previous_used > r->used)
        return false;
    uint64_t offset = a->phys - r->phys_base;
    if (offset > r->capacity || a->bytes > r->capacity - offset ||
        offset + a->bytes != r->used || a->previous_used > offset ||
        a->cpu_ptr != (r->cpu_base ? (void *)(r->cpu_base + (size_t)offset) : NULL))
        return false;
    r->used = a->previous_used;
    return true;
}

bool soc_mem_reset(soc_mem_region_t *r, bool consumers_quiesced) {
    if (!r || !r->name || !consumers_quiesced || r->generation == UINT32_MAX)
        return false;
    r->used = 0;
    r->generation++;
    return true;
}
