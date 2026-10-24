/* spes synchronous backend for the HackiOS RedwoodGPU service.
 * Included after the verified probe helpers in sweet_touch.c.
 * The service lock serializes all calls after startup. Never reset a faulted GPU.
 */
#define SPES_GPU_BASE 0x20000000ull
#define SPES_GPU_SIZE 0x10000000ull
#define SPES_GPU_GRANULE 0x10000ull
static struct {
 bool ready, faulted;
 vm_offset_t gpu, smmu, dma;
 uint32_t context, tail, fence;
 uint64_t *l2, *tables[128];
 uint8_t used[4096];
 struct { uint64_t base, size, span; bool unmapped; } buffers[1024];
 uint32_t submissions;
} sg;
uint32_t gpu_va, gpu_log;
extern void RedwoodGPUStart(void);

bool redwood_gpu_ready(void) { return sg.ready && !sg.faulted; }
void redwood_gpu_stop(void) {
 sg.ready = false;
 if (sg.gpu) touch_wr(sg.gpu, 0x2020u, 3u);
}
bool redwood_gpu_recover(void) { return false; }
void redwood_gpu_report(const char *why) {
 printf("SPES GPU: backend stopped: %s fence=%u tail=%u\n", why, sg.fence, sg.tail);
 if (sg.gpu) {
  printf("SPES GPU: SUBMIT_STATUS rptr=%u wptr=%u int=%#x fault=%#x int0=%#x GFSR=%#x FSR=%#x\n",
      touch_rd(sg.gpu, 0x2018u), sg.tail, touch_rd(sg.gpu, 0x208cu),
      touch_rd(sg.gpu, 0x2084u), touch_rd(sg.gpu, 0x804u),
      touch_rd(sg.smmu, 0x48u), touch_rd(sg.smmu, sg.context + 0x58u));
  printf("SPES GPU: SUBMIT_IB1 base=%#x:%#x remaining=%u\n",
      touch_rd(sg.gpu, 0x24a4u), touch_rd(sg.gpu, 0x24a0u), touch_rd(sg.gpu, 0x24a8u));
 }
 sg.faulted = true;
 redwood_gpu_stop();
}
static bool spes_gpu_backend_sync(void) {
 if (spes_gpu_tlb_sync(sg.smmu, sg.context)) return true;
 redwood_gpu_report("TLB sync timeout; allocations retained");
 return false;
}
static int spes_gpu_owner(uint64_t address, uint64_t size) {
 if (!size || address < SPES_GPU_BASE || address >= SPES_GPU_BASE + SPES_GPU_SIZE ||
     size > SPES_GPU_BASE + SPES_GPU_SIZE - address) return -1;
 for (unsigned i=0;i<1024;++i)
  if (sg.buffers[i].base && address >= sg.buffers[i].base &&
      address - sg.buffers[i].base < sg.buffers[i].size &&
      size <= sg.buffers[i].size - (address - sg.buffers[i].base)) return (int)i;
 return -1;
}
uint64_t redwood_gpu_address(uint64_t size) {
 if (!redwood_gpu_ready() || !size || size > SPES_GPU_SIZE || (size & 4095)) return 0;
 uint64_t span=(size+SPES_GPU_GRANULE-1)&~(SPES_GPU_GRANULE-1);
 unsigned slot=1024;
 for(unsigned i=0;i<1024;++i) if(!sg.buffers[i].base){slot=i;break;}
 if(slot==1024)return 0;
 unsigned needed=(unsigned)(span/SPES_GPU_GRANULE), run=0;
 for(unsigned i=0;i<4096;++i){
  run=sg.used[i]?0:run+1;
  if(run!=needed)continue;
  unsigned first=i+1-needed;
  for(unsigned j=first;j<=i;++j)sg.used[j]=1;
  sg.buffers[slot].base=SPES_GPU_BASE+first*SPES_GPU_GRANULE;
  sg.buffers[slot].size=size;sg.buffers[slot].span=span;sg.buffers[slot].unmapped=true;
  return sg.buffers[slot].base;
 }
 return 0;
}
static uint64_t *spes_gpu_leaf(uint64_t address, bool create) {
 if(address<SPES_GPU_BASE || address>=SPES_GPU_BASE+SPES_GPU_SIZE)return NULL;
 unsigned index=(unsigned)((address-SPES_GPU_BASE)>>21);
 if(!sg.tables[index] && create){
  vm_offset_t memory=0;
  if(kmem_alloc_contig(kernel_map,&memory,PAGE_SIZE,PAGE_MASK,0,0,
      KMA_DATA|KMA_ZERO|KMA_PERMANENT,VM_KERN_MEMORY_IOKIT)!=KERN_SUCCESS)return NULL;
  uint64_t physical=ptoa_64(pmap_find_phys(kernel_pmap,(addr64_t)memory));
  if(!physical || physical>=(1ull<<36) || (physical&4095))return NULL;
  memset((void *)memory,0,PAGE_SIZE);
  to_memory(memory,PAGE_SIZE); /* child must be visible before parent */
  sg.tables[index]=(uint64_t *)memory;
  sg.l2[256+index]=physical|3;
  to_memory((vm_offset_t)&sg.l2[256+index],8);
 }
 return sg.tables[index]?&sg.tables[index][(address>>12)&511]:NULL;
}
bool redwood_gpu_map(uint64_t address,uint64_t physical,bool ro) {
 int owner=spes_gpu_owner(address,4096);
 if(!redwood_gpu_ready() || owner<0 || (address&4095) || !physical ||
     (physical&4095) || physical>=(1ull<<36))return false;
 uint64_t *leaf=spes_gpu_leaf(address,true);
 if(!leaf || *leaf)return false;
 *leaf=physical|0xe43ull|(ro?0x80ull:0);
 sg.buffers[owner].unmapped=false;
 to_memory((vm_offset_t)leaf,8);
 return true;
}
bool redwood_gpu_mapped(void) {
 return redwood_gpu_ready() && spes_gpu_backend_sync();
}
bool redwood_gpu_done(uint32_t fence) {
 if(!redwood_gpu_ready() || fence>sg.fence)return false;
 __asm__ volatile("dsb sy" ::: "memory");
 return ((volatile uint32_t *)(sg.dma+0xc000))[9]>=fence;
}
uint32_t redwood_gpu_last(void){return sg.fence;}
bool redwood_gpu_unmap(uint64_t address,uint64_t size) {
 int owner=spes_gpu_owner(address,size);
 if(!redwood_gpu_ready() || owner<0 || address!=sg.buffers[owner].base ||
     size!=sg.buffers[owner].size || !redwood_gpu_done(sg.fence))return false;
 for(uint64_t offset=0;offset<size;offset+=4096){
  uint64_t *leaf=spes_gpu_leaf(address+offset,false);
  if(leaf){*leaf=0;to_memory((vm_offset_t)leaf,8);}
 }
 if(!spes_gpu_backend_sync())return false;
 sg.buffers[owner].unmapped=true;
 return true;
}
void redwood_gpu_address_free(uint64_t address,uint64_t size) {
 int owner=spes_gpu_owner(address,size);
 if(!redwood_gpu_ready() || owner<0 || address!=sg.buffers[owner].base ||
     size!=sg.buffers[owner].size || !sg.buffers[owner].unmapped)return;
 unsigned first=(unsigned)((address-SPES_GPU_BASE)/SPES_GPU_GRANULE);
 unsigned count=(unsigned)(sg.buffers[owner].span/SPES_GPU_GRANULE);
 for(unsigned i=first;i<first+count;++i)sg.used[i]=0;
 memset(&sg.buffers[owner],0,sizeof(sg.buffers[owner]));
}
void redwood_gpu_to_memory(void *start,uint64_t size) {
 if(size && (!start || size>SPES_GPU_SIZE || (uintptr_t)start+size<(uintptr_t)start))return;
 to_memory((vm_offset_t)start,(vm_size_t)size);
}
uint32_t redwood_gpu_submit(const uint64_t *addresses,const uint32_t *words,uint32_t count) {
 if(!redwood_gpu_ready() || !count || count>64 || sg.fence==0xffffffffu ||
     !redwood_gpu_done(sg.fence))return 0;
 uint32_t commands[266],n=0;
 /* Linux/HackiOS invalidate depth/color before each batch. */
 commands[n++]=0x70468001;commands[n++]=0x18;
 commands[n++]=0x70468001;commands[n++]=0x19;
 for(unsigned i=0;i<count;++i){
  if(!words[i] || words[i]>0xfffffu || (addresses[i]&3) ||
      spes_gpu_owner(addresses[i],(uint64_t)words[i]*4)<0)return 0;
  uint64_t end=addresses[i]+(uint64_t)words[i]*4;
  for(uint64_t page=addresses[i]&~4095ull;page<end;page+=4096){
   uint64_t *leaf=spes_gpu_leaf(page,false);if(!leaf || !(*leaf&1))return 0;
  }
  commands[n++]=0x70bf8003;commands[n++]=(uint32_t)addresses[i];
  commands[n++]=(uint32_t)(addresses[i]>>32);commands[n++]=words[i];
 }
 uint32_t fence=sg.fence+1;
 commands[n++]=0x70268000;
 commands[n++]=0x70460004;commands[n++]=4;commands[n++]=0x011f0024;
 commands[n++]=0;commands[n++]=fence;
 if(!spes_gpu_ring_append((volatile uint32_t *)(sg.dma+0x8000),&sg.tail,
     touch_rd(sg.gpu,0x2018),commands,n))return 0;
 sg.fence=fence;
 __asm__ volatile("dsb sy" ::: "memory");
 touch_wr(sg.gpu,0x201c,sg.tail);
 if(!spes_gpu_retire(sg.gpu,sg.smmu,sg.context,sg.tail,NULL)){
  redwood_gpu_report("submission fault or timeout");return 0;
 }
 for(unsigned i=0;i<1000;++i){
  if(redwood_gpu_done(fence)){
   if(!spes_gpu_retire(sg.gpu,sg.smmu,sg.context,sg.tail,NULL))break;
   ++sg.submissions;return fence;
  }
  touch_wait(1);
 }
 redwood_gpu_report("completion fence timeout");return 0;
}
void redwood_gpu_space(uint64_t *used,uint32_t *live,uint64_t *largest,unsigned *holes,
    unsigned *most,uint64_t *lost,uint32_t *refused){
 *used=0;*live=0;*largest=0;*holes=0;*lost=0;*refused=0;
 uint64_t run=0;
 for(unsigned i=0;i<4096;++i){
  if(sg.used[i]){*used+=SPES_GPU_GRANULE;run=0;}
  else{if(!run)++*holes;run+=SPES_GPU_GRANULE;if(run>*largest)*largest=run;}
 }
 for(unsigned i=0;i<1024;++i)if(sg.buffers[i].base)++*live;
 *most=*holes;
}
void redwood_gpu_worked(uint64_t *us,uint32_t *submissions,uint32_t by[7]){
 *us=0;*submissions=sg.submissions;memset(by,0,7*sizeof(*by));sg.submissions=0;
}
/* Only hardware facts from the spes A610 descriptor; do not copy A642L caps. */
bool redwood_gpu_parameter(uint32_t which,uint64_t *value){
 switch(which){
 case 1:*value=610;return true;
 case 2:*value=132u*1024u;return true;
 case 3:*value=0x06010001;return true;
 case 6:*value=0x100000;return true;
 case 7:*value=1;return true;
 case 0x10:*value=14;return true;
 case 0x12:*value=7;return true;
 case 0x13:*value=0;return true;
 default:return false;
 }
}
static bool spes_gpu_backend_start(vm_offset_t gpu,vm_offset_t smmu,uint32_t context,
    vm_offset_t dma,uint64_t *l2,uint32_t tail){
 if(sg.ready || sg.faulted)return false;
 for(unsigned i=256;i<384;++i)if(l2[i])return false;
 sg.gpu=gpu;sg.smmu=smmu;sg.context=context;sg.dma=dma;sg.l2=l2;sg.tail=tail;
 sg.fence=((volatile uint32_t *)(dma+0xc000))[9];
 sg.ready=true;
 RedwoodGPUStart();
 printf("SPES GPU: persistent backend ready; synchronous submissions, 256 MiB VA\n");
 return true;
}
