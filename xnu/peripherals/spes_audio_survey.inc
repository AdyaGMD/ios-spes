/* Included by SpesModem.cpp; independent of modem=1. Read-only first stage
 * of the HackiOS ADSP survey, using spes SMEM instead of redwood IPCC/RPMh.
 * No PAS, mailbox, regulator, codec or amplifier writes.
 */
#include "spes_smem_read.h"
static void
spes_audio_survey_thread(void *, wait_result_t)
{
    IOMemoryMap *mapping = map_phys(SMEM_PA, SMEM_SIZE, true);
    uint8_t *snapshot = (uint8_t *)IOMalloc(SMEM_SIZE);
    if (!mapping || !snapshot) {
        IOLog("SPES AUDIO: SMEM snapshot allocation failed\n");
    } else {
        memcpy(snapshot, (const void *)mapping->getVirtualAddress(), SMEM_SIZE);
        uint32_t length = 0;
        const uint8_t *part = spes_smem_partition_read(snapshot, SMEM_SIZE, 2, &length);
        IOLog("SPES AUDIO: read-only ADSP survey; partition=%s bytes=%u\n", part ? "valid" : "absent-or-invalid", length);
        const uint16_t ids[] = { 443, 429, 423, 478, 479, 480 };
        for (unsigned i = 0; part && i < sizeof(ids) / sizeof(ids[0]); i++) {
            uint32_t bytes = 0;
            const uint8_t *item = spes_smem_item_read(part, length, ids[i], &bytes);
            IOLog("SPES AUDIO: SMEM item=%u present=%u bytes=%u\n", ids[i], item != NULL, bytes);
            if ((ids[i] == 443 || ids[i] == 429) && item && bytes >= 20 &&
                spes_le32(item) == 0x504d5324 && item[4] == 1) {
                uint16_t total = spes_le16(item + 12), valid = spes_le16(item + 14);
                if (total > 16 || valid > total || (uint32_t)valid * 20 > bytes - 20) {
                    IOLog("SPES AUDIO: invalid SMP2P entry bounds\n");
                    continue;
                }
                IOLog("SPES AUDIO: SMP2P local=%u remote=%u entries=%u flags=%x\n",
                    spes_le16(item + 8), spes_le16(item + 10), valid, spes_le32(item + 16));
                for (unsigned j = 0; j < valid; j++) {
                    char name[17];
                    memcpy(name, item + 20 + 20 * j, 16); name[16] = 0;
                    IOLog("SPES AUDIO: SMP2P %.16s=%x\n", name, spes_le32(item + 36 + 20 * j));
                }
            }
        }
        IOLog("SPES AUDIO: survey complete; DSP and amplifiers not started\n");
    }
    if (snapshot) IOFree(snapshot, SMEM_SIZE);
    if (mapping) mapping->release();
    thread_terminate(current_thread());
}
static void
spes_audio_survey_init(void)
{
    uint32_t enabled = 0;
    static bool started;
    if (started || !PE_parse_boot_argn("spesaudiosurvey", &enabled, sizeof(enabled)) || enabled != 1) return;
    thread_t worker;
    started = true;
    if (kernel_thread_start(spes_audio_survey_thread, NULL, &worker) == KERN_SUCCESS) thread_deallocate(worker);
    else IOLog("SPES AUDIO: could not start survey thread\n");
}
