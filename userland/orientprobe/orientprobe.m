// orientprobe: where does a texture's vertical orientation go wrong under NegroniMetal (metal2vulkan over Turnip)?
// carenderprobe (all37/all38) showed CoreAnimation's images and text upside down while its geometry was right.
// Each path below gets an 8x8 RGBA8 pattern that is different in every row and column (R = 32x, G = 32y, B = 255 in the
// top half), and the result is read back and called "upright", "flipped" (rows reversed) or "other":
//   upload     replaceRegion, then getBytes of the same texture
//   sample-*   the texture drawn into an 8x8 target by sampled_fragment (samples at position.xy / 8: target pixel (x, y)
//              reads texel (x, y), no texture coordinates involved), then getBytes of the target
//              sample-upload (replaceRegion), sample-nocopy (newTextureWithBytesNoCopy: CoreAnimation's image path),
//              sample-buffer (a texture over a buffer)
//   gpu        an 8x8 texture cleared blue with its top half drawn red (colored_vertex/colored_fragment, Metal's clip
//              space: y = +1 is the top), read back; then sample-gpu, the same texture sampled
// Shaders: metal2vulkan's runtime_examples fixture (Apple's metal output), in /usr/local/share/negronimetal/orientprobe.metallib.
//   orientprobe [METALLIB]
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/message.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define N 8
static uint32_t pattern[N * N];
static id<MTLDevice> dev;
static id<MTLCommandQueue> queue;
static id<MTLRenderPipelineState> sampled, colored;

static uint32_t texel(int x, int y) { return (uint32_t)(x * 32) | ((uint32_t)(y * 32) << 8) | ((y < N / 2 ? 255u : 0u) << 16) | 0xff000000u; }

static const char *verdict(const uint32_t *got, const uint32_t *want, int *bad)
{
	int same = 0, flip = 0;
	for (int y = 0; y < N; y++) for (int x = 0; x < N; x++) {
		same += got[y * N + x] == want[y * N + x];
		flip += got[y * N + x] == want[(N - 1 - y) * N + x];
	}
	*bad = N * N - same;
	return same == N * N ? "upright" : flip == N * N ? "FLIPPED (rows reversed)" : "other";
}

static void show(const char *name, const uint32_t *got, const uint32_t *want)
{
	int bad;
	const char *v = verdict(got, want, &bad);
	printf("orientprobe: %-14s %s (%d of %d texels differ); row 0: %08x %08x .. row 7: %08x\n", name, v, bad, N * N,
	    got[0], got[1], got[(N - 1) * N]);
}

static void readTex(id<MTLTexture> t, uint32_t *out) { [t getBytes:out bytesPerRow:N * 4 fromRegion:MTLRegionMake2D(0, 0, N, N) mipmapLevel:0]; }

static id<MTLTexture> target(void)
{
	MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:N height:N mipmapped:NO];
	d.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
	d.storageMode = MTLStorageModeShared;
	return [dev newTextureWithDescriptor:d];
}

// two triangles over clip space (colored_vertex: float2 positions in buffer 0, float4 colours in buffer 1); y0..y1 in clip y
static void draw(id<MTLRenderCommandEncoder> e, float y0, float y1, float r, float g, float b)
{
	float pos[12] = { -1, y0, 1, y0, -1, y1, 1, y0, 1, y1, -1, y1 };
	float col[24];
	for (int i = 0; i < 6; i++) { col[i * 4] = r; col[i * 4 + 1] = g; col[i * 4 + 2] = b; col[i * 4 + 3] = 1; }
	[e setVertexBytes:pos length:sizeof(pos) atIndex:0];
	[e setVertexBytes:col length:sizeof(col) atIndex:1];
	[e drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:6];
}

static id<MTLTexture> pass(id<MTLTexture> source, bool gpuDraw)
{
	id<MTLTexture> t = target();
	MTLRenderPassDescriptor *rp = [MTLRenderPassDescriptor renderPassDescriptor];
	rp.colorAttachments[0].texture = t;
	rp.colorAttachments[0].loadAction = MTLLoadActionClear;
	rp.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 1, 1);
	rp.colorAttachments[0].storeAction = MTLStoreActionStore;
	id<MTLCommandBuffer> cb = [queue commandBuffer];
	id<MTLRenderCommandEncoder> e = [cb renderCommandEncoderWithDescriptor:rp];
	if (gpuDraw) {
		[e setRenderPipelineState:colored];
		draw(e, 0, 1, 1, 0, 0);                 // the top half (clip y 0..1) red
	} else {
		[e setRenderPipelineState:sampled];
		[e setFragmentTexture:source atIndex:0];
		draw(e, -1, 1, 0, 0, 0);
	}
	[e endEncoding];
	[cb commit];
	[cb waitUntilCompleted];
	if (cb.status != MTLCommandBufferStatusCompleted) {
		printf("orientprobe: command buffer status %ld: %s\n", (long)cb.status, cb.error.description.UTF8String ?: "");
	}
	return t;
}

int main(int argc, char **argv)
{
	@autoreleasepool {
		setvbuf(stdout, NULL, _IONBF, 0);
		const char *path = argc > 1 ? argv[1] : "/usr/local/share/negronimetal/orientprobe.metallib";
		dev = MTLCreateSystemDefaultDevice();
		if (!dev) { printf("orientprobe: FAIL no Metal device\n"); return 2; }
		printf("orientprobe: device %s\n", dev.name.UTF8String);
		queue = [dev newCommandQueue];
		NSError *err = nil;
		id<MTLLibrary> lib = [dev newLibraryWithURL:[NSURL fileURLWithPath:@(path)] error:&err];
		if (!lib) { printf("orientprobe: FAIL library %s: %s\n", path, err.description.UTF8String); return 1; }
		MTLRenderPipelineDescriptor *pd = [MTLRenderPipelineDescriptor new];
		pd.vertexFunction = [lib newFunctionWithName:@"colored_vertex"];
		pd.fragmentFunction = [lib newFunctionWithName:@"sampled_fragment"];
		pd.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
		sampled = [dev newRenderPipelineStateWithDescriptor:pd error:&err];
		if (!sampled) { printf("orientprobe: FAIL sampled pipeline: %s\n", err.description.UTF8String); return 1; }
		pd.fragmentFunction = [lib newFunctionWithName:@"colored_fragment"];
		colored = [dev newRenderPipelineStateWithDescriptor:pd error:&err];
		if (!colored) { printf("orientprobe: FAIL colored pipeline: %s\n", err.description.UTF8String); return 1; }

		for (int y = 0; y < N; y++) for (int x = 0; x < N; x++) pattern[y * N + x] = texel(x, y);
		uint32_t got[N * N];
		MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:N height:N mipmapped:NO];
		d.usage = MTLTextureUsageShaderRead;
		d.storageMode = MTLStorageModeShared;

		id<MTLTexture> up = [dev newTextureWithDescriptor:d];
		[up replaceRegion:MTLRegionMake2D(0, 0, N, N) mipmapLevel:0 withBytes:pattern bytesPerRow:N * 4];
		readTex(up, got); show("upload", got, pattern);
		readTex(pass(up, false), got); show("sample-upload", got, pattern);

		// rows padded to the device's linear alignment, as newTextureWithBytesNoCopy and a texture over a buffer read them
		NSUInteger align = [dev minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatRGBA8Unorm];
		NSUInteger pitch = (N * 4 + align - 1) / align * align;
		printf("orientprobe: linear pitch %lu (alignment %lu)\n", (unsigned long)pitch, (unsigned long)align);
		size_t page = (size_t)getpagesize();
		void *mem = NULL;
		posix_memalign(&mem, page, page);
		memset(mem, 0, page);
		for (int y = 0; y < N; y++) memcpy((uint8_t *)mem + y * pitch, &pattern[y * N], N * 4);
		id<MTLTexture> nc = nil;
		SEL nocopy = @selector(newTextureWithBytesNoCopy:length:descriptor:deallocator:);
		if ([dev respondsToSelector:nocopy]) {
			nc = ((id<MTLTexture> (*)(id, SEL, void *, NSUInteger, MTLTextureDescriptor *, id))objc_msgSend)(dev, nocopy, mem,
			    page, d, nil);
		}
		if (nc) {
			readTex(nc, got); show("nocopy", got, pattern);
			readTex(pass(nc, false), got); show("sample-nocopy", got, pattern);
		} else {
			printf("orientprobe: sample-nocopy  not made (newTextureWithBytesNoCopy refused or missing)\n");
		}

		id<MTLBuffer> buf = [dev newBufferWithLength:page options:MTLResourceStorageModeShared];
		for (int y = 0; y < N; y++) memcpy((uint8_t *)buf.contents + y * pitch, &pattern[y * N], N * 4);
		id<MTLTexture> ob = [buf newTextureWithDescriptor:d offset:0 bytesPerRow:pitch];
		if (ob) {
			readTex(ob, got); show("buffer", got, pattern);
			readTex(pass(ob, false), got); show("sample-buffer", got, pattern);
		} else {
			printf("orientprobe: sample-buffer  not made (texture over buffer refused)\n");
		}

		uint32_t want[N * N];
		for (int y = 0; y < N; y++) for (int x = 0; x < N; x++) want[y * N + x] = y < N / 2 ? 0xff0000ffu : 0xffff0000u;
		id<MTLTexture> g = pass(nil, true);
		readTex(g, got); show("gpu", got, want);
		readTex(pass(g, false), got); show("sample-gpu", got, want);
		printf("orientprobe: done\n");
	}
	return 0;
}
