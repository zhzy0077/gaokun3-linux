/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GAOKUN_GPFS_H
#define GAOKUN_GPFS_H
#include <stddef.h>
int fp_gpfs_open_root(const char *path);
int fp_gpfs_dispatch(int rootfd, unsigned char *buffer, size_t size);
#endif
