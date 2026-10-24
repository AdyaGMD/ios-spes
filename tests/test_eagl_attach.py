"""Exercise the actual EAGL surface-to-target helper with mocked OpenGL."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'research/hackios-xnu-userland/userland/src/eagl.c'
PATCH = ROOT / 'tools/eagl-attach-gpu.patch'

PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef unsigned int GLenum;
typedef unsigned int GLuint;
typedef unsigned int GLbitfield;
typedef int GLint;
typedef int GLsizei;
#define GL_TEXTURE_2D 0x0de1
#define GL_RGBA 0x1908
#define GL_BGRA 0x80e1
#define GL_UNSIGNED_BYTE 0x1401
#define GL_READ_FRAMEBUFFER 0x8ca8
#define GL_DRAW_FRAMEBUFFER 0x8ca9
#define GL_READ_FRAMEBUFFER_BINDING 0x8caa
#define GL_DRAW_FRAMEBUFFER_BINDING 0x8ca6
#define GL_COLOR_ATTACHMENT0 0x8ce0
#define GL_FRAMEBUFFER_COMPLETE 0x8cd5
#define GL_COLOR_BUFFER_BIT 0x4000
#define GL_NEAREST 0x2600
struct eagl { GLuint reader, writer; };
struct image {
    GLenum to, internal, format, type;
    GLsizei width, height;
    bool invert;
    GLuint mirror, texture;
};
static GLenum internal_format(GLenum internal, GLenum format) {
    return format == GL_BGRA && internal == GL_RGBA ? GL_BGRA : internal;
}
static GLenum error;
static GLint had_width, had_height, had_format, read_bound, draw_bound;
static GLuint read_attachment, draw_attachment;
static int allocations, blits;
static bool null_allocation = true, complete = true, fail_blit;
static GLint blit_args[8];
static GLenum glGetError(void) { GLenum e = error; error = 0; return e; }
static void glGetTexLevelParameteriv(GLenum target, GLint level, GLenum name, GLint *value) {
    (void)target; (void)level;
    *value = name == 0x1000 ? had_width : name == 0x1001 ? had_height : had_format;
}
static void glTexImage2D(GLenum target, GLint level, GLint internal, GLsizei width, GLsizei height,
    GLint border, GLenum format, GLenum type, const void *pixels) {
    (void)target; (void)level; (void)border; (void)format; (void)type;
    allocations++; null_allocation = null_allocation && pixels == NULL;
    had_width = width; had_height = height; had_format = internal;
}
static void glGetIntegerv(GLenum name, GLint *value) {
    *value = name == GL_READ_FRAMEBUFFER_BINDING ? read_bound : draw_bound;
}
static void glGenFramebuffers(GLsizei count, GLuint *names) {
    (void)count; *names = *names == 0 ? 9 : 10;
}
static void glBindFramebuffer(GLenum target, GLuint name) {
    if (target == GL_READ_FRAMEBUFFER) read_bound = (GLint)name;
    else draw_bound = (GLint)name;
}
static void glFramebufferTexture2D(GLenum target, GLenum attachment, GLenum kind, GLuint texture, GLint level) {
    (void)attachment; (void)kind; (void)level;
    if (target == GL_READ_FRAMEBUFFER) read_attachment = texture;
    else draw_attachment = texture;
}
static GLenum glCheckFramebufferStatus(GLenum target) {
    (void)target; return complete ? GL_FRAMEBUFFER_COMPLETE : 0;
}
static void glBlitFramebuffer(GLint a, GLint b, GLint c, GLint d, GLint e, GLint f, GLint g, GLint h,
    GLbitfield mask, GLenum filter) {
    (void)mask; (void)filter;
    GLint values[8] = { a, b, c, d, e, f, g, h };
    blits++;
    for (int i = 0; i < 8; i++) blit_args[i] = values[i];
    if (fail_blit) error = 0x0501;
}
'''

SUFFIX = r'''
static struct eagl e;
static struct image image;
static void reset(void) {
    e = (struct eagl){0, 0};
    image = (struct image){ GL_TEXTURE_2D, GL_BGRA, GL_BGRA, GL_UNSIGNED_BYTE,
        1125, 2436, false, 33, 44 };
    error = 0; had_width = 1125; had_height = 2436; had_format = GL_BGRA;
    read_bound = 5; draw_bound = 6; read_attachment = draw_attachment = 0;
    allocations = blits = 0; null_allocation = true; complete = true; fail_blit = false;
}
int main(void) {
    reset();
    assert(surface_to_target(&e, &image));
    assert(allocations == 0 && blits == 1);
    assert(read_attachment == 33 && draw_attachment == 44);
    assert(read_bound == 5 && draw_bound == 6);
    GLint normal[8] = { 0, 0, 1125, 2436, 0, 0, 1125, 2436 };
    for (int i = 0; i < 8; i++) assert(blit_args[i] == normal[i]);

    reset(); image.invert = true;
    assert(surface_to_target(&e, &image));
    GLint inverted[8] = { 0, 2436, 1125, 0, 0, 0, 1125, 2436 };
    for (int i = 0; i < 8; i++) assert(blit_args[i] == inverted[i]);

    reset(); had_width = had_height = had_format = 0;
    assert(surface_to_target(&e, &image));
    assert(allocations == 1 && null_allocation && blits == 1);

    reset(); complete = false;
    assert(!surface_to_target(&e, &image));
    assert(blits == 0 && read_bound == 5 && draw_bound == 6);

    reset(); fail_blit = true;
    assert(!surface_to_target(&e, &image));
    assert(blits == 1 && read_bound == 5 && draw_bound == 6);
    puts("EAGL attach mock PASS");
    return 0;
}
'''


@unittest.skipUnless(SOURCE.exists() and shutil.which('clang'), 'pinned HackiOS source and clang required')
class EAGLAttachTests(unittest.TestCase):
    def test_gpu_fill_and_attach_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            source = tree / 'userland/src/eagl.c'
            source.parent.mkdir(parents=True)
            source.write_bytes(SOURCE.read_bytes())
            subprocess.run(['patch', '-s', '-p1', '-d', str(tree)], input=PATCH.read_bytes(),
                           check=True, capture_output=True)
            patched = source.read_text()
            start = patched.index('static bool\nsurface_to_target')
            end = patched.index('/* What has been drawn into a texture', start)
            helper = patched[start:end]
            self.assertNotIn('glFinish', helper)
            self.assertNotIn('glFlush', helper)
            self.assertNotIn('IOSurfaceLock', helper)
            self.assertIn('gpu_filled = mirrored && surface_to_target(e, image);', patched)
            self.assertIn('(mirrored && !gpu_filled) || (!mirrored && !surface_shared(e, image))', patched)
            original_tex = SOURCE.read_text().split('my_texImageIOSurface(', 1)[1].split(
                '/* (the "image" is the target', 1)[0]
            patched_tex = patched.split('my_texImageIOSurface(', 1)[1].split(
                '/* (the "image" is the target', 1)[0]
            self.assertEqual(original_tex, patched_tex)

            harness = tree / 'attach.c'
            executable = tree / 'attach'
            harness.write_text(PREFIX + helper + SUFFIX)
            subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            str(harness), '-o', str(executable)], check=True, capture_output=True)
            result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
            self.assertIn('EAGL attach mock PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
