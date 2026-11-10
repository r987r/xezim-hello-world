#ifndef SOC_DMA_H_
#define SOC_DMA_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "../common/sram_pool.h"

/* Exact pinned PULP idma_desc64 descriptor layout. */
#define SOC_DMA_DESC_BYTES 32u
#define SOC_DMA_DESC_ALIGN 32u
#define SOC_DMA_CHAIN_END UINT64_MAX
#define SOC_DMA_FLAG_IRQ (1u << 0)
#define SOC_DMA_FLAG_SRC_INCR (1u << 1)
#define SOC_DMA_FLAG_DST_INCR (1u << 3)
#define SOC_DMA_FLAGS_MEMCPY (SOC_DMA_FLAG_SRC_INCR | SOC_DMA_FLAG_DST_INCR)

typedef struct {
    uint32_t length;
    uint32_t flags;
    uint64_t next;
    uint64_t src_addr;
    uint64_t dst_addr;
} soc_dma_desc_t;

/* All boot/runtime/DMA SRAM allocations use the same generic bounded pool. */
typedef soc_sram_pool_t soc_dma_arena_t;
static inline bool soc_dma_arena_init(soc_dma_arena_t *a, void *p,
                                       uint64_t addr, size_t bytes) {
    return soc_sram_pool_init(a, p, addr, bytes);
}
static inline bool soc_dma_arena_alloc(soc_dma_arena_t *a, size_t bytes,
                                        size_t alignment, void **p, uint64_t *addr) {
    return soc_sram_pool_alloc(a, bytes, alignment, p, addr);
}
/* Explicit barrier to prevent freeing descriptors still in use by a DMA. */
static inline bool soc_dma_arena_reset(soc_dma_arena_t *a, bool dma_idle) {
    return soc_sram_pool_reset(a, dma_idle);
}

typedef struct {
    uint64_t src_addr;
    uint64_t dst_addr;
    uint32_t length;
} soc_dma_copy_t;
typedef struct {
    soc_dma_desc_t *cpu_descs;
    uint64_t head_phys;
    size_t count;
} soc_dma_chain_t;

bool soc_dma_chain_build(soc_dma_arena_t *arena, const soc_dma_copy_t *copies,
                         size_t count, bool irq_last, soc_dma_chain_t *out);
void soc_dma_publish(void);  /* cache clean required on noncoherent CPUs */

/* Firmware-side 32-bit registers on the real soc_dma_regs MMIO boundary.
 * APB_BUSY covers only head submission, never full descriptor retirement.
 * Keep descriptors/source SRAM allocated until IRQ, writebacks and idle.
 */
/* The checked-in C header is emitted from the existing SystemRDL model.
 * Only compatibility/negative ABI tests opt into legacy literals. Vendor
 * DMA registers, descriptors and RTL are not replaced by this header.
 */
#ifndef SOC_USE_LEGACY_DMA_CSR
#include "generated/soc_dma_shim_regs.h"
#else
#define SOC_DMA_REG_HEAD_LO       0x00u
#define SOC_DMA_REG_HEAD_HI       0x04u
#define SOC_DMA_REG_COMMAND       0x08u
#define SOC_DMA_REG_STATUS        0x0cu
#define SOC_DMA_CMD_SUBMIT        (1u << 0)
#define SOC_DMA_CMD_IRQ_ACK       (1u << 1)
#define SOC_DMA_STATUS_APB_BUSY   (1u << 0)
#define SOC_DMA_STATUS_IRQ        (1u << 1)
#define SOC_DMA_STATUS_APB_ERROR  (1u << 2)
#define SOC_DMA_STATUS_RAW_IRQ    (1u << 3)
#endif

/* Reject invalid, unaligned and busy/pending/error CSR submissions. A
 * release fence precedes the doorbell; noncoherent CPUs need cache clean.
 * The caller must still track engine completion and descriptor lifetime.
 */
bool soc_dma_mmio_submit(volatile uint32_t *csr, uint64_t head_phys);
/* Bounded polling for the sticky completion status; errors win over IRQ. */
bool soc_dma_mmio_wait_irq(volatile const uint32_t *csr,
                           uint32_t max_polls, uint32_t *status_out);
/* Asynchronous one-shot acknowledgement; re-read STATUS to confirm clear. */
void soc_dma_mmio_ack_irq(volatile uint32_t *csr);
#endif
