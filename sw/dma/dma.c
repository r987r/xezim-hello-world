#include "dma.h"
#include <limits.h>

_Static_assert(sizeof(soc_dma_desc_t) == SOC_DMA_DESC_BYTES, "iDMA size mismatch");
_Static_assert(offsetof(soc_dma_desc_t, length) == 0, "iDMA length offset");
_Static_assert(offsetof(soc_dma_desc_t, flags) == 4, "iDMA flags offset");
_Static_assert(offsetof(soc_dma_desc_t, next) == 8, "iDMA next offset");
_Static_assert(offsetof(soc_dma_desc_t, src_addr) == 16, "iDMA src offset");
_Static_assert(offsetof(soc_dma_desc_t, dst_addr) == 24, "iDMA dst offset");

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
