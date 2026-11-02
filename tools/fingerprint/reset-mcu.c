// SPDX-License-Identifier: GPL-2.0-only
/* BIOS 2.16 SPBA reset: TLMM GPIO185 high 10ms, then low. */
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/gpio.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;

static void stop_child(int signo)
{
	interrupted = signo;
}

static void delay_ms(long ms)
{
	struct timespec delay = {.tv_sec = ms / 1000,
		.tv_nsec = (ms % 1000) * 1000000};
	while (nanosleep(&delay, &delay) && errno == EINTR)
		;
}

static int pulse(int fd)
{
	struct gpio_v2_line_config config = {
		.flags = GPIO_V2_LINE_FLAG_OUTPUT | GPIO_V2_LINE_FLAG_BIAS_PULL_UP,
		.num_attrs = 1,
		.attrs = {{.attr = {.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES,
			.values = 1}, .mask = 1}},
	};
	struct gpio_v2_line_values values = {.mask = 1, .bits = 0};
	if (ioctl(fd, GPIO_V2_LINE_SET_CONFIG_IOCTL, &config))
		return -1;
	printf("GPIO185 reset=high duration_ms=10\n");
	delay_ms(10);
	if (ioctl(fd, GPIO_V2_LINE_SET_VALUES_IOCTL, &values))
		return -1;
	printf("GPIO185 reset=low\n");
	delay_ms(100);
	return 0;
}

static int matching_board(void)
{
	char compatible[256] = {0}, bios[32] = {0};
	FILE *file = fopen("/sys/firmware/devicetree/base/compatible", "rb");
	if (!file)
		return 0;
	size_t size = fread(compatible, 1, sizeof(compatible) - 1, file);
	fclose(file);
	if (size < sizeof("huawei,gaokun3") || strcmp(compatible, "huawei,gaokun3"))
		return 0;
	file = fopen("/sys/class/dmi/id/bios_version", "r");
	if (!file)
		return 0;
	int matched = fgets(bios, sizeof(bios), file) && !strcmp(bios, "2.16\n");
	fclose(file);
	return matched;
}

int main(int argc, char **argv)
{
	struct gpio_v2_line_request request = {.offsets = {185}, .num_lines = 1};
	struct gpio_v2_line_info info = {.offset = 185};
	struct gpio_v2_line_values values = {.mask = 1};
	struct gpio_v2_line_config restore = {
		.flags = GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN};
	struct sigaction action = {.sa_handler = stop_child};
	glob_t chips = {0};
	int fd = -1, status = 1, child_status;
	pid_t child;
	setbuf(stdout, NULL);
	if (argc < 2) {
		fprintf(stderr, "Usage: %s COMMAND [ARGS...]\n", argv[0]);
		return 1;
	}
	if (!matching_board()) {
		fprintf(stderr, "Required board: huawei,gaokun3 BIOS 2.16\n");
		return 1;
	}
	if (glob("/dev/gpiochip*", 0, NULL, &chips))
		return 1;
	for (size_t i = 0; i < chips.gl_pathc; i++) {
		struct gpiochip_info chip = {0};
		fd = open(chips.gl_pathv[i], O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			continue;
		if (!ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &chip) &&
		    !strcmp(chip.label, "f100000.pinctrl") && chip.lines > 185)
			break;
		close(fd);
		fd = -1;
	}
	globfree(&chips);
	if (fd < 0) {
		fprintf(stderr, "TLMM controller unavailable\n");
		return 1;
	}
	if (ioctl(fd, GPIO_V2_GET_LINEINFO_IOCTL, &info) ||
	    (info.flags & GPIO_V2_LINE_FLAG_USED) ||
	    !(info.flags & GPIO_V2_LINE_FLAG_INPUT)) {
		fprintf(stderr, "Required GPIO185 state: unused input; flags=%#llx\n",
			(unsigned long long)info.flags);
		close(fd);
		return 1;
	}
	request.config = restore;
	strcpy(request.consumer, "gaokun-fingerprint-reset");
	if (ioctl(fd, GPIO_V2_GET_LINE_IOCTL, &request)) {
		perror("request GPIO185");
		close(fd);
		return 1;
	}
	close(fd);
	sigemptyset(&action.sa_mask);
	sigaction(SIGINT, &action, NULL);
	sigaction(SIGTERM, &action, NULL);
	if (ioctl(request.fd, GPIO_V2_LINE_GET_VALUES_IOCTL, &values) || values.bits) {
		fprintf(stderr, "Required GPIO185 level: low\n");
		goto out;
	}
	if (pulse(request.fd)) {
		perror("MCU reset");
		goto out;
	}
	if (interrupted)
		goto out;
	child = fork();
	if (child < 0) {
		perror("fork");
		goto out;
	}
	if (!child) {
		close(request.fd);
		signal(SIGINT, SIG_DFL);
		signal(SIGTERM, SIG_DFL);
		execvp(argv[1], argv + 1);
		perror("exec");
		_exit(127);
	}
	for (;;) {
		if (interrupted) {
			kill(child, interrupted);
			interrupted = 0;
		}
		if (waitpid(child, &child_status, 0) == child) {
			status = WIFEXITED(child_status) ? WEXITSTATUS(child_status) : 1;
			break;
		}
		if (errno != EINTR) {
			perror("waitpid");
			goto out;
		}
	}
	/* Reset after the client has unloaded its TA, returning MCU to boot state. */
	if (pulse(request.fd)) {
		perror("MCU cleanup reset");
		status = 1;
	}
out:
	if (ioctl(request.fd, GPIO_V2_LINE_SET_CONFIG_IOCTL, &restore)) {
		perror("restore GPIO185");
		status = 1;
	} else {
		printf("GPIO185 restored=input,pull-down\n");
	}
	close(request.fd);
	return status;
}
