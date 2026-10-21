# right-0903 基线 + DSI/PLL 修复交接

更新时间：2026-10-21（Asia/Shanghai）。工作目录：`/home/zhzy0077/Code/linux-gaokun-buildbot`。

## 当前结果

已本地构建并安装 `7.3.0-right1-gaokun3-el2`。用户在追加 DSI/PLL 单补丁后重启，并反馈“设备已经启动”。本次核查 `uname -r` 与启动项均确认正在运行此版本，MSM 已初始化并接管 framebuffer。

当前源码范围是 Linux v7.3 + right-0903 的 recommended、el2 补丁集、板级设备树与触屏驱动，再额外加入本仓库 `others/0007`。这是用户逐步明确授权的范围；继续工作时保持单补丁增量验证。

## 来源与适配

| 项目 | 固定来源 / 说明 |
| --- | --- |
| Linux 基线 | torvalds/linux v7.3，`c03c1a14507dfaf8b856c2608f9ac216021fc222` |
| right-0903 参考 | https://github.com/right-0903/linux-gaokun ，`7463df37160bdecc3f2609d72f9a69cfa2b390e4` |
| 补丁集 | recommended 14 项、el2 24 项；EL2 0006 与 0010 的功能由 v7.3 代码覆盖 |
| 板级设备树 | 同一参考提交；PCIe reset/wake GPIO 属性迁移到 v7.3 端口节点 |
| 触屏 | 参考仓库 `touchscreen-hx83121a-dkms/himax-spi.c`，集成为 `himax-gaokun-right` 模块 |
| 额外补丁 | [0007-drm-msm-dsi-restore-bonded-PLL-initialization.patch](../patches/others/0007-drm-msm-dsi-restore-bonded-PLL-initialization.patch) |

v7.3 移植保留了上游 handover IRQ helper、异步 remoteproc attach 和 PAS 状态检查，并适配旧 PAS shutdown helper 命名与 RPMsg 接口。详细源码及配置哈希、移植记录保存在构建目录。

历史解释纠正：参考提交删除了 negligible 中的 MDSS 副本；recommended/0005 仍保留对应 cpu-cfg 路径。本次基线包含该功能。

## DSI/PLL 问题与唯一追加补丁

首次 right-only 启动后，用户报告屏幕仅显示白线，与此前双 DSI PLL 回归现象相符。随后明确要求“仅添加这个 patch，并更新到 ESP 中”。

0007 恢复上游 `93c97bc8d85d`（Neil Armstrong，`drm/msm: dsi: fix PLL init in bonded mode`）的初始化修复；此前回退提交为 `5de981b7db1f`。补丁将 PLL bias 引用计数管理保留在 PLL helpers 中，并在每次 enable 时编程 bias，适配双 DSI 共用 PLL 的初始化顺序。

它只修改 `drivers/gpu/drm/msm/dsi/phy/dsi_phy.h` 和 `dsi_phy_7nm.c`，已通过应用及反向应用检查。其余原基线清单中的源码哈希一致。

增量编译耗时约 54 秒，重新生成 MSM 模块并 strip、签名、安装，随后重建 initramfs。修复位于模块中，所以 EFI 内核与 DTB 哈希保持原值；initramfs 和来源清单已更新。版本名保留，区分更新前后应使用文件哈希。

## 构建与安装位置

统一构建目录：`/home/zhzy0077/.cache/gaokun-right-build`（下文简称 B）。

| 路径 | 内容 |
| --- | --- |
| `B/source/`、`B/out/` | 当前含 PLL 修复的源码、增量编译产物 |
| `B/build.sh` | 构建脚本，4 路并行 |
| `B/source-manifest.json` | 参考补丁、配置、最终源码哈希，additional_patches 记录唯一追加项 |
| `B/right-only-v7.3.patch` | 原始 right-only 相对 pristine v7.3 的差异 |
| `B/right-plus-pll-v7.3.patch` | 当前完整差异 |
| `B/port-records/`、`B/port-*.py` | v7.3 适配记录 |
| `B/logs/build.log`、`B/logs/build-pll.log` | 首次完整构建、PLL 增量构建日志 |
| `B/pll-install-verification.json` | 更新安装凭据，含 initramfs 内 MSM 一致性核验 |
| `B/boot-pll-verification.json` | 本次重启后的版本、命令行、哈希与显示日志核查 |
| `B/logs/boot-pll-success-kernel.log` | 本次启动完整 kernel journal |
| `B/before-pll/esp/`、`B/before-pll/msm.ko` | 单补丁更新前的 ESP 文件、MSM 模块备份 |
| `/usr/lib/modules/7.3.0-right1-gaokun3-el2/` | 安装模块 |
| `/boot/efi/gaokun-right1/` | linux.efi、initramfs.img、gaokun3-el2.dtb、source-manifest.json |
| `/boot/efi/loader/entries/gaokun-right1.conf` | 本次选中的启动项 |

启动菜单标题：**Fedora 44 - right-0903 baseline (Linux 7.3 EL2)**。

原默认启动项仍是 **Fedora 44 - Gaokun3 EL2 Release 13**（`7.2.9-gaokun3-el2+`），可从菜单选择返回旧内核。ESP 为 `/dev/nvme0n1p1`，更新后约剩余 16 MiB；新增独立产物前需计算容量。更新前备份位于根文件系统。

工具链环境：`source /home/zhzy0077/.config/gaokun/kernel-env.sh`。使用系统 GCC 16.2.1、Rust 1.99.0、LLVM 22.1.8，独立 ccache，ARCH=arm64。首次完整构建耗时约 2 小时 10 分钟。

`build.sh` 每次会覆盖 build-start/build-finish 时间文件；目前其中记录的是 PLL 增量构建时间。`install.sh` 是首次安装入口，会拒绝已存在的安装目录。后续更新须按实际产物准备更新流程；`update-pll-esp.py` 检查 ESP 与 before-pll 备份一致，因此也不是可重复覆盖的通用安装器。

## 本次启动验证

- Boot ID：`f86b4421-fdf2-4c43-9bb1-3549b36a33a4`。
- `uname -r`：`7.3.0-right1-gaokun3-el2`；bootctl 标记 `gaokun-right1.conf` 为 selected。
- 命令行 initrd 路径：`\gaokun-right1\initramfs.img`，根分区 UUID 为 `194b449e-9dcd-42d9-80b2-a3a39b424a16`。
- 日志：`Initialized msm 1.13.0`，`fb0: msmdrmfb frame buffer device`。
- ESP 所有安装文件与安装报告 SHA-256 一致，磁盘 MSM 模块哈希一致。
- 安装阶段已检查 EFI 格式、EL2 DTB 属性、initramfs 显示/触屏/QRTR/固件内容、模块 vermagic、源码及配置哈希。

关键 SHA-256：

```text
initramfs.img  72d7b1c62caa942695c7f4c24290239a626f3363f5e5c62ae9488b9a0a569181
msm.ko        a04517c85a258f84dbf278fad39dd2f678a761eb8c69278063092f487b08bd7e
```

用户目前确认的是设备已启动。屏幕白线是否完全消失、亮度调整及挂起恢复后的显示稳定性，尚未有逐项实测反馈。音频、摄像头、USB、无线等功能本轮尚未完成回归测试。

## 后续接手

以当前版本作为 right 基线加必要 PLL 修复的验证点，记录显示反馈；其他问题按实际症状定位，再逐项加入补丁并记录前后结果。重建显示模块后必须同步更新 initramfs，保存可区分同版本产物的哈希。

工作区另有以下既存未跟踪文件，属于此前音频诊断工作：`tests/test_adsp_boot_retry.py`、`tools/audio/adsp-boot-retry.py`、`tools/audio/gaokun-adsp-boot-retry.service`、`tools/audio/gaokun-adsp-boot-retry.timer`。
