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
        (kind != SOC_MEM_SRAM && cpu_base != NULL) ||
        capacity > UINT64_MAX - phys_base ||
        (cpu_base && capacity > SIZE_MAX))
        return false;
    *r = (soc_mem_region_t){.name=name, .kind=kind,
       .phys_base=phys_base, .capacity=capacity, .cpu_base=(uint8_t *)cpu_base,
       .used=0, .next_token=1, .top_token=0, .generation=1};
    return true;
}

bool soc_mem_alloc(soc_mem_region_t *r, uint64_t bytes, uint64_t alignment,
                   soc_mem_allocation_t *out) {
    if (!r || !r->name || !r->capacity || !out || !bytes ||
        !power_of_two(alignment) || r->used > r->capacity ||
        r->next_token == UINT64_MAX ||
        alignment - 1u > UINT64_MAX - r->phys_base)
        return false;
    if (r->cpu_base &&
        (((uintptr_t)r->cpu_base ^ (uintptr_t)r->phys_base) &
         (uintptr_t)(alignment - 1u)))
        return false;
    if (r->used > UINT64_MAX - r->phys_base) return false;
    uint64_t current = r->phys_base + r->used;
    if (current > UINT64_MAX - (alignment - 1u)) return false;
    uint64_t address = (current + alignment - 1u) & ~(alignment - 1u);
    uint64_t offset = address - r->phys_base;
    if (offset > r->capacity || bytes > r->capacity - offset)
        return false;
    if (r->cpu_base && (offset > SIZE_MAX || bytes > SIZE_MAX - (size_t)offset))
        return false;
    *out = (soc_mem_allocation_t){
        .phys=address, .bytes=bytes, .previous_used=r->used,
        .cpu_ptr=r->cpu_base ? r->cpu_base + (size_t)offset : NULL,
        .generation=r->generation, .token=r->next_token,
        .previous_token=r->top_token
    };
    r->used = offset + bytes;
    r->top_token = r->next_token++;
    return true;
}

bool soc_mem_release(soc_mem_region_t *r, const soc_mem_allocation_t *a,
                     bool consumers_quiesced) {
    if (!r || !a || !consumers_quiesced || a->generation != r->generation ||
        !a->token || a->token != r->top_token ||
        !a->bytes || a->phys < r->phys_base || a->previous_used > r->used)
        return false;
    uint64_t offset = a->phys - r->phys_base;
    if (offset > r->capacity || a->bytes > r->capacity - offset ||
        offset + a->bytes != r->used || a->previous_used > offset ||
        a->cpu_ptr != (r->cpu_base ? (void *)(r->cpu_base + (size_t)offset) : NULL))
        return false;
    r->used = a->previous_used;
    r->top_token = a->previous_token;
    return true;
}

bool soc_mem_reset(soc_mem_region_t *r, bool consumers_quiesced) {
    if (!r || !r->name || !consumers_quiesced || r->generation == UINT32_MAX)
        return false;
    r->used = 0;
    r->top_token = 0;
    r->generation++;
    return true;
}
