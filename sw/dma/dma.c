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

/* The 64-bit upstream iDMA descriptor pointer crosses an AXI-Lite
 * 32-bit firmware CSR in two writes, committed by a one-shot doorbell.
 */
bool soc_dma_mmio_submit(volatile uint32_t *csr, uint64_t head_phys) {
    if (!csr || (head_phys & (SOC_DMA_DESC_ALIGN - 1u)) != 0)
        return false;
    uint32_t status = csr[SOC_DMA_REG_STATUS / 4u];
    if (status & (SOC_DMA_STATUS_APB_BUSY | SOC_DMA_STATUS_IRQ |
                  SOC_DMA_STATUS_APB_ERROR))
        return false;
    csr[SOC_DMA_REG_HEAD_LO / 4u] = (uint32_t)head_phys;
    csr[SOC_DMA_REG_HEAD_HI / 4u] = (uint32_t)(head_phys >> 32);
    soc_dma_publish();
    csr[SOC_DMA_REG_COMMAND / 4u] = SOC_DMA_CMD_SUBMIT;
    return true;
}

bool soc_dma_mmio_wait_irq(volatile const uint32_t *csr,
                           uint32_t max_polls, uint32_t *status_out) {
    if (!csr || !max_polls) return false;
    for (uint32_t n = 0; n < max_polls; ++n) {
        uint32_t status = csr[SOC_DMA_REG_STATUS / 4u];
        if (status_out) *status_out = status;
        if (status & SOC_DMA_STATUS_APB_ERROR) return false;
        if (status & SOC_DMA_STATUS_IRQ) return true;
    }
    return false;
}

void soc_dma_mmio_ack_irq(volatile uint32_t *csr) {
    if (csr) csr[SOC_DMA_REG_COMMAND / 4u] = SOC_DMA_CMD_IRQ_ACK;
}
