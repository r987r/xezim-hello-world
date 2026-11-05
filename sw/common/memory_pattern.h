#ifndef SOC_MEMORY_PATTERN_H_
#define SOC_MEMORY_PATTERN_H_
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

/* Same physical-address recipe as tools/memory_service.py::Pattern.
 * These are CPU-side bytes only. Never dereference DDR/HBM physical
 * addresses on an RV32I CPU just because a DMA allocation exists.
 */
typedef enum {
    SOC_PATTERN_COUNTER8 = 1,
    SOC_PATTERN_CONSTANT = 2,
    SOC_PATTERN_ADDRESS_XOR = 3
} soc_pattern_kind_t;

bool soc_mem_pattern_valid(soc_pattern_kind_t kind);
uint8_t soc_mem_expected_byte(uint64_t phys_addr, uint32_t seed,
                              soc_pattern_kind_t kind);
/* Writes exactly n bytes to mapped CPU RAM; no implicit full-image preload. */
void soc_mem_fill_pattern(void *cpu_dst, uint64_t phys_addr, size_t n,
                          uint32_t seed, soc_pattern_kind_t kind);
/* Returns first mismatch offset or n on success. CPU-accessible memory only. */
size_t soc_mem_check_pattern(const void *cpu_src, uint64_t phys_addr, size_t n,
                             uint32_t seed, soc_pattern_kind_t kind);
#endif
