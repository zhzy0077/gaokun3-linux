// SPDX-License-Identifier: GPL-2.0-only
/* Fixed FTE7001 bring-up commands through upstream qcomtee and UID 122. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <qcomtee_object_types.h>
#include "tests_private.h"
#include "qtee-listener.h"

#define IMAGE_SIZE 3669575
#define ACK 0x5aa5
#define MAX_PAYLOAD 32768

static volatile sig_atomic_t stopping;
static int automatic;
static int wait_finger(struct qcomtee_object *app, int present);

static void stop_client(int signo)
{
	stopping = signo;
}

struct frame {
	uint32_t command, input_size, output_size;
	unsigned char payload[MAX_PAYLOAD];
};

static int send_frame(struct qcomtee_object *app, uint32_t command,
		      const void *input, size_t input_size, size_t output_size,
		      struct frame *request, struct frame *response)
{
	struct qcomtee_param p[10] = {0};
	uint32_t is64 = 1;
	qcomtee_result_t result = -1;
	int ret;

	if (input_size > sizeof(request->payload) ||
	    output_size > sizeof(response->payload) || (input_size && !input))
		return -1;
	memset(request, 0, sizeof(*request));
	request->command = command;
	request->input_size = input_size;
	request->output_size = output_size;
	if (input_size)
		memcpy(request->payload, input, input_size);
	*response = *request;
	memset(response->payload, 0xa5, output_size);
	p[0].attr = QCOMTEE_UBUF_INPUT;
	p[0].ubuf = (struct qcomtee_ubuf){request, 12 + input_size};
	p[1].attr = QCOMTEE_UBUF_INPUT;
	p[1].ubuf = (struct qcomtee_ubuf){response, 12 + output_size};
	p[2].attr = QCOMTEE_UBUF_INPUT; /* No embedded address offsets. */
	p[3].attr = QCOMTEE_UBUF_INPUT;
	p[3].ubuf = (struct qcomtee_ubuf){&is64, sizeof(is64)};
	p[4].attr = QCOMTEE_UBUF_OUTPUT;
	p[4].ubuf = p[0].ubuf;
	p[5].attr = QCOMTEE_UBUF_OUTPUT;
	p[5].ubuf = p[1].ubuf;
	for (int i = 6; i < 10; i++)
		p[i].attr = QCOMTEE_OBJREF_INPUT; /* Four null memory objects. */
	ret = qcomtee_object_invoke(app, 0, p, 10, &result);
	printf("command=%#x transport=%d result=%d request_size=%zu response_size=%zu ack=%#x\n",
	       command, ret, result, p[4].ubuf.size, p[5].ubuf.size,
	       request->command);
	if (ret || result || request->command != ACK || request->output_size)
		return -1;
	return 0;
}

static void print_payload(const char *label, const unsigned char *p, size_t n)
{
	printf("%s=", label);
	for (size_t i = 0; i < n; i++)
		printf("%02x", p[i]);
	putchar('\n');
}

static int print_packets(const unsigned char *data, size_t size)
{
	int found = 0;
	for (size_t i = 0; i + 5 <= size; i++) {
		size_t length = ((size_t)data[i + 1] << 8) | data[i + 2];
		unsigned char checksum = 0;
		if (data[i] != 2 || !length || length + 4 > size - i)
			continue;
		for (size_t j = 1; j < length + 3; j++)
			checksum ^= data[i + j];
		if (checksum != data[i + length + 3])
			continue;
		printf("mcu_response command=%#x checksum=valid ", data[i + 3]);
		print_payload("payload", data + i + 4, length - 1);
		if (data[i + 3] == 4)
			found++;
		else if (data[i + 3] == 9)
			return -1;
		i += length + 3;
	}
	return found;
}

static int mcu_query_value(struct qcomtee_object *app, unsigned char command,
		     const unsigned char *payload, size_t size, const char *label,
		     unsigned char *value)
{
	struct frame request, response;
	unsigned char packet[64] = {2, 0, 0};
	unsigned char checksum = 0;
	if (size > sizeof(packet) - 5)
		return -1;
	packet[2] = size + 1;
	packet[3] = command;
	if (size)
		memcpy(packet + 4, payload, size);
	for (size_t i = 1; i < size + 4; i++)
		checksum ^= packet[i];
	packet[size + 4] = checksum;
	if (send_frame(app, 0x8021, packet, size + 5, 0, &request, &response))
		return -1;
	for (int attempt = 0; attempt < 10 && !stopping; attempt++) {
		usleep(20000);
		if (send_frame(app, 0x8020, NULL, 0, 64, &request, &response))
			return -1;
		print_payload(label, response.payload, 64);
		int packets = print_packets(response.payload, 64);
		if (packets < 0)
			return -1;
		if (!packets)
			continue;
		if (!value)
			return 0;
		for (size_t i = 0; i + 6 <= 64; i++) {
			const unsigned char *reply = response.payload + i;
			if (!memcmp(reply, "\x02\x00\x02\x04", 4) &&
			    (unsigned char)(reply[1] ^ reply[2] ^ reply[3] ^ reply[4]) == reply[5]) {
				*value = reply[4];
				return 0;
			}
		}
		return -1;
	}
	fprintf(stderr, "MCU reply timeout\n");
	return -1;
}

static int mcu_query(struct qcomtee_object *app, unsigned char command,
		     const unsigned char *payload, size_t size, const char *label)
{
	return mcu_query_value(app, command, payload, size, label, NULL);
}

static int ta_read_image(struct qcomtee_object *app)
{
	const unsigned char packet[] = {2, 0, 3, 0x8e, 0x76, 0, 0xfb};
	struct frame request, response;
	if (send_frame(app, 0x8021, packet, sizeof(packet), 0, &request, &response))
		return -1;
	usleep(150000);
	/* TA reads the complete encrypted MCU frame, decrypts and normalizes it. */
	if (send_frame(app, 0x802c, NULL, 0, 0, &request, &response) ||
	    send_frame(app, 0x802d, NULL, 0, 4, &request, &response))
		return -1;
	print_payload("ta_image_info", response.payload, 4);
	printf("ta_image_quality=%u area=%u\n", response.payload[0], response.payload[1]);
	return 0;
}

static int ta_image_quality(struct qcomtee_object *app, int wait_for_finger)
{
	const unsigned char enter_detect[] = {0x71, 2};
	if (mcu_query(app, 0x8e, enter_detect, sizeof(enter_detect), "enter_detect"))
		return -1;
	if (wait_for_finger) {
		printf("ready_for_ta_image; send newline with finger in place\n");
		if ((!automatic && getchar() != '\n') || stopping)
			return -1;
		if (automatic && wait_finger(app, 1))
			return -1;
		usleep(150000);
	}
	return ta_read_image(app);
}

static int wait_finger(struct qcomtee_object *app, int present)
{
	const unsigned char query[] = {0x73, 1};
	printf("await_finger=%s\n", present ? "on" : "off");
	for (int poll = 0; poll < 600 && !stopping; poll++) {
		unsigned char state;
		int ret = -1;
		/* This status request is idempotent; resend if the MCU was scanning. */
		for (int attempt = 0; attempt < 3 && ret && !stopping; attempt++)
			ret = mcu_query_value(app, 0x8e, query, sizeof(query), "finger_state", &state);
		if (ret)
			return -1;
		if ((state == 5) == present)
			return 0;
		usleep(200000);
	}
	fprintf(stderr, "finger transition timeout or interrupted\n");
	return -1;
}

static int enroll_series(struct qcomtee_object *app)
{
	const unsigned char enter_detect[] = {0x71, 2};
	unsigned char identity[69] = {0};
	struct frame request, response;
	int32_t result;
	if (mcu_query(app, 0x8e, enter_detect, sizeof(enter_detect), "enter_detect"))
		return -1;
	printf("ready_for_enrollment_series; send newline then lift/place the same finger 24 times\n");
	if ((!automatic && getchar() != '\n') || stopping)
		return -1;
	/* The pinned vendor enrollment configuration requests 24 images. */
	unsigned char sample = 0;
	for (int attempt = 0; attempt < 100 && sample < 24; attempt++) {
		if (attempt && wait_finger(app, 0))
			return -1;
		if (wait_finger(app, 1))
			return -1;
		/* MCU publishes state 5 before its foreground image scan completes. */
		usleep(150000);
		result = -1;
		for (int capture = 0; capture < 3 && !stopping; capture++) {
			if (ta_read_image(app) ||
			    send_frame(app, 0x8026, &sample, 1, 4, &request, &response))
				return -1;
			memcpy(&result, response.payload, sizeof(result));
			printf("enrollment_sample_index=%u result=%d capture=%d\n",
			       sample, result, capture);
			if (result != -3 && result != -4)
				break;
			usleep(150000);
		}
		if (stopping)
			return -1;
		if (!result) {
			sample++;
			printf("enrollment_progress=%u/24\n", sample);
		} else
			printf("enrollment_retry=%d\n", result);
	}
	if (sample != 24)
		return -1;
	/* 68 opaque identity bytes followed by slot 0. Authorized template rebuild. */
	memcpy(identity, "gaokun3-linux-experiment", sizeof("gaokun3-linux-experiment"));
	if (send_frame(app, 0x802b, identity, sizeof(identity), 8, &request, &response))
		return -1;
	memcpy(&result, response.payload, sizeof(result));
	printf("template_commit_result=%d slot=%u\n", result, response.payload[4]);
	if (result)
		return -1;
	if (send_frame(app, 0x802f, NULL, 0, 4, &request, &response))
		return -1;
	print_payload("template_state_after_commit", response.payload, 4);
	uint32_t count;
	memcpy(&count, response.payload, sizeof(count));
	printf("loaded_template_count_after_commit=%u\n", count);
	return count == 1 ? 0 : -1;
}

int main(int argc, char **argv)
{
	struct qcomtee_object *root = NULL, *env = NULL, *loader = NULL, *app = NULL;
	struct fp_listener *listeners[2] = {NULL, NULL};
	struct qcomtee_param p[4] = {0};
	const char name[] = "fingerpr";
	struct frame request, response;
	unsigned char *image = NULL;
	char dist[256] = {0};
	qcomtee_result_t result = -1;
	FILE *file;
	uint32_t status;
	int ret, exit_status = 1;
	const char *mode = argc >= 3 ? argv[2] : "listener-template-count";
	automatic = getenv("GAOKUN3_FP_AUTOMATIC") &&
		!strcmp(getenv("GAOKUN3_FP_AUTOMATIC"), "1");

	setbuf(stdout, NULL);
	if (argc < 2 || argc > 3 ||
	    (strcmp(mode, "listener-template-count") &&
	     strcmp(mode, "listener-enroll-series-wait") &&
	     strcmp(mode, "listener-verify-wait") &&
	     strcmp(mode, "listener-delete-template"))) {
		fprintf(stderr, "Usage: %s VERIFIED_IMAGE [listener-template-count|listener-enroll-series-wait|listener-verify-wait|listener-delete-template]\n", argv[0]);
		return 1;
	}
	mode += strlen("listener-");
	struct sigaction action = {.sa_handler = stop_client};
	sigemptyset(&action.sa_mask);
	sigaction(SIGINT, &action, NULL);
	sigaction(SIGTERM, &action, NULL);
	file = fopen(argv[1], "rb");
	if (!file) {
		perror("firmware");
		return 1;
	}
	image = malloc(IMAGE_SIZE);
	if (!image || fread(image, 1, IMAGE_SIZE, file) != IMAGE_SIZE ||
	    fgetc(file) != EOF) {
		fprintf(stderr, "firmware_size_error\n");
		fclose(file);
		goto out;
	}
	fclose(file);
	root = test_get_root();
	if (!root)
		goto out;
	env = test_get_client_env_object(root);
	if (!env)
		goto out;
	listeners[0] = fp_listener_start(root, env, 0x7000, 504 * 1024,
					  "/var/lib/gaokun3-fingerprint/secure-files");
	if (!listeners[0])
		goto out;
	listeners[1] = fp_listener_start(root, env, 10, 20 * 1024, NULL);
	if (!listeners[1])
		goto out;
	loader = test_get_service_object(env, 122);
	if (!loader)
		goto out;
	p[0].attr = QCOMTEE_UBUF_INPUT;
	p[0].ubuf = (struct qcomtee_ubuf){image, IMAGE_SIZE};
	p[1].attr = QCOMTEE_UBUF_INPUT;
	p[1].ubuf = (struct qcomtee_ubuf){(void *)name, sizeof(name) - 1};
	p[2].attr = QCOMTEE_UBUF_OUTPUT;
	p[2].ubuf = (struct qcomtee_ubuf){dist, sizeof(dist)};
	p[3].attr = QCOMTEE_OBJREF_OUTPUT;
	ret = qcomtee_object_invoke(loader, 1, p, 4, &result);
	printf("load transport=%d result=%d distinguished_name=%.*s\n",
	       ret, result, (int)sizeof(dist), dist);
	if (ret || result)
		goto out;
	app = p[3].object;
	if (!app)
		goto out;
	if (stopping)
		goto unload;
	if (send_frame(app, 0x8031, NULL, 0, 4, &request, &response))
		goto unload;
	memcpy(&status, response.payload, sizeof(status));
	printf("status=%#x\n", status);
	if (status == 0xa5a5a5a5)
		goto unload;
	uint32_t count;
	if (send_frame(app, 0x802f, NULL, 0, 4, &request, &response))
		goto unload;
	memcpy(&count, response.payload, sizeof(count));
	print_payload("loaded_template_state", response.payload, 4);
	printf("loaded_template_count=%u\n", count);
	if (count > 20)
		goto unload;
	if (!strcmp(mode, "enroll-series-wait")) {
		if (count || enroll_series(app))
			goto unload;
	} else if (!strcmp(mode, "verify-wait")) {
		int32_t match;
		unsigned char options[16] = {0}, expected_identity[68] = {0};
		if (!count || ta_image_quality(app, 1) ||
		    send_frame(app, 0x8027, options, sizeof(options), 73, &request, &response))
			goto unload;
		memcpy(&match, response.payload, sizeof(match));
		memcpy(expected_identity, "gaokun3-linux-experiment",
		       sizeof("gaokun3-linux-experiment"));
		int identity_matches = !memcmp(response.payload + 4, expected_identity,
					       sizeof(expected_identity));
		printf("verify_result=%d matched_slot=%u\n", match, response.payload[72]);
		printf("matched_experiment_identity=%d\n", identity_matches);
		if (match || !identity_matches ||
		    response.payload[72] != 0)
			goto unload;
	} else if (!strcmp(mode, "delete-template")) {
		if (count > 1 || send_frame(app, 0x8030, NULL, 0, 0, &request, &response) ||
		    send_frame(app, 0x802f, NULL, 0, 4, &request, &response))
			goto unload;
		memcpy(&count, response.payload, sizeof(count));
		printf("template_count_after_delete=%u\n", count);
		if (count)
			goto unload;
	}
	exit_status = stopping ? 128 + stopping : 0;
unload:
	result = -1;
	ret = qcomtee_object_invoke(app, 2, NULL, 0, &result);
	printf("unload transport=%d result=%d\n", ret, result);
	if (ret || result) {
		printf("unload_failed; retaining client pid=%ld\n", (long)getpid());
		for (;;)
			pause();
	}
out:
	qcomtee_object_refs_dec(app);
	for (int i = 1; i >= 0; i--)
		if (fp_listener_stop(listeners[i]))
			for (;;)
				pause();
	qcomtee_object_refs_dec(loader);
	qcomtee_object_refs_dec(env);
	qcomtee_object_refs_dec(root);
	free(image);
	if (stopping)
		exit_status = 128 + stopping;
	return exit_status;
}
