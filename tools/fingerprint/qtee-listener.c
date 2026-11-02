// SPDX-License-Identifier: GPL-2.0-only
/* Qualcomm minkipc IRegisterListenerCBO, pinned in docs/fingerprint.md. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "qtee-listener.h"
#include "gpfs.h"

struct fp_listener {
    struct qcomtee_object callback;
    struct qcomtee_object *memory, *registrar;
    uint32_t id, is64, offsets[4];
    int directory;
};

static void release_listener(struct qcomtee_object *object)
{
    struct fp_listener *l = container_of(object, struct fp_listener, callback);
    printf("listener_callback_release id=%#x\n", l->id);
    qcomtee_memory_object_release(l->memory);
    if (l->directory >= 0)
        close(l->directory);
    free(l);
}

static qcomtee_result_t listener_request(struct qcomtee_object *object,
                                       qcomtee_op_t op,
                                       struct qcomtee_param *p, int num)
{
    struct fp_listener *l = container_of(object, struct fp_listener, callback);
    unsigned char *buf;
    size_t size;
    uint32_t command;
    int32_t error;
    if (op == 1 && num == 0)
        return QCOMTEE_OK; /* Single supplicant serializes requests. */
    if (!l->memory)
        return QCOMTEE_ERROR_UNAVAIL;
    buf = qcomtee_memory_object_addr(l->memory);
    size = qcomtee_memory_object_size(l->memory);
    if (op || num != 6 || p[0].attr != QCOMTEE_UBUF_OUTPUT ||
        p[1].attr != QCOMTEE_UBUF_OUTPUT || p[1].ubuf.size < 4)
        return QCOMTEE_ERROR_INVALID;
    for (int i = 2; i < 6; i++)
        if (p[i].attr != QCOMTEE_OBJREF_OUTPUT)
            return QCOMTEE_ERROR_INVALID;
    if (size < 272)
        return QCOMTEE_ERROR_INVALID;
    memcpy(&command, buf, 4);
    printf("listener_request id=%#x command=%#x\n", l->id, command);
    if (l->id != 0x7000)
        return QCOMTEE_ERROR_UNAVAIL;
    if (l->directory >= 0) {
        if (fp_gpfs_dispatch(l->directory, buf, size))
            return QCOMTEE_ERROR_INVALID;
    } else {
        error = ENOENT;
        if (command == 1 || command == 5 || command == 9)
            error = EOPNOTSUPP;
        memset(buf, 0, size);
        memcpy(buf, &command, 4);
        memcpy(buf + 4, &error, 4);
    }
    p[0].ubuf.addr = l->offsets;
    p[0].ubuf.size = 0;
    p[1].ubuf.addr = &l->is64;
    p[1].ubuf.size = sizeof(l->is64);
    for (int i = 2; i < 6; i++)
        p[i].object = NULL;
    return QCOMTEE_OK;
}

static struct qcomtee_object_ops listener_ops = {
    .release = release_listener,
    .dispatch = listener_request,
};

int fp_listener_stop(struct fp_listener *l)
{
    if (!l)
        return 0;
    qcomtee_object_refs_dec(l->registrar);
    l->registrar = NULL;
    /* Keep the caller's reference until QTEE releases its registration reference. */
    for (int i = 0; i < 500 && atomic_load(&l->callback.refs) != 1; i++)
        usleep(10000);
    if (atomic_load(&l->callback.refs) != 1) {
        printf("listener_release_pending id=%#x refs=%d; retaining client pid=%ld\n",
               l->id, atomic_load(&l->callback.refs), (long)getpid());
        return -1;
    }
    printf("listener_registration_released id=%#x\n", l->id);
    qcomtee_object_refs_dec(&l->callback);
    return 0;
}

struct fp_listener *fp_listener_start(struct qcomtee_object *root,
                                    struct qcomtee_object *env, uint32_t id,
                                    size_t memory_bytes, const char *storage_path)
{
    uint32_t uid = 87;
    struct qcomtee_param p[3] = {0};
    qcomtee_result_t result = -1;
    struct fp_listener *l = calloc(1, sizeof(*l));
    int ret;
    if (!l || (id != 0x7000 && id != 10)) {
        free(l);
        return NULL;
    }
    l->id = id;
    l->is64 = 1;
    l->directory = -1;
    if (storage_path) {
        l->directory = fp_gpfs_open_root(storage_path);
        if (l->directory < 0) {
            perror("gpfs storage root");
            free(l);
            return NULL;
        }
    }
    if (memory_bytes && qcomtee_memory_object_alloc(memory_bytes, root, &l->memory)) {
        if (l->directory >= 0) close(l->directory);
        free(l);
        return NULL;
    }
    if (qcomtee_object_cb_init(&l->callback, &listener_ops, root)) {
        qcomtee_memory_object_release(l->memory);
        if (l->directory >= 0) close(l->directory);
        free(l);
        return NULL;
    }
    p[0].attr = QCOMTEE_UBUF_INPUT;
    p[0].ubuf = (struct qcomtee_ubuf){&uid, sizeof(uid)};
    p[1].attr = QCOMTEE_OBJREF_OUTPUT;
    ret = qcomtee_object_invoke(env, 0, p, 2, &result);
    printf("listener_service_open transport=%d result=%d\n", ret, result);
    if (ret || result || !p[1].object)
        goto failure;
    l->registrar = p[1].object;
    memset(p, 0, sizeof(p));
    p[0].attr = QCOMTEE_UBUF_INPUT;
    p[0].ubuf = (struct qcomtee_ubuf){&l->id, sizeof(l->id)};
    p[1].attr = QCOMTEE_OBJREF_INPUT;
    p[1].object = &l->callback;
    p[2].attr = QCOMTEE_OBJREF_INPUT;
    p[2].object = l->memory;
    qcomtee_object_refs_inc(&l->callback); /* Donated reference, plus caller reference. */
    ret = qcomtee_object_invoke(l->registrar, 0, p, 3, &result);
    printf("listener_register id=%#x memory_bytes=%zu transport=%d result=%d\n",
           id, memory_bytes, ret, result);
    if (ret || result)
        goto failure;
    return l;
failure:
    if (fp_listener_stop(l))
        for (;;)
            pause();
    return NULL;
}
