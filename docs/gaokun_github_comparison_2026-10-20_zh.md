# Gaokun3 Linux 社区实现与本仓库比较

核对日期：2026-10-20。本仓库基准为 `95845f7`，内核目标 v7.2.9；本机为 Fedora 44 / Gaokun3，运行 `7.2.9-gaokun3-el2+`。比较依据包括 GitHub 固定提交的源码、补丁应用脚本、构建配置和项目验证记录。下文“已覆盖”指本仓库已有对应行为；“上游”专指 Linux upstream，社区下游合入另行标明。

本仓库的主要优势是 **EL2、Iris 解码及 Fedora 安装/升级集成**；最值得借鉴的是 **gaokun3/linux 的小型正确性修复，以及 vahiru 的触控、手写笔、传感器和休眠工作**。各项目擅长的部分不同，适合按功能移植。

## 1. 仓库定位与版本

| 项目与核对提交 | 实现路线 | 与本仓库的主要区别 |
| --- | --- | --- |
| [right-0903/linux-gaokun](https://github.com/right-0903/linux-gaokun/tree/7463df37160bdecc3f2609d72f9a69cfa2b390e4) `7463df3` | 硬件研究、补丁集、DKMS、Arch/AUR；含 recommended、EL2、实验性频率调节 | 本仓库已吸收大量基础补丁；force-GSI 实现、DDR/LLCC 带宽调节和校准研究仍值得跟进 |
| [gaokun3/linux](https://github.com/gaokun3/linux/tree/73033564068250603f5b2150c408554faaf22d66) `7303356`；[gaokun3/build](https://github.com/gaokun3/build/tree/18b5b5d1c107c7f455a11165c141e247c8cd8dec) `18b5b5d` | 完整 downstream 内核树 + 独立构建仓库；build 当前 `next` 分支固定该内核 SHA，Makefile 为 7.2.7 | 与本仓库有共同 buildbot 历史；触屏传输/跳点修复更完整；迁移配置暂未提供 EL2；构建和镜像仍标为迁移候选 |
| [vahiru/gaokun-android](https://github.com/vahiru/gaokun-android/tree/85522669f355a1b6e9dfcded3f5dee3142aa0d04) `8552266` | 内核补丁 + Android HAL、服务、设备配置 | 新功能覆盖最广：手写笔、SLPI 传感器、更多触摸/相机/电源管理修复；Fedora 移植需要拆出通用部分 |
| [chiyuki0325/EGoTouchRev-Linux](https://github.com/chiyuki0325/EGoTouchRev-Linux/tree/475a6db2b58be377f446a56ff9cfd1ea1280d11c) `475a6db` | Himax SPI 触摸驱动、算法与调参 GUI | 本仓库 `hx-algo.c`、`hx-algo.h` 与该版字节一致；本地增加 GPIO174 模式控制、GTK4 工具改进 |
| [whitelewi1-ctrl/matebook-e-go-linux](https://github.com/whitelewi1-ctrl/matebook-e-go-linux/tree/9d2a0a50af22ae2f7b718524b1932d61387971ad) `9d2a0a5` | BIOS/ACPI 调查、少量显示/蓝牙/EC 补丁、用户空间工具 | 其五个 kernel-patches 的功能在本仓库或当前基线已有对应覆盖；BIOS 2.16/2.17、Wi-Fi 校准调查仍有参考价值 |
| [PeronGH/fedora-gaokun](https://github.com/PeronGH/fedora-gaokun/tree/2ecfae284dd52ce2a199fa2374bc8f333498a73e) `2ecfae2` | 改造 Fedora 官方 Rawhide Live ISO | 单一 GPT FAT32 ESP、直接 GRUB、保留 squashfs；屏蔽 `msm` 使用固件 framebuffer，适合参考救援/安装介质制作 |
| [aoripus/easy-for-gaokun](https://github.com/aoripus/easy-for-gaokun/tree/93e7b94782a809966d5ee8daab5137ec3f1af48b) `93e7b94` | Ubuntu 26.04 / GNOME 50 的平板体验整合，针对 2022 性能版 3 GHz 型号 | 选择 EL1 Venus，另有触控调参、UCM、Waydroid/OOBE；型号、频率和音频策略需与 Gaokun3 2023 分开评估 |
| [pelikanade/nixos-gaokun](https://github.com/pelikanade/nixos-gaokun/tree/3301b4b4362fb397c4c05e91b708cb1e56ad1e78) `3301b4b` | NixOS 声明式模块和 raw EFI 镜像 | 固定 6.16-rc6 / jhovold 源码，使用 `nomodeset`；主要价值是可复现配置组织方式 |

另核对了 [TheUnknownThing/linux-gaokun](https://github.com/TheUnknownThing/linux-gaokun/tree/48d86fdc25c407003bde8ca6924a9bede3c06b24)（较早 EC/UCSI/频率调节来源）、[quyansiyuanwang/gaokun-device-fixes](https://github.com/quyansiyuanwang/gaokun-device-fixes/tree/e03e64d68a3cd660e291d2ae1addaaceed02ec0c)（Mesa 环境变量与触屏 sysfs 调整）、[mdlvnn/gaokun3-msm-dsi-fix](https://github.com/mdlvnn/gaokun3-msm-dsi-fix/tree/4c2dd1df8ddde20c4649762df2034d31a2853076)（与本地 `others/0007` 相同方向的 bonded PLL 回退）。这些项目提供历史或专项参考。

归档的 [KawaiiHachimi/linux-gaokun-buildbot](https://github.com/KawaiiHachimi/linux-gaokun-buildbot/tree/315528c028843794ccd0f3d9dab373b03033150f) `315528c` 是本地 HEAD 的祖先，本地增加了 41 个提交。其主页指向 `gaokun3/build`，因此比较时应同时看后继双仓库。

## 2. 直接后继项目：维护结构和发行策略

| 维度 | 本仓库 | gaokun3/linux + build |
| --- | --- | --- |
| 内核源码组织 | stable + patch tree，同时维护 drivers/DTS/config 镜像 | 驱动、DTS、defconfig 在完整内核树；build.env 固定 SHA |
| 基线 | 7.2.9 | 实际 build.env 固定 7.2.7 的 `7303356` |
| EL2 | 独立 EL2 包、EFI 引导、remoteproc attach、Iris 固件/IOMMU 路径；本地文档记录 H.264/HEVC/VP9/Firefox 验证 | `KERNEL_EL2_COMMIT` 为空，显式请求会提前失败 |
| Fedora 集成 | Fedora 配置基线、独立 `gaokun3-platform` RPM、Anaconda 流程、dracut/kernel-install 升级挂钩 | 共享 defconfig、RPM/DEB 和 raw image CI；普通 ext4 根分区、首次启动账户配置 |
| BLS | 默认 machine-id token | 使用 fedora/ubuntu 的 os-id token |
| 音频策略 | DSP 数字增益约 +10.57 dB，保留现有 codec/PA 限制 | unity 数字增益，PA 默认 +18 dB，配合 UCM/WirePlumber 软件音量 |

后继仓库的 [migration.md](https://github.com/gaokun3/build/blob/18b5b5d1c107c7f455a11165c141e247c8cd8dec/docs/migration.md) 和 [kernel-audit.md](https://github.com/gaokun3/build/blob/18b5b5d1c107c7f455a11165c141e247c8cd8dec/docs/kernel-audit.md) 记录了多轮候选 SHA、包/镜像 CI 及部分用户反馈；表中版本以当前 `build.env` 为准。文档引用的旧候选 CI 不能直接作为当前固定 SHA 的全部硬件验收记录。双仓库方案适合减少补丁与源码镜像同步成本；迁移需要携带本仓库已有的 EL2 和 Fedora 行为。

## 3. 建议移植顺序：按收益与依赖排序

| 优先级 | 来源与改动 | 本仓库核对结果 | Fedora 集成要点 |
| --- | --- | --- | --- |
| P0 | gaokun3 内核审计中的 EC GPIO probe 错误返回修复 | `drivers/gaokun-ec/huawei-gaokun-ec.c` 获取 GPIO 失败后调用 `dev_err_probe()`，漏了 `return`，会吞掉 `-EPROBE_DEFER` 等错误 | 修正返回路径，并同步驱动镜像与补丁 |
| P0 | vahiru `0040`，gaokun3/linux 已合入：SPI 重试、完整事件栈读取 | 本地共享 TX/RX 缓冲区只在重试前初始化一次命令；最大传输长度未含 3 字节头，5132 字节栈实际拆成 5129+3 | 每次尝试重建命令，为头预留长度；验证失败重试和完整栈传输 |
| P0 | vahiru `0038`，gaokun3/linux 已合入：预测位置跳点判定 | 本地按实际位移判跳点；默认阈值 0，但 GUI gaming 预设启用 6400 | 使用预测误差；验证快速连续滑动及真正跳点 |
| P1 | right recommended `0025`：force-GSI | 本地 DTS 声明 `qcom,force-gsi-mode`，当前补丁树没有对应 SPI GENI 属性处理 | 对照目标 stable 驱动补入，再验证触控 SPI 路径 |
| P1 | vahiru `0072`：电池状态位解码和读取错误处理 | 本地忽略读取返回值，失败可能解码未初始化字节；按整字节匹配也漏掉组合状态 | 先移植通用正确性修复；CAPACITY_LEVEL 阈值另按 Fedora/UPower 策略评估 |
| P1 | vahiru `0073`：启动时报告合盖状态 | 本地主要通过事件和 resume 更新 lid，缺少启动时读取 | 与 GNOME 合盖策略及开盖恢复一起验证 |
| P1 | vahiru `0092`：重发丢失的 GET_CONNECTOR_STATUS | 本地仍用 `ucsi_sync_control_common`；已有初始化重试解决的是另一阶段 | 移植到本地 UCSI 同步/通知机制，验证双端口和 DP 插拔 |
| P1 | vahiru `0094/0095`：EC suspend IRQ 与 wake-source | 本地 suspend 中 IRQ handler 直接返回，未屏蔽对应电平 IRQ；已有 `others/0017` 电源时序 | 与 enable GPIO、唤醒源设置合并审查，覆盖休眠中断及恢复 |
| P2 | vahiru `0041–0044`、`0081/0082`：zone/peak 保留、掌触、坐标分辨率 | 本地 zone 满时中止扫描，缺少相应改进与轴分辨率 | 分离算法、诊断接口和参数；多指、掌触、libinput 一起验证 |
| P2 | vahiru SLPI/SSC 传感器栈 | 本机 SLPI attached；仓库缺少完整 libssc/hexagonrpcd/registry 部署与桌面桥接 | 加速度计/陀螺仪是自动旋转候选；需接 iio-sensor-proxy 或等效桌面接口 |
| P2 | vahiru `0079/0080` + gk3pend：M-Pencil | 本仓库缺少该输入路径 | 内核 SPI20/GPIO39 取坐标，USB 12d1:10b8 取压力/按键等，守护进程合并为 uinput；配套 systemd/udev |
| P2 | vahiru 相机 `0035/0036`、libcamera sensor helpers | 本地已有 OV13B10 和时钟停泊；仍缺传感器部分失败回退、实际 PMIC 闪光灯路径等 | 增加 HI846/OV13B10 helper；验证曝光、对焦、闪光灯及前后摄切换 |
| P2 | vahiru `0009/0071/0086`：CPU cooling、低地址 CMA、L9D 共享电源 | 本地已有 skin 55/58°C 对 CPU4–7 的 cooling；无相同逐 CPU passive maps/CMA alloc-ranges；L9D 生命周期实现不同 | 分别审查温控、DMA 寻址和共享供电，不合并成一个笼统电源补丁 |
| P2 | vahiru `0097–0102`：ath11k crash/suspend 恢复 | 本地未见对应系列 | 按当前 kernel/firmware 核查竞态；Android 快速再次休眠的 10 秒 wake hold 单独评估 |
| P3 | right freq_scaling、校准研究；aoripus 平板体验 | 提供 DDR/LLCC ICC 带宽调节、逐机 Wi-Fi/颜色校准及桌面体验方向 | 先建立频率/功耗/带宽测量，再决定默认配置 |

P0/P1 是下一轮补丁整理的优先候选；P2 是需要跨内核与用户空间验收的功能工作。这里的“缺少”来自源码对照，并不等同于本机已触发该故障。

## 4. 已有覆盖与实现冲突

本地 [README](../README.md) 已标出主要来源，以下差异决定哪些内容应保留或只取增量：

| 功能 | 比较结论 |
| --- | --- |
| 摄像头基础 | vahiru `0031/0032/0034` 对应 OV13B10 变体、匹配/电源/时钟工作已由本地 `others/0009/0010` 和 DTS 吸收 |
| USB-C / DP | vahiru `0088–0091` 的端口数、HPD 断开、EC 通知不阻塞、DP 前设置方向，本地已有对应处理；本地还包含初始化恢复和 sideband 同步 |
| 触屏 GPIO174 | 本地 mode-gpios 由驱动在 reset 周期主动控制；gaokun3/linux 对应版本主要使用 pinctrl output-low。移植算法时保留本地模式选择流程 |
| Iris 解码 | 本地 `media/0004` 有 EL2 restart、timestamp/EOS 修复；vahiru 另有断电 IRQ、防非法 uc_region、实例锁、seek/flush 等工作，应逐项与本地生命周期比较 |
| 显示 | 本地包含 DSC 60/120 Hz、DPU plane mask 修复和 bonded PLL 回退；社区各条 DSC 宽度/PLL 路线存在行为差异，不能按补丁日期直接替换 |
| 音频 | 本地 DSP、后继 PA、aoripus UCM、Android Histen/HAL 是不同增益链；应选定整条链并测量，不能叠加各项目的增益值 |

vahiru 当前应用脚本明确选择 patch 列表；一些调试补丁、旧方案已停用。例如 Iris `0055/0057/0058` 已移出当前启用路线。Android 专属 ashmem、KernelSU、用户空间 VA 限制、SELinux/HAL 策略，以及 fuzz=0、USB role 用户空间策略，不属于 Fedora 的直接导入清单。

## 5. 新功能证据应如何理解

- **手写笔**：[当前 stylus 文档](https://github.com/vahiru/gaokun-android/blob/85522669f355a1b6e9dfcded3f5dee3142aa0d04/docs/stylus.md) 描述第二代 CD54 支持、CD52 不支持、第三代未测试，并提供内核和守护进程实现。根 README 的旧 alpha 状态已落后于源码。
- **自动旋转**：[SLPI 部署文档](https://github.com/vahiru/gaokun-android/blob/85522669f355a1b6e9dfcded3f5dee3142aa0d04/docs/contrib/slpi-sensors-deploy.md) 与 SSC 协议记录给出 FastRPC → hexagonrpcd → registry → SSC/QMI → libssc 路径及传感器数据。Android HAL 已做加速度/陀螺仪集成；光线传感器路径因 DSP 问题关闭。DTS 中没有普通 IIO 传感器节点不能推出硬件不支持旋转。
- **EL2 解码**：aoripus 选择 EL1 Venus，并在文档中对 EL2/Iris 作出较强否定；本仓库 [视频验证记录](video-decoding.md) 已有 EL2 Iris 实测，应按具体内核、驱动和固件加载路径判断。
- **版本**：vahiru 的 [v1.0.0-rc.1 记录](https://github.com/vahiru/gaokun-android/blob/85522669f355a1b6e9dfcded3f5dee3142aa0d04/docs/relnotes/v1.0.0-rc.1.md) 基于 7.2.9；本次固定源码还含后续开发。上述功能表反映核对提交，发布包覆盖范围以对应 release 的提交为准。

## 6. 与 upstream 清理工作的关系

社区新增补丁、下游已合入、Linux upstream 已修复是三种状态。本报告确定跨仓库的增量；现有 58 个 patch 的 upstream 取舍见 [Fedora patch audit](fedora_patch_audit_2026-10-20_zh.md)。下一轮宜先合入表中 P0 正确性修复，再处理 P1 的协议和休眠行为，随后为传感器、手写笔建立独立 Fedora 包和验收流程。

本次完成只读源码/配置/历史比较并新增本文档，未修改驱动、补丁、运行内核或系统服务。
