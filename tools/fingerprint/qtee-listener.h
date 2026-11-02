/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GAOKUN_QTEE_LISTENER_H
#define GAOKUN_QTEE_LISTENER_H
#include <stdint.h>
#include <qcomtee_object_types.h>
struct fp_listener;
struct fp_listener *fp_listener_start(struct qcomtee_object *root,
                                    struct qcomtee_object *env, uint32_t id,
                                    size_t memory_bytes, const char *storage_path);
int fp_listener_stop(struct fp_listener *listener);
#endif
