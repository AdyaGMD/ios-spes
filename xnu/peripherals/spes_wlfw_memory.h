/* WLFW MSA_INFO TLV: u8 count, then {le64 address, le32 size, u8 secure}.
 * Validate every region before transferring ownership. No hardware dependencies.
 */
#ifndef SPES_WLFW_MEMORY_H
#define SPES_WLFW_MEMORY_H
static bool
spes_msa_regions_valid(const uint8_t *v, uint32_t len, uint64_t base, uint32_t size)
{
    if (!v || !len || !v[0] || len != 1u + 13u * v[0]) return false;
    for (unsigned i = 0; i < v[0]; i++) {
        const uint8_t *e = v + 1 + 13 * i;
        uint64_t addr = 0;
        uint32_t bytes = 0;
        for (unsigned b = 0; b < 8; b++) addr |= (uint64_t)e[b] << (8 * b);
        for (unsigned b = 0; b < 4; b++) bytes |= (uint32_t)e[8 + b] << (8 * b);
        if (!bytes || e[12] > 1 || addr < base || addr - base >= size ||
            bytes > size - (addr - base)) return false;
        for (unsigned j = 0; j < i; j++) {
            const uint8_t *p = v + 1 + 13 * j;
            uint64_t previous = 0;
            uint32_t previous_bytes = 0;
            for (unsigned b = 0; b < 8; b++) previous |= (uint64_t)p[b] << (8 * b);
            for (unsigned b = 0; b < 4; b++) previous_bytes |= (uint32_t)p[8 + b] << (8 * b);
            /* Both addresses already bounded by the supplied window. */
            if (addr - base < previous - base + previous_bytes &&
                previous - base < addr - base + bytes) return false;
        }
    }
    return true;
}
#endif
