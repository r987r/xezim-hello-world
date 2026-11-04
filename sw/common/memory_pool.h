#ifndef SOC_MEMORY_POOL_H_
#define SOC_MEMORY_POOL_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* A single physical-region allocator contract for SRAM, DDR and HBM.
 * Region metadata is CPU-owned, never stored in the target buffer.
 * Only CPU-mapped SRAM yields a usable cpu_ptr. The 32-bit CPUs cannot
 * directly dereference 64-bit DDR/HBM physical addresses.
 * LIFO retirement allows deterministic reuse without a heap or malloc.
 * Caller must serialize all CPU users and DMA users of a region.
 */
typedef enum {
    SOC_MEM_SRAM = 1,
    SOC_MEM_DDR = 2,
    SOC_MEM_HBM = 3
} soc_mem_kind_t;

typedef struct {
    const char *name;
    soc_mem_kind_t kind;
    uint64_t phys_base;
    uint64_t capacity;
    uint8_t *cpu_base;      /* NULL for inaccessible target regions */
    uint64_t used;
    uint32_t generation;
} soc_mem_region_t;

typedef struct {
    uint64_t phys;
    uint64_t bytes;
    uint64_t previous_used;
    void *cpu_ptr;          /* NULL for physical-only memory */
    uint32_t generation;
} soc_mem_allocation_t;

bool soc_mem_region_init(soc_mem_region_t *region, const char *name,
                         soc_mem_kind_t kind, uint64_t phys_base,
                         uint64_t capacity, void *cpu_base);
bool soc_mem_alloc(soc_mem_region_t *region, uint64_t bytes, uint64_t alignment,
                   soc_mem_allocation_t *out);
/* A safe free of the most recent allocation only; an active DMA means false.
 * Stale handles and out-of-order frees are rejected.
 */
bool soc_mem_release(soc_mem_region_t *region, const soc_mem_allocation_t *allocation,
                     bool consumers_quiesced);
/* Full-region reset is permitted only after all users are quiescent. */
bool soc_mem_reset(soc_mem_region_t *region, bool consumers_quiesced);
#endif
