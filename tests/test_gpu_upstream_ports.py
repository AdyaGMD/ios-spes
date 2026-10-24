"""Exercise the patched framebuffer handoff with stalled GPU and disappearing IDs."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]


def patched_source(directory, names):
    subprocess.run(['git', 'init', '-q', str(directory)], check=True)
    for patch in sorted((ROOT / 'xnu/patches').glob('*.patch')):
        if not any(('+++ b/' + name + '\n').encode() in patch.read_bytes() for name in names):
            continue
        subprocess.run(['git', 'apply', *['--include=' + n for n in names], str(patch)],
                       cwd=directory, check=True, capture_output=True)
    return [(directory / name).read_text() for name in names]


class UpstreamPorts(unittest.TestCase):
    def test_retained_frames_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            source, = patched_source(d, ['iokit/Kernel/arm/SweetFramebuffer.cpp'])
            swap = source[source.index('void\nAppleCLCD::swap('):source.index('void\nAppleCLCD::presenterMain(')]
            presenter = source[source.index('void\nAppleCLCD::presenter()'):source.index('bool\nAppleCLCD::present(')]
            harness = r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#define SWEET_FB_LAYERS 4
#define SWEET_FB_SWAP_REC_SIZE 0x46c
#define THREAD_UNINT 0
#define THREAD_TIMED_OUT 1
#define kMillisecondScale 0
#define IOLog(...) ((void)0)
#define OSSafeReleaseNULL(p) do { if(p) { (p)->release(); (p)=nullptr; } } while(0)
using AbsoluteTime=uint64_t;
struct Idle {};
static void IOLockLock(int) {}
static void IOLockUnlock(int) {}
static void IOLockWakeup(int,void*,bool) {}
static void IOLockSleep(int,void*,int) {throw Idle{};}
static int IOLockSleepDeadline(int,void*,uint64_t,int) {return THREAD_TIMED_OUT;}
static void clock_interval_to_deadline(int,int,uint64_t *d) {*d=1;}
struct SweetSurface { unsigned refs=1; void release(){assert(refs);--refs;} } surface;
static SweetSurface *table[8]={};
static SweetSurface *sweet_surface_copy(uint32_t id) {
    SweetSurface *p=id<8?table[id]:nullptr; if(p)++p->refs;return p;
}
static uint32_t get32(const uint8_t *p,unsigned off){uint32_t v;memcpy(&v,p+off,4);return v;}
static uint64_t sweet_fb_swap_count;
struct AppleCLCD {
 int fLock=0;bool fDirty=false,fPowerOff=false,fPresentReady=false,ready=true;
 uint32_t fSwapID=0,fMissed=0;unsigned presents=0;
 uint8_t fPending[SWEET_FB_SWAP_REC_SIZE]={};SweetSurface *fPendingSurfaces[4]={};
 void swap(const uint8_t *);void presenter();
 bool present(const uint8_t *,SweetSurface **s) {assert(s[0]==&surface);assert(surface.refs==2);++presents;return ready;}
};
'''
            harness += swap + presenter
            harness += r'''
static void tick(AppleCLCD &fb){fb.fPresentReady=true;try{fb.presenter();}catch(Idle&) {}}
int main(){
 AppleCLCD fb;uint8_t rec[SWEET_FB_SWAP_REC_SIZE]={};uint32_t id=1;
 memcpy(rec+0x54,&id,4);table[1]=&surface;
 fb.swap(rec);assert(fb.fDirty && surface.refs==2);
 table[1]=nullptr; // user's reference/ID lookup may disappear before the timer
 fb.ready=false;tick(fb);assert(fb.fDirty && surface.refs==2 && fb.presents==1);
 uint8_t other[SWEET_FB_SWAP_REC_SIZE]={};fb.swap(other); // timeout cannot replace pending refs
 assert(fb.fPendingSurfaces[0]==&surface && surface.refs==2);
 fb.ready=true;tick(fb);assert(!fb.fDirty && surface.refs==1 && fb.presents==2);
 table[1]=&surface;fb.swap(rec);fb.fPowerOff=true;tick(fb);
 assert(!fb.fDirty && surface.refs==1 && fb.presents==2);
 fb.swap(rec);assert(!fb.fDirty && surface.refs==1); // screen off
 fb.fPowerOff=false;fb.swap(rec);fb.ready=false;
 for(unsigned i=0;i<10;i++)tick(fb);
 assert(!fb.fDirty && surface.refs==1); // bounded retry drops exactly once
}
'''
            (d / 'test.cpp').write_text(harness)
            subprocess.run(['clang++','-std=c++14','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined',str(d/'test.cpp'),'-o',str(d/'test')],check=True)
            subprocess.run([str(d/'test')],check=True)

if __name__ == '__main__': unittest.main()
