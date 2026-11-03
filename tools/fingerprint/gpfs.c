// SPDX-License-Identifier: GPL-2.0-only
/* GPFS wire layout: Qualcomm minkipc, also recovered from QcTrEE.sys. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#include "gpfs.h"

#define NAME_BYTES 256
#define MAX_TRANSFER 512000U
#define MAX_FILE (16U * 1024 * 1024)

static uint32_t get32(const unsigned char *p)
{
    uint32_t value;
    memcpy(&value, p, 4);
    return value;
}

static void put32(unsigned char *p, uint32_t value)
{
    memcpy(p, &value, 4);
}

static int private_directory(int fd)
{
    struct stat st;
    if (fstat(fd, &st))
        return -1;
    if (!S_ISDIR(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 077)) {
        errno = EACCES;
        return -1;
    }
    return 0;
}

int fp_gpfs_open_root(const char *path)
{
    int fd, saved;
    if (mkdir(path, 0700) && errno != EEXIST)
        return -1;
    fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0)
        return -1;
    if (private_directory(fd) || flock(fd, LOCK_EX | LOCK_NB)) {
        saved = errno;
        close(fd);
        errno = saved;
        return -1;
    }
    return fd;
}

/* Translate firmware paths to namespaces below the private directory. */
static int local_path(const unsigned char *wire, char *path, size_t capacity, uint32_t command)
{
    static const struct { const char *prefix, *space; } prefixes[] = {
        {"/persist/data/", "persist"},
        {"/data/misc/qsee/", "data"},
        {"/data/vendor/tzstorage/", "vendor"},
    };
    const char *text = (const char *)wire;
    if (!memchr(wire, 0, NAME_BYTES))
        return ENAMETOOLONG;
    if (*text != '/' && command >= 4 && command <= 11) {
        int n = snprintf(path, capacity, "%s/%s", command >= 8 ? "persist" : "data", text);
        return n < 0 || (size_t)n >= capacity ? ENAMETOOLONG : 0;
    }
    for (unsigned int i = 0; i < sizeof(prefixes) / sizeof(prefixes[0]); i++) {
        size_t len = strlen(prefixes[i].prefix);
        if (!strncmp(text, prefixes[i].prefix, len)) {
            int n = snprintf(path, capacity, "%s/%s", prefixes[i].space, text + len);
            return n < 0 || (size_t)n >= capacity ? ENAMETOOLONG : 0;
        }
    }
    return EACCES;
}

/* Resolve directories with fd-relative operations and reject traversal/symlinks. */
static int parent_directory(int rootfd, const char *path, int create, char *leaf)
{
    char copy[512], *cursor, *component;
    int fd = dup(rootfd), next, saved;
    if (fd < 0)
        return -1;
    if (snprintf(copy, sizeof(copy), "%s", path) >= (int)sizeof(copy)) {
        close(fd);
        errno = ENAMETOOLONG;
        return -1;
    }
    cursor = copy;
    while ((component = strsep(&cursor, "/"))) {
        if (!*component || !strcmp(component, ".") || !strcmp(component, "..") ||
            strlen(component) >= NAME_BYTES) {
            errno = EACCES;
            goto failure;
        }
        if (!cursor) {
            strcpy(leaf, component);
            return fd;
        }
        if (create && mkdirat(fd, component, 0700) && errno != EEXIST)
            goto failure;
        next = openat(fd, component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (next < 0)
            goto failure;
        if (private_directory(next)) {
            saved = errno;
            close(next);
            errno = saved;
            goto failure;
        }
        close(fd);
        fd = next;
    }
    errno = EINVAL;
failure:
    saved = errno;
    close(fd);
    errno = saved;
    return -1;
}

static int backup_file(int parent, const char *leaf, int fd)
{
    char backup[NAME_BYTES + 8];
    unsigned char data[65536];
    struct stat st;
    off_t offset = 0;
    int out, error = 0;
    if (fstat(fd, &st))
        return errno;
    if (!S_ISREG(st.st_mode) || st.st_size > MAX_FILE)
        return EFBIG;
    if (snprintf(backup, sizeof(backup), "%s.bak", leaf) >= NAME_BYTES)
        return ENAMETOOLONG;
    out = openat(parent, backup, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (out < 0)
        return errno;
    while (offset < st.st_size) {
        ssize_t count = pread(fd, data, sizeof(data), offset);
        if (count <= 0) { error = count < 0 ? errno : EIO; break; }
        ssize_t done = 0;
        while (done < count) {
            ssize_t written = write(out, data + done, count - done);
            if (written < 0 && errno == EINTR)
                continue;
            if (written <= 0) { error = written < 0 ? errno : EIO; break; }
            done += written;
        }
        if (error)
            break;
        offset += count;
    }
    if (!error && fsync(out))
        error = errno;
    close(out);
    return error;
}

int fp_gpfs_dispatch(int rootfd, unsigned char *buf, size_t size)
{
    uint32_t command, operation, count = 0, transferred = 0;
    int32_t offset = 0;
    char path[512] = {0}, target[512], leaf[NAME_BYTES], target_leaf[NAME_BYTES];
    int parent = -1, other_parent = -1, fd = -1, error = 0;
    struct stat st;
    if (size < 12)
        return -1;
    command = get32(buf);
    if (command == 12) {
        put32(buf + 4, 2); /* GP_FS_VERSION */
        put32(buf + 8, 0);
        return 0;
    }
    if (command > 11) {
        put32(buf + 4, (uint32_t)-1);
        return 0;
    }
    operation = command % 4;
    if (size < 4 + NAME_BYTES || (operation <= 1 && size < 272) ||
        (operation == 3 && size < 4 + 2 * NAME_BYTES))
        return -1;
    error = local_path(buf + 4, path, sizeof(path), command);
    if (error)
        goto response;
    if (operation <= 1) {
        offset = (int32_t)get32(buf + 260);
        count = get32(buf + 264);
        if (offset < 0 || count > MAX_TRANSFER || (uint64_t)offset + count > MAX_FILE ||
            (operation == 1 && count > size - 272) || (operation == 0 && count > size - 12)) {
            error = EINVAL;
            goto response;
        }
    }
    parent = parent_directory(rootfd, path, operation == 1, leaf);
    if (parent < 0) { error = errno; goto response; }
    if (operation == 0 || operation == 1) {
        fd = openat(parent, leaf, (operation == 1 ? O_RDWR | O_CREAT : O_RDONLY) |
                    O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0600);
        if (fd < 0) { error = errno; goto response; }
        if (fstat(fd, &st)) { error = errno; goto response; }
        if (!S_ISREG(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 077)) {
            error = EACCES;
            goto response;
        }
        if (operation == 1 && get32(buf + 268)) {
            error = backup_file(parent, leaf, fd);
            if (error)
                goto response;
        }
        while (transferred < count) {
            ssize_t done = operation == 0
                ? pread(fd, buf + 12 + transferred, count - transferred, offset + transferred)
                : pwrite(fd, buf + 272 + transferred, count - transferred, offset + transferred);
            if (done < 0 && errno == EINTR)
                continue;
            if (done < 0) { error = errno; break; }
            if (!done) { if (operation == 1) error = EIO; break; }
            transferred += done;
        }
        if (operation == 1 && !error && (fsync(fd) || fsync(parent)))
            error = errno;
    } else if (operation == 2) {
        if (unlinkat(parent, leaf, 0) || fsync(parent))
            error = errno;
    } else {
        error = local_path(buf + 260, target, sizeof(target), command);
        if (error)
            goto response;
        other_parent = parent_directory(rootfd, target, 0, target_leaf);
        if (other_parent < 0) { error = errno; goto response; }
        if (renameat(parent, leaf, other_parent, target_leaf) || fsync(parent) || fsync(other_parent))
            error = errno;
    }
response:
    if (fd >= 0) close(fd);
    if (parent >= 0) close(parent);
    if (other_parent >= 0) close(other_parent);
    put32(buf, command);
    put32(buf + 4, error);
    put32(buf + 8, error ? 0 : transferred);
    printf("gpfs command=%u path=%s offset=%d count=%u error=%d transferred=%u\n",
           command, path, offset, count, error, transferred);
    return 0;
}
