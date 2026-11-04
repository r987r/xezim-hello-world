#include "dma.h"
#include <limits.h>

_Static_assert(sizeof(soc_dma_desc_t) == SOC_DMA_DESC_BYTES, "iDMA size mismatch");
_Static_assert(offsetof(soc_dma_desc_t, length) == 0, "iDMA length offset");
_Static_assert(offsetof(soc_dma_desc_t, flags) == 4, "iDMA flags offset");
_Static_assert(offsetof(soc_dma_desc_t, next) == 8, "iDMA next offset");
_Static_assert(offsetof(soc_dma_desc_t, src_addr) == 16, "iDMA src offset");
_Static_assert(offsetof(soc_dma_desc_t, dst_addr) == 24, "iDMA dst offset");

static bool power_of_two(size_t value) {
    return value && !(value & (value - 1));
}

bool soc_dma_arena_init(soc_dma_arena_t *arena, void *cpu_base,
                        uint64_t phys_base, size_t capacity) {
    if (!arena || !cpu_base || capacity == 0 ||
        (uint64_t)capacity > UINT64_MAX - phys_base) return false;
    arena->cpu_base = (uint8_t *)cpu_base;
    arena->phys_base = phys_base;
    arena->capacity = capacity;
    arena->used = 0;
    return true;
}

void soc_dma_arena_reset(soc_dma_arena_t *arena) {
    if (arena) arena->used = 0;
}

bool soc_dma_arena_alloc(soc_dma_arena_t *arena, size_t bytes,
                         size_t align, void **cpu_out, uint64_t *phys_out) {
    if (!arena || !arena->cpu_base || !cpu_out || !phys_out ||
        bytes == 0 || !power_of_two(align) || arena->used > arena->capacity)
        return false;
    /* Alignment applies to DMA physical addresses AND CPU pointers. */
    if (((uintptr_t)arena->cpu_base & (align - 1)) !=
        ((uintptr_t)arena->phys_base & (align - 1))) return false;
    if ((uint64_t)arena->used > UINT64_MAX - arena->phys_base) return false;
    uint64_t current = arena->phys_base + (uint64_t)arena->used;
    uint64_t mask = (uint64_t)align - 1;
    if (current > UINT64_MAX - mask) return false;
    uint64_t aligned = (current + mask) & ~mask;
    if (aligned < arena->phys_base) return false;
    uint64_t offset = aligned - arena->phys_base;
    if (offset > arena->capacity || bytes > arena->capacity - (size_t)offset)
        return false;
    *cpu_out = arena->cpu_base + (size_t)offset;
    *phys_out = aligned;
    arena->used = (size_t)offset + bytes;
    return true;
}

bool soc_dma_chain_build(soc_dma_arena_t *arena, const soc_dma_copy_t *copies,
                         size_t count, bool irq_last, soc_dma_chain_t *out) {
    if (!arena || !copies || !out || !count ||
        count > SIZE_MAX / SOC_DMA_DESC_BYTES) return false;
    for (size_t i = 0; i < count; ++i) {
        if (!copies[i].length ||
            (uint64_t)copies[i].length > UINT64_MAX - copies[i].src_addr ||
            (uint64_t)copies[i].length > UINT64_MAX - copies[i].dst_addr)
            return false;
    }
    void *cpu = NULL;
    uint64_t head = 0;
    if (!soc_dma_arena_alloc(arena, count * SOC_DMA_DESC_BYTES,
                             SOC_DMA_DESC_ALIGN, &cpu, &head)) return false;
    soc_dma_desc_t *descs = (soc_dma_desc_t *)cpu;
    for (size_t i = 0; i < count; ++i) {
        descs[i].length = copies[i].length;
        descs[i].flags = SOC_DMA_FLAGS_MEMCPY |
            ((irq_last && i == count - 1) ? SOC_DMA_FLAG_IRQ : 0u);
        descs[i].next = (i == count - 1) ? SOC_DMA_CHAIN_END :
            (head + (uint64_t)(i + 1) * SOC_DMA_DESC_BYTES);
        descs[i].src_addr = copies[i].src_addr;
        descs[i].dst_addr = copies[i].dst_addr;
    }
    out->cpu_descs = descs;
    out->head_phys = head;
    out->count = count;
    return true;
}

void soc_dma_publish(void) {
#if defined(__GNUC__) || defined(__clang__)
    __atomic_thread_fence(__ATOMIC_RELEASE);
#else
#error "soc_dma_publish requires an implementation of a CPU memory fence"
#endif
}
