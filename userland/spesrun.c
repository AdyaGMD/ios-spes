/*
 * spesrun [-o FILE] SECONDS PROGRAM [ARG...]: wait, then exec PROGRAM. With -o, stdout and stderr go
 * to FILE (appended; read from the next root snapshot) instead of the console. For one-shot test jobs in launchd.plist
 * (tools/add-launchd-job.py) that must start after the GPU service is up, e.g. /redwood/bin/vkprobe.
 * Output goes where the job's StandardOutPath says (the console, which the kernel log keeps).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

int
main(int argc, char **argv)
{
	const char *out = NULL;
	if (argc >= 3 && strcmp(argv[1], "-o") == 0) {
		out = argv[2];
		argv += 2;
		argc -= 2;
	}
	if (argc < 3) {
		fprintf(stderr, "usage: spesrun [-o FILE] SECONDS PROGRAM [ARG...]\n");
		return 2;
	}
	/*
	 * Output straight to the console: launchd's StandardOutPath=/dev/console output never reached
	 * the kernel's console tee (all33), while a process's own open() of /dev/console does.
	 */
	int fd = out ? open(out, O_WRONLY | O_CREAT | O_APPEND, 0644) : open("/dev/console", O_WRONLY | O_NOCTTY);
	if (fd >= 0) {
		dup2(fd, 1);
		dup2(fd, 2);
		if (fd > 2) {
			close(fd);
		}
	}
	sleep((unsigned)atoi(argv[1]));
	printf("spesrun: %s after %s s\n", argv[2], argv[1]);
	fflush(stdout);
	execv(argv[2], argv + 2);
	perror("spesrun: execv");
	return 1;
}
