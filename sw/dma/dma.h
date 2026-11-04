#ifndef SOC_DMA_H_
#define SOC_DMA_H_

/*
 * Portable, freestanding iDMA descriptor-chain construction.
 * Matches pulp-platform/iDMA idma_desc64_top.sv at the pinned SoC revision.
 * Descriptors MUST be in DMA-visible physical SRAM, not CPU-only memory.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SOC_DMA_DESC_BYTES       32u
#define SOC_DMA_DESC_ALIGN       32u
#define SOC_DMA_CHAIN_END        UINT64_MAX
#define SOC_DMA_FLAG_IRQ         (1u << 0)
#define SOC_DMA_FLAG_SRC_INCR    (1u << 1)
#define SOC_DMA_FLAG_DST_INCR    (1u << 3)
#define SOC_DMA_FLAGS_MEMCPY     (SOC_DMA_FLAG_SRC_INCR | SOC_DMA_FLAG_DST_INCR)

typedef struct {
    uint32_t length;
    uint32_t flags;
    uint64_t next;
    uint64_t src_addr;
    uint64_t dst_addr;
} soc_dma_desc_t;

/* No malloc: a physically contiguous SRAM arena owned by a caller/test. */
typedef struct {
    uint8_t *cpu_base;
    uint64_t phys_base;
    size_t capacity;
    size_t used;
} soc_dma_arena_t;

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

/* Caller must map cpu_base onto phys_base with the same byte alignment. */
bool soc_dma_arena_init(soc_dma_arena_t *arena, void *cpu_base,
                        uint64_t phys_base, size_t capacity);
void soc_dma_arena_reset(soc_dma_arena_t *arena); /* only after all DMA work retires */
bool soc_dma_arena_alloc(soc_dma_arena_t *arena, size_t bytes,
                         size_t align, void **cpu_out, uint64_t *phys_out);

/* Builds contiguous descriptors; IRQ only on the final descriptor if enabled.
 * Transfer ranges must be valid mapped addresses. This function does not
 * submit a chain or guarantee ordering between dependent copies.
 */
bool soc_dma_chain_build(soc_dma_arena_t *arena, const soc_dma_copy_t *copies,
                         size_t count, bool irq_last, soc_dma_chain_t *out);

/* Compiler/CPU release fence; caller must additionally clean caches as needed. */
void soc_dma_publish(void);

#endif /* SOC_DMA_H_ */
