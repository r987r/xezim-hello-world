#include "memory_pattern.h"

uint8_t soc_mem_expected_byte(uint64_t phys_addr, uint32_t seed,
                              soc_pattern_kind_t kind) {
    switch (kind) {
    case SOC_PATTERN_CONSTANT: return (uint8_t)seed;
    case SOC_PATTERN_COUNTER8: return (uint8_t)(phys_addr + seed);
    case SOC_PATTERN_ADDRESS_XOR: return (uint8_t)(phys_addr ^ seed);
    default: return 0; /* callers validate the declared enum */
    }
}

void soc_mem_fill_pattern(void *cpu_dst, uint64_t phys_addr, size_t n,
                          uint32_t seed, soc_pattern_kind_t kind) {
    volatile uint8_t *p = (volatile uint8_t *)cpu_dst;
    for (size_t i=0; i<n; ++i)
        p[i] = soc_mem_expected_byte(phys_addr+i, seed, kind);
}

size_t soc_mem_check_pattern(const void *cpu_src, uint64_t phys_addr, size_t n,
                             uint32_t seed, soc_pattern_kind_t kind) {
    volatile const uint8_t *p = (volatile const uint8_t *)cpu_src;
    for (size_t i=0; i<n; ++i)
        if (p[i] != soc_mem_expected_byte(phys_addr+i, seed, kind))
            return i;
    return n;
}
