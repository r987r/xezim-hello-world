#ifndef SOC_MEMORY_POOL_H_
#define SOC_MEMORY_POOL_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Unified, deterministic physical-region allocator. Metadata is CPU-owned,
 * not stored in SRAM/DDR/HBM target storage. DDR/HBM may be inaccessible to
 * CPU load/store: physical addresses are still valid for DMA descriptors.
 *
 * A region has one owner at a time. Synchronization/IRQ/AXI drain is the
 * caller's responsibility; a boolean quiescence acknowledgement is a
 * lifetime precondition, NOT proof supplied by the allocator.
 */
typedef enum {
    SOC_MEM_SRAM = 1, SOC_MEM_DDR = 2, SOC_MEM_HBM = 3
} soc_mem_kind_t;

typedef struct {
    const char *name;
    soc_mem_kind_t kind;
    uint64_t phys_base, capacity;
    uint8_t *cpu_base;    /* Only CPU-addressable SRAM exposes a pointer */
    uint64_t used;
    uint64_t next_token, top_token;
    uint32_t generation;
} soc_mem_region_t;

typedef struct {
    uint64_t phys, bytes, previous_used;
    void *cpu_ptr;        /* NULL for DDR/HBM/CPU-inaccessible SRAM */
    uint64_t token, previous_token;
    uint32_t generation;
} soc_mem_allocation_t;

bool soc_mem_region_init(soc_mem_region_t *region, const char *name,
                         soc_mem_kind_t kind, uint64_t phys_base,
                         uint64_t capacity, void *cpu_base);
bool soc_mem_alloc(soc_mem_region_t *region, uint64_t bytes, uint64_t alignment,
                   soc_mem_allocation_t *out);
/* LIFO release only, after consumers are quiescent. Reject stale/double free
 * even when a newer allocation happens to reuse the same physical address.
 */
bool soc_mem_release(soc_mem_region_t *region, const soc_mem_allocation_t *allocation,
                     bool consumers_quiesced);
bool soc_mem_reset(soc_mem_region_t *region, bool consumers_quiesced);
#endif
