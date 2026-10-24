/* Read-only, bounded Qualcomm private SMEM decoding. No mapped pointers escape
 * until the partition and item bounds have been checked. Caller supplies a
 * snapshot: this parser does not synchronize with a running remote processor.
 */
#ifndef SPES_SMEM_READ_H
#define SPES_SMEM_READ_H
static uint32_t spes_le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint16_t spes_le16(const uint8_t *p) { return (uint16_t)p[0] | (uint16_t)p[1] << 8; }
static const uint8_t *
spes_smem_partition_read(const uint8_t *mem, uint32_t size, uint16_t remote, uint32_t *length)
{
    *length = 0;
    if (!mem || size < 4096) return NULL;
    const uint8_t *toc = mem + size - 4096;
    if (memcmp(toc, "$TOC", 4) || spes_le32(toc + 4) != 1) return NULL;
    uint32_t count = spes_le32(toc + 8);
    if (count > (4096 - 32) / 48) return NULL;
    for (unsigned i = 0; i < count; i++) {
        const uint8_t *e = toc + 32 + 48 * i;
        uint16_t a = spes_le16(e + 12), b = spes_le16(e + 14);
        if (!((a == 0 && b == remote) || (b == 0 && a == remote))) continue;
        uint32_t off = spes_le32(e), bytes = spes_le32(e + 4);
        if (!off || bytes < 32 || off > size - 4096 || bytes > size - 4096 - off) return NULL;
        const uint8_t *p = mem + off;
        if (memcmp(p, "$PRT", 4) || spes_le16(p + 4) != a || spes_le16(p + 6) != b ||
            spes_le32(p + 8) != bytes) return NULL;
        uint32_t uncached = spes_le32(p + 12), cached = spes_le32(p + 16);
        if (uncached < 32 || uncached > bytes || cached < uncached || cached > bytes) return NULL;
        *length = bytes;
        return p;
    }
    return NULL;
}
static const uint8_t *
spes_smem_item_read(const uint8_t *part, uint32_t length, uint16_t id, uint32_t *bytes)
{
    *bytes = 0;
    if (!part || length < 32) return NULL;
    uint32_t end = spes_le32(part + 12);
    if (end < 32 || end > length) return NULL;
    for (uint32_t pos = 32; end - pos >= 16;) {
        const uint8_t *h = part + pos;
        uint32_t size = spes_le32(h + 4), pad = spes_le16(h + 8), hdrpad = spes_le16(h + 10);
        if (spes_le16(h) != 0xa5a5 || pad > size || hdrpad > end - pos - 16 ||
            size > end - pos - 16 - hdrpad) return NULL;
        if (spes_le16(h + 2) == id) {
            *bytes = size - pad;
            return h + 16 + hdrpad;
        }
        pos += 16 + hdrpad + size;
    }
    return NULL;
}
#endif
