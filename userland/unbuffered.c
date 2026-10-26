/*
 * Linked into on-phone test tools (vkprobe): stdout and stderr unbuffered from the start, so what a
 * tool printed reaches the console (and the kernel log) even if it hangs or is killed before exit().
 */
#include <stdio.h>

__attribute__((constructor)) static void
spes_unbuffered(void)
{
	setvbuf(stdout, NULL, _IONBF, 0);
	setvbuf(stderr, NULL, _IONBF, 0);
}
