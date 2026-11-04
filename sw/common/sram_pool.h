#ifndef SOC_SRAM_POOL_H_
#define SOC_SRAM_POOL_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Independent, non-overlapping, physically addressed SRAM region.
 * The platform reserves region ranges; NEVER allocate over running firmware.
 * No malloc, caches, or implicit reuse while consumers/DMA are active.
 */
typedef struct {
    uint8_t *cpu_base;
    uint64_t phys_base;
    size_t capacity;
    size_t used;
} soc_sram_pool_t;

bool soc_sram_pool_init(soc_sram_pool_t *pool, void *cpu_base,
                        uint64_t phys_base, size_t capacity);
bool soc_sram_pool_alloc(soc_sram_pool_t *pool, size_t bytes, size_t alignment,
                         void **cpu_out, uint64_t *phys_out);
/* Only after all users of this region have completed; no implicit synchronization. */
bool soc_sram_pool_reset(soc_sram_pool_t *pool, bool users_quiesced);
/* Reuse an explicitly separate boot-scratch window after firmware CHECK and
 * all outstanding CPU/DMA accesses to that scratch region have drained.
 * This never includes executing firmware nor mailboxes still observed by DV.
 */
bool soc_sram_pool_reclaim_boot_scratch(soc_sram_pool_t *pool,
                                        bool boot_check_complete,
                                        bool users_quiesced);
#endif
