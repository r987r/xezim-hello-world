/* Minimal freestanding RV32I compiler runtime for the verification CPU.
 *
 * PicoRV32 is compiled without the RISC-V M extension. clang/lld -nostdlib
 * correctly requires an integer multiply helper and C object initialization.
 * This platform ABI support is not an alternate DMA, SRAM or NoC model.
 * Replace these two entrypoints with a pinned compiler-rt/libgcc + libc
 * runtime when a full RISC-V BSP is introduced.
 */
#include <stddef.h>
#include <stdint.h>

/* libgcc/compiler-rt ABI: low 32 bits of a signed 32x32 multiplication.
 * Only shifts/adds are used, so an RV32I compiler cannot recurse through
 * another __mulsi3 call. Cast to uint32_t makes overflow well-defined.
 */
int32_t __mulsi3(int32_t lhs, int32_t rhs) {
    uint32_t a = (uint32_t)lhs;
    uint32_t b = (uint32_t)rhs;
    uint32_t product = 0;
    while (b != 0) {
        if ((b & 1u) != 0) product += a;
        a <<= 1u;
        b >>= 1u;
    }
    return (int32_t)product;
}

/* Minimal C ABI memset; volatile byte stores prevent compilers from
 * recognizing this loop and lowering it into a call to itself at -Oz.
 * These helpers are linked only into the freestanding CPU image.
 */
void *memset(void *dst, int value, size_t count) {
    volatile unsigned char *p = (volatile unsigned char *)dst;
    unsigned char byte = (unsigned char)value;
    for (size_t i = 0; i < count; ++i) p[i] = byte;
    return dst;
}
