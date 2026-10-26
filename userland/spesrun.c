/*
 * spesrun SECONDS PROGRAM [ARG...]: wait, then exec PROGRAM. For one-shot test jobs in launchd.plist
 * (tools/add-launchd-job.py) that must start after the GPU service is up, e.g. /redwood/bin/vkprobe.
 * Output goes where the job's StandardOutPath says (the console, which the kernel log keeps).
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int
main(int argc, char **argv)
{
	if (argc < 3) {
		fprintf(stderr, "usage: spesrun SECONDS PROGRAM [ARG...]\n");
		return 2;
	}
	sleep((unsigned)atoi(argv[1]));
	printf("spesrun: %s after %s s\n", argv[2], argv[1]);
	fflush(stdout);
	execv(argv[2], argv + 2);
	perror("spesrun: execv");
	return 1;
}
