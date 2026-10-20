# Gaokun Fedora 内核补丁审计（2026-10-20）

当前 Fedora 44 / Linux 7.2.9 构建仍需要这棵树的大部分硬件补丁。现存 58 个补丁中，没有确认可仅因 **7.2.9 已完整覆盖**而直接删除的项目。可先精简 5 个与本机功能无直接关系的补丁；升级到本次核对的最新主线后，可用正式背光实现和新版 Iris 接口替换对应下游实现。

## 基线与核对方法

| 对象 | 本次核对结果 |
| --- | --- |
| 本机 | Matebook E Go，`huawei,gaokun3` / SC8280XP，Fedora 44 aarch64 |
| 正在运行 | `7.2.9-gaokun3-el2+`，RPM 查询显示普通 EL2 包为 release 13 |
| 启动状态 | 所有 CPU 从 EL2 启动，VHE 初始化成功；ADSP、CDSP、SLPI 当前均为 `attached` |
| 摄像头 | 本次启动日志识别 HI846 `08 46`、OV13B10 `0x560d42` |
| 显示连接 | 本次检查 DSI 已连接，两路 DP 未连接 |
| 本仓库 | `95845f7`，打包修订已到 16；本机运行状态只能直接代表已加载版本 |
| 当前构建源 | [gregkh/linux v7.2.9](https://github.com/gregkh/linux/tree/5fce161649b4d779d1b76d9fcd52dc77779774b8)，提交 `5fce161649b4` |
| 最新主线快照 | [torvalds/linux](https://github.com/torvalds/linux/tree/f47d223627f80cb7a1eb14c585fe6cb35de5e984)，提交 `f47d223627f8`，2026-10-20；Makefile 为 7.3.0，正在接收 7.4 合并窗口内容 |
| 参考补丁树 | [right-0903/linux-gaokun](https://github.com/right-0903/linux-gaokun/tree/7463df37160bdecc3f2609d72f9a69cfa2b390e4)、[TravMurav/linux 指定 EL2 分支](https://github.com/TravMurav/linux/tree/x13s-6.18-v1.1-cxsd) |

构建脚本从 upstream stable 源码开始，合并 Fedora 配置并制作专用 RPM。因此这里的“Fedora build”以本项目使用的 stable 源码为准。`patches/upstream/` 表示来源分组，其中包含尚未合入主线的改动。

核对包含：读取全部补丁、下载固定提交中涉及的源码、检查正向和反向应用、核对相关函数语义、查询上游文件提交历史。补丁应用失败需要结合源码判断；背光补丁即使仍能正向应用，也可能已被另一种上游实现覆盖。

## 当前 7.2.9 构建的保留项

下表编号均相对于 `patches/`。标为“保留”的改动在 7.2.9 中仍有作用；最新主线存在替代方案的项目另在后文说明。

### 显示、输入、USB 与电源

| 补丁 | 判断 | 对 Gaokun Fedora 的作用与依赖 |
| --- | --- | --- |
| `upstream/0005` | 保留 | 添加 MDSS `cpu-cfg` interconnect 投票；7.2.9 与本次主线快照均缺少该路径。 |
| `upstream/0014` | 保留 | 视频已运行时避免亮度 DCS 命令额外开关 link clocks / OPP，处理双 DSI 闪烁。 |
| `others/0005` | 保留 | DSC 压缩后的 timing width 按字节数向上取整。上游 DPU timing 仍使用会截断的计算。 |
| `others/0007` | 保留 | 恢复 bonded DSI PLL 初始化修复，解决本项目记录的白线/黑屏；原始修复随后被上游撤销。 |
| `others/0006` | 7.2.9 保留；升级后替换 | 驱动对 DTS `bl-supply` 的消费；最新主线已有更完整的背光电源管理。 |
| `others/0011`、`others/0013` | 成对保留 | 前者固定 Gaokun primary plane / CRTC 对应关系，后者让公共 allocator 真正使用 `possible_crtcs`。用于 GDM/桌面与外屏切换；仅有 0011 时 mask 会被硬编码 `0xff` 覆盖。 |
| `others/0003` | 保留 | HX83121A SPI 触屏驱动及触点算法，配合 DTS GPIO174 模式选择、GPIO99 reset、GPIO175 IRQ 和 panel follower。主线 panel 驱动只覆盖显示部分。 |
| `upstream/0018` | 保留 | 移除 GPIO175→PDC237 的触屏唤醒映射，处理 EC 唤醒引入后的触屏冻结/迟滞。上游仍有该映射。 |
| `others/0004` | 保留 | UCSI 异步初始化恢复、sideband ACK、固定端口拓扑及 DP/HPD 状态同步；基础 mode switching 虽已上游化，这些增量仍存在。 |
| `others/0014` | 保留 | 在生成 ACK bit mask 前检查 `-1` 哨兵和端口范围，修复负移位 UBSAN。最新主线仍保留先计算再处理哨兵的代码。 |
| `others/0015` | 保留 | QMP combo PHY 失败清理归还正确资源，避免 PIPE clock 重复 disable、错误减少引用计数。 |
| `others/0016` | 保留 | Gaokun Type-C 重配置保留公共时钟/电源投票；仓库记录了 USB2/USB3 hub 和接收器枚举的对照验证。依赖 0015 的资源生命周期修复。 |
| `upstream/0012` | 保留 | EC PM 回调从 noirq 阶段移到普通 system sleep 阶段，使 I²C 交互仍能执行。 |
| `upstream/0015` | 保留 | 电池 `_STA` 与 EC 0xA3 事件处理。 |
| `upstream/0016`、`others/0017` | 成组保留 | EC enable/reset GPIO，以及用 EC IRQ 管理 wakeup source。对应 DTS、休眠和合盖行为，应联合维护。 |
| `others/0001` | 按现有蓝牙方案保留 | 当前方案先修补 NVM BDADDR；此补丁避免有效地址仍触发 `USE_BDADDR_PROPERTY`、导致未配置状态。若改用有效的 DT `local-bd-address`，可重新评估该策略补丁。 |

### 音频、摄像头与视频

| 补丁 | 判断 | 对 Gaokun Fedora 的作用与依赖 |
| --- | --- | --- |
| `upstream/0002` | 保留 | 为 ADSP FastRPC 增加 remote heap 保留内存和 VMID。上游已有 FastRPC 节点，但这部分内存布局仍缺少。 |
| `upstream/0020` | 保留 | HI846 写寄存器成功时清理正数 `ret`，避免 PM runtime 返回值被当作控制操作错误。 |
| `upstream/0021` | 保留 | HI846 按 PLL、时钟和 lane 数计算 link frequency。 |
| `upstream/0022` | 完整摄像头构建保留 | 增加前摄 6MP / 8MP 模式。 |
| `upstream/0023` | 随 HI846 系列保留 | 根据 2/4 lane 选择合法模式表，避免选到当前 lane 配置不支持的模式；依赖前面的模式改动。 |
| `others/0009` | 保留 | 本机 OV13B10 的 OF 匹配、共享 L2B 供电和 Gaokun 电源顺序；本机已确认安装该传感器。 |
| `others/0010` | 保留 | CAMNOC / AHB 时钟停用时停靠 XO，处理再次打开摄像头的 TITAN_TOP 超时。 |
| `media/0001–0003` | 7.2.9 成组保留；升级后迁移 | 本地 binding、SC8280XP codec DT 资源、Iris VPU2 平台匹配，提供当前使用的 `qcom,sc8280xp-venus` 路径。 |
| `media/0004` | 保留，升级时拆分移植 | 混合了 Gaokun EL2 固件 IOMMU/direct boot，以及 timestamp ring、VP9 EOS、IRQ teardown、scratch buffer/restart 修复。已有硬解、重复播放和 Firefox 导入的仓库验证记录。 |
| `0099` 的板级 DTS / camera dtsi | 保留 | 把上述驱动连接到实际硬件，包括触屏、背光、EC、双摄、音频和 OEM 视频固件。上游已有基础 Gaokun DTS，仍未覆盖本地完整配置。 |

音频与视频的历史实机验证见 [ADSP 诊断](adsp-boot-diagnostics.md)、[摄像头](camera_support.md)、[视频解码](video-decoding.md)；USB 验证见 [USB hub 诊断](usb-hub-diagnostics.md)。本次审计读取现有运行状态并验证源码，没有重启执行新的硬件 A/B 测试。

### 本机 EL2 路径

| 补丁 | 判断 | 剩余作用 |
| --- | --- | --- |
| `el2/0001–0005` | 保留 | SMP2P kick 时序、边界和字符串检查、复用 boot firmware SMEM 状态。7.2.9 与所查主线都还缺少这些改动。 |
| `el2/0006` | 保留并随核心 API 演进维护 | 扩展 auto-boot 策略，在固件可用时重启 detached remoteproc。上游 async attach 不覆盖该策略。 |
| `el2/0007–0010` | 成组保留 | 从 SMP2P 检测已运行 DSP、attach helper、正确 stop 信号以及 PAS attach/restart 决策。上游已有 `qcom_pas_attach()`，本地补丁是对它的增量修改。 |
| `el2/0011–0012`、`el2/0014` | 保留 | SHM bridge VMID binding、SELF_OWNER 处理及 SC8280XP overlay；服务于 EL2 下 SCM/TZMEM。 |
| `el2/0016`、`el2/0018` | 保留 | 对 SC8280XP 标记并处理 `qcom,broken-reset`，在 OEM hypervisor 不运行时使用预先启动的 DSP。 |
| `el2/0020–0022` | 成组保留 | rpmsg announce 生命周期、手工 endpoint 创建与 QRTR 收发回调竞争修复；最新主线相关旧行为仍存在。 |
| `el2/0023–0024` | 保留功能部分 | 前者传播 attach/IRQ 错误并记录状态；后者在映射不可用时执行最多 100ms 的有界等待。0024 依赖 0023 的函数结构，0023 中的日志可另行拆为 debug 选项。 |

这些 EL2 补丁为 remoteproc / SCM 等子系统补充启动支持；KVM/VHE 本身由上游内核提供，固件启动链还使用项目的 EFI payload。

## 可以精简或移为选项的项目

| 优先级 | 项目 | 处理建议 |
| --- | --- | --- |
| 1 | `el2/0013`、`el2/0015`、`el2/0017` | Gaokun 专用构建可删除：只改 SC7180 / X1 overlay。保留 SC8280XP 的 0014、0018。 |
| 1 | `el2/0019` | Gaokun 专用构建可删除：修改 PMIC GLINK 平台/rpmsg 注册时序；本机 live DT 没有 `qcom,pmic-glink`，Type-C/电池由 Huawei EC 驱动处理。若扩展支持其他机型，再按其 DT 纳入。 |
| 1 | `upstream/0019` | 可删除：调整 DSI1 PHY 节点顺序以消除 harmless deferred-probe 日志。 |
| 2 | `others/0008` | 移入 QSEE fTPM 实验 profile；目前是显式 `allow_probe=1` 的验证驱动。删除时同步调整 `CONFIG_TCG_QCOM_TPM_QSEE`、相关配置检查和测试。 |
| 2 | `others/0012` | 移为声音调校选项：为 Gaokun speaker graph 增加约 +10.57dB DSP 增益。标准音频工作不以此为前提。 |
| 2 | `others/0002` | 可改用模块参数配置：它只把已有 `enable_dsc` 默认值改为 true。保留 DSC 体验时，改为设置 `panel_himax_hx83121a.enable_dsc=1` 并确保 initramfs/模块加载路径带入。 |
| 2 | `0099` 的 CPU 产品名与 `gaokun3_defconfig` | 可拆出：CPU 字符串是展示定制；当前 CI 用 Fedora baseline + fragments，不调用 `make gaokun3_defconfig`。板级 DTS 仍需保留。 |
| 3 | `el2/0023` 日志部分 | 可独立 debug 化；保留错误传播和 0024 所需函数结构。 |

在临时源码树中跳过前 5 个补丁（3 个其他 SoC overlay、PMIC GLINK、DSI 排序），其余 **53 个补丁按构建顺序全部应用成功**。这是源码依赖检查，尚未形成新的构建/启动验收结果。

## 已由 upstream 覆盖的历史补丁与基础功能

下列项目大多已被本仓库删除，或者在目前补丁中仅保留额外增量。不要从旧 patch tree 重复导入。

| 历史补丁/功能 | 7.2.9 源码证据 | 处理 |
| --- | --- | --- |
| ADSP FastRPC 节点（旧 `upstream/0001`） | [1825ac5e2ad2](https://github.com/torvalds/linux/commit/1825ac5e2ad2)，原补丁可在 7.2.9 反向应用 | 已覆盖；当前 `upstream/0002` 的 heap/VMID 增量继续保留。 |
| SC8280XP DSI 节点（旧 `0004`） | `mdss0_dsi0/1` 与 PHY、clock、graph 节点存在；参考树旧补丁反向检查通过 | 已覆盖。 |
| HX83121A panel 基础驱动（旧 `0007`） | [a7c61963b727](https://github.com/torvalds/linux/commit/a7c61963b727)，已含面板和 DSC 模式 | 已覆盖；SPI 触屏和默认 DSC 策略分别评估。 |
| DISPCC MDP 初始化不 park（旧 `0008`） | `clk_rcg2_shared_no_init_park_ops`；旧补丁反向检查通过 | 已覆盖。 |
| DISPCC 相关 `CLK_SET_RATE_PARENT` 移除（旧 `0009`） | 对应四处旧补丁反向检查通过 | 已覆盖。 |
| bonded DSI pclk 取整（旧 `00013`） | 分割每条 link 的 hdisplay 后分别取整；旧补丁反向检查通过 | 已覆盖。 |
| DPU widebus DSC data window（旧 `0011`） | `dpu_hw_intf.c` 压缩路径直接用 `DIV_ROUND_UP(dce_bytes_per_line, 6/3)` | 已由新的字节数算法覆盖；`others/0005` 修复的是另一处 timing width。 |
| PDC range 扩展（旧 `0017`） | [96f65d01f313](https://github.com/torvalds/linux/commit/96f65d01f313)，`<214 643 2>`、`<255 454 3>`；反向检查通过 | 已覆盖，本仓库 `8e73fc5` 已删除；GPIO175 workaround 独立保留。 |
| SMP2P `irq_get_irqchip_state`（参考树 EL2 `0006`） | [8a9a7b9d14c2](https://github.com/torvalds/linux/commit/8a9a7b9d14c2)，当前函数在无映射时返回 `-ENODEV` | 已覆盖；旧版本无映射返回成功且 level=0 的行为已被替代。 |
| PAS attach 与 remoteproc 异步 attach 基础 | `qcom_pas_attach()`、`.attach`、`schedule_work(&rproc->attach_work)` 均存在 | 基础已有；EL2 剩余策略/状态机改动保留。 |
| Huawei UCSI mode switching（参考树旧 `0024`） | `TYPEC_DP_STATE_*`、`typec_mux_set`、mux 获取/释放均存在 | 基础已有；本地初始化重试和状态同步继续保留。 |
| Iris VPU preset `0xb0088` | `iris_vpu_set_preset_registers()` 已写该寄存器 | 无需重复引入旧系列的额外 preset callback。 |

重要例外：PLL 修复 [93c97bc8d85d](https://github.com/torvalds/linux/commit/93c97bc8d85d) 曾经合入，但主线以 [44784327815b](https://github.com/torvalds/linux/commit/44784327815b) 撤销；7.2.9 对应 stable revert 为 `5de981b7db1f`。所以 `others/0007` 仍有必要，其作用范围应保持在本项目已验证的双 DSI 设备。

## 升级到最新主线时可替换的现存补丁

### `others/0006`：用正式背光 regulator 实现替换

主线 [98b46e693b91](https://github.com/torvalds/linux/commit/98b46e693b91) 已通过 `devm_regulator_get_optional(dev, "bl")` 获取背光电源，并随亮度/背光电源状态控制 regulator。7.2.9 尚无此实现。

升级后保留 `bl-supply` DTS，删除本地向 panel bulk supplies 加入 `bl` 的补丁。继续叠加会额外保留一份 panel 电源引用，妨碍上游按背光状态关闭该电源。验收亮度 0、恢复亮度、灭屏与 suspend/resume。

### `media/0001–0003`：迁移到上游 Iris ABI

主线 [3a52eef16b97](https://github.com/torvalds/linux/commit/3a52eef16b97) 已增加 SC8280XP Iris DT。新版 [binding](https://github.com/torvalds/linux/blob/f47d223627f80cb7a1eb14c585fe6cb35de5e984/Documentation/devicetree/bindings/media/qcom,sm8250-venus.yaml) 和 [Iris 驱动](https://github.com/torvalds/linux/blob/f47d223627f80cb7a1eb14c585fe6cb35de5e984/drivers/media/platform/qcom/iris/iris_probe.c) 使用兼容回退到 SM8250 的方案。

| 接口 | 当前本地补丁 | 所查主线 |
| --- | --- | --- |
| DT label | `venus` | `iris` |
| compatible | `qcom,sc8280xp-venus` | `qcom,sc8280xp-iris`, `qcom,sm8250-venus` |
| Driver data | 独立 `sc8280xp_data` | 回退匹配 `sm8250_data`，4 VPP pipes |
| reset names | `core` | `bus`, `core` |
| power-domain names | `venus`, `vcodec0`, `mx` | 另含 `mmcx` |
| IOMMU specifier | `0x2e00` | `0x2a00 0x400` |

因此升级时可替换这三个补丁负责的 Gaokun/SC8280XP 基础接入，但须同步修改 `0099` 的 `&venus` 引用、OEM `firmware-name` 和 `media/0004` 对板型/compatible 的判断。EL2 direct boot、独立 firmware domain 和 decoder restart 改动仍需逐项移植。上游 DT 的基础接入不能作为本机 EL2 硬解已通过验证的证据。

## 参考树中值得补齐的一项

[GENI SPI force-GSI 补丁](https://github.com/right-0903/linux-gaokun/blob/7463df37160bdecc3f2609d72f9a69cfa2b390e4/patch%20sets/recommended/0025-spi-qcom-geni-Add-property-to-force-GSI-mode.patch) 仍未由所查 7.2.9 或主线驱动实现，也未包含在本仓库补丁链中。

本地 DTS `&spi6` 已设置 `qcom,force-gsi-mode`，而 `spi-geni-qcom.c` 只读取硬件 `GENI_IF_DISABLE_RO` 选择 FIFO/GPI。当前属性不会强制改变模式；硬件本身仍可能选择 GPI。该补丁可作为触屏传输性能候选，检查 DMA channel、实际模式和延迟后再纳入。已经正常注册的触屏设备说明它不是当前触屏 probe 的必要条件。

## 已完成的检查与构建建议

- 从固定 upstream 提交下载 patch target 文件，核对了全部 58 个现存补丁和参考树的历史补丁。
- 使用新下载的 7.2.9 文件运行 `GAOKUN_KERNEL_SRC=... python3 -B tests/test_kernel_patches.py -v`，8 项全部通过：标准/EL2 完整链、DTS/driver 镜像一致性、PLL、plane mask、EC ACK、QMP 资源生命周期、Iris 资源和 remoteproc stop 状态。
- 在临时树验证了删除上述 5 个精简项后剩余 53 个补丁的应用顺序。
- 检查了本机包版本、启动日志、remoteproc 状态、摄像头 ID 和 live DT。

建议先继续使用 **7.2.9 + 必需硬件补丁 + 本机 EL2 增量**，把可选调校/验证功能拆出；升级主线时优先采用正式背光与 Iris 接口。普通 EL1 构建不应用 `el2/*`，EL2 构建保留其余 remoteproc / SCM 支持。此次仅新增审计文档，补丁链和安装状态保持原状。
