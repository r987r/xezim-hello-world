#include "../dma.h"
#include <assert.h>
#include <stdio.h>

static _Alignas(32) unsigned char pool[4096];

int main(void) {
    soc_dma_arena_t arena = {0};
    soc_dma_chain_t chain = {0};
    soc_dma_copy_t ops[3] = {
        {0x10002000u, 0x140000100ull, 64},
        {0x10002040u, 0x140000140ull, 17},
        {0x10002080u, 0x140000180ull, 1},
    };
    assert(soc_dma_arena_init(&arena, pool, 0x10001000, sizeof(pool)));
    assert(soc_dma_chain_build(&arena, ops, 3, true, &chain));
    assert(chain.count == 3 && chain.head_phys == 0x10001000);
    assert(arena.used == 96);
    assert(chain.cpu_descs[0].length == 64 && chain.cpu_descs[0].flags == 0xau);
    assert(chain.cpu_descs[0].next == 0x10001020);
    assert(chain.cpu_descs[2].flags == 0xbu);
    assert(chain.cpu_descs[2].next == SOC_DMA_CHAIN_END);
    assert(!soc_dma_chain_build(&arena, ops, 0, true, &chain));
    soc_dma_copy_t bad[] = {{UINT64_MAX, 0, 2}};
    assert(!soc_dma_chain_build(&arena, bad, 1, false, &chain));
    soc_dma_copy_t big_ops[129];
    for (size_t i = 0; i < 129; ++i) big_ops[i] = ops[0];
    assert(!soc_dma_chain_build(&arena, big_ops, 129, true, &chain));
    assert(arena.used == 96);
    soc_dma_publish();
    soc_dma_arena_reset(&arena);
    assert(soc_dma_chain_build(&arena, ops, 3, false, &chain));
    assert(chain.cpu_descs[2].flags == 0xau);
    puts("PASS dma C descriptor allocator and chain ABI");
    return 0;
}
