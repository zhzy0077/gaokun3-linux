# Linux v7.3 补丁重构与代码审查

审查基准：原仓库 `95845f7`；新构建源为 [torvalds/linux v7.3](https://github.com/torvalds/linux/tree/c03c1a14507dfaf8b856c2608f9ac216021fc222)，提交 `c03c1a14507dfaf8b856c2608f9ac216021fc222`。日期：2026-10-20。

**原 58 个补丁删除 10 个，Iris 混合补丁拆为 2 个，最终在用 49 个。** 标准链 30 个，EL2 增量 19 个。删除项中 4 个由新基线的实现替代，6 个在 Gaokun 构建中没有所需功能增量。

## 审查标准

逐项检查 pristine v7.3、按顺序应用后的源码、调用者、DT compatible/属性消费者、配置和错误清理路径。patch 的说明与历史日志用于定位，不作为有效性的结论。正向/反向应用检查用于识别差异，不能替代语义比较。

证据分为：原函数与修改后函数的行为对照；源码调用链/资源所有权；编译后 DTB 与驱动匹配；硬件 workaround 的待验证假设。当前正在运行的 7.2.9 内核只能用于确认设备拓扑，不能证明新 v7.3 的硬件回归已通过。

机器可读记录为 [patches/inventory.json](../patches/inventory.json)，包含每项代码依据、证据类型、内容哈希与删除原因。`upstream/` 是沿用的目录名，实际 upstream 状态以清单为准。

## 删除项

| 原编号 | 处理 | 代码依据 |
| --- | --- | --- |
| `upstream/0019` | 删除：无功能增量 | DSI1 PHY 节点搬移；搬移块及剩余 DTS 分别逐字节一致。设备依赖仍由 deferred probe 处理。 |
| `others/0006` | 删除：上游实现替代 | v7.3 panel 已 devm_regulator_get_optional(bl) 并按背光状态 enable/disable；旧 bulk supply 会额外持有 regulator 引用。 |
| `media/0001` | 删除：上游实现替代 | 采用 upstream SC8280XP Iris binding，保留 sm8250 fallback；旧 SC8280XP/SM8350 Venus binding 不再用于本板。 |
| `media/0002` | 删除：上游实现替代 | v7.3 sc8280xp.dtsi 已有 iris 节点、clock/reset/power-domain/OPP/IOMMU 资源。 |
| `media/0003` | 删除：上游实现替代 | upstream sm8250_data 已提供 4 VPP pipe，SC8280XP 通过 compatible fallback 匹配。 |
| `el2/0006` | 删除：本机路径不可达 | Gaokun EL2 的四个 DSP 都选 no-reset ops，永不选 RESTART_IF_FW_AVAILABLE；恢复 upstream bool auto_boot 和全局 remoteproc core，去掉跨 13 文件的 enum 改造。 |
| `el2/0013` | 删除：其他 SoC | 只改 sc7180-el2.dtso，本板 overlay 不引用。 |
| `el2/0015` | 删除：其他 SoC | 只改 x1-el2.dtso，本板 overlay 不引用。 |
| `el2/0017` | 删除：其他 SoC | 只改 sc7180-el2.dtso，本板 overlay 不引用。 |
| `el2/0019` | 删除：无对应设备 | Gaokun live DT 和板级 DTS 无 qcom,pmic-glink platform 设备，Type-C/电池走 Huawei EC；无需改全局 platform/rpmsg 注册顺序。 |

## 移植中保留的新基线行为

- **Iris**：板级 `&venus` 改为 `&iris`，保留 OEM firmware-name 和独立 firmware IOMMU 子设备。direct load 先调用上游固件识别，再设置 `iris_firmware_data`，避免绕过新 HFI descriptor 初始化。
- **remoteproc**：attach 使用 v7.3 的 handover IRQ 管理 helper；PAS 调用沿用上游接口及 devm 生命周期。收窄 `el2/0010` 后保留 bool auto_boot，移除 lite-firmware shutdown/restart 分支。
- **PCIe**：保留上游把 reset/wake GPIO 放到 `pcie*_port0` 的变更。
- **QMP**：保留上游新增的 aon_toggle 选择；Gaokun force 重配置跳转放在该变量初始化之后。
- **EC/电池**：修正原 `upstream/0016`、`0015` 中漏掉的 `return dev_err_probe(...)`。错误获取 GPIO 时立即返回；可选 GPIO 不存在时继续正常探测。
- **Iris 补丁拆分**：`media/0004` 仅承载 EL2 固件启动；`media/0005` 承载通用的元数据、EOS、IRQ 和解码重启行为。

## 剩余 49 项逐项依据

类别统计：19 项硬件接入、15 项正确性修复、7 项 workaround、3 项默认策略、2 项依赖性重构、1 项 opt-in 实验功能；另有 1 项 DTS/配置/展示混合项与 1 项错误处理/诊断混合项。

“硬件接入”表示存在实际 DT/驱动消费路径；“正确性修复”表示可以从控制流、数据或测试证明行为差异。7 项 workaround 暂保留在默认链，清单记录了需要 A/B 的条件。DSC 默认值、蓝牙 NVM 策略和扬声器增益是产品策略；QSEE fTPM 默认不 probe。这些项目不归为基础启动必需修复。

| 编号 | 类别 | 代码判断 | 证据 |
| --- | --- | --- | --- |
| [upstream/0002](../patches/upstream/0002-arm64-dts-qcom-sc8280xp-Add-memory-region-for-audio-.patch) | 硬件接入 | ADSP FastRPC 的 memory-region 被驱动用于 remote heap，qcom,vmids 决定分配内存的 SCM 归属；基线缺少这两项。 | DT/consumer |
| [upstream/0005](../patches/upstream/0005-arm64-dts-qcom-sc8280xp-add-MDSS-registers-interconn.patch) | 硬件接入 | msm_mdss 获取 cpu-cfg 并在 runtime resume/suspend 投票；缺失 DT path 时对应寄存器带宽投票为空。 | DT/consumer |
| [upstream/0012](../patches/upstream/0012-platform-arm64-huawei-gaokun-ec-fix-suspend-resume.patch) | 正确性修复 | EC suspend/resume 回调执行 I2C 传输；普通 PM 阶段提供中断完成条件，noirq 阶段不适合该调用路径。 | control-flow |
| [upstream/0014](../patches/upstream/0014-drm-msm-dsi-avoid-link-clock-toggles-during-active-v.patch) | workaround | active video 已持有 link clock/OPP，DCS xfer_restore 又执行 disable/OPP 释放；绕过额外投票改变了真实时钟路径。需新基线亮度/灭屏 A/B。 | control-flow; hardware A/B pending |
| [upstream/0015](../patches/upstream/0015-power-supply-gaokun-fix-battery-_STA-handling.patch) | 硬件接入 | bat GPIO 控制 EC 初始化命令发送，A3 事件重新读取 present；本地 DTS 提供 GPIO41。此次补回 GPIO 获取失败的 return。 | DT/consumer; native GPIO failure |
| [upstream/0016](../patches/upstream/0016-platform-arm64-huawei-gaokun-ec-introduce-EC-enable-.patch) | 硬件接入 | EC enable GPIO 在 probe、suspend、resume 被实际驱动；此次补回 GPIO 获取失败的 return，避免错误指针进入后续路径。 | DT/consumer; native GPIO failure |
| [upstream/0018](../patches/upstream/0018-HACK-pinctrl-qcom-sc8280xp-do-not-map-gpio175-to-pdc.patch) | workaround | 只删除 GPIO175 到 PDC237 的映射；触屏仍经 TLMM IRQ，唤醒行为发生变化。现有资料不足以证明 v7.3 仍需此 workaround，暂保留待休眠 A/B。 | DT/consumer; hardware A/B pending |
| [upstream/0020](../patches/upstream/0020-media-hi846-fix-hi846_write_reg_16-handling.patch) | 正确性修复 | HI846 set_ctrl 把 pm_runtime_get_if_in_use 的正数传给 write_reg_16；成功 I2C 写不清零导致正数返回。原函数复现，修复函数通过。 | native before/after |
| [upstream/0021](../patches/upstream/0021-media-hi846-fix-link-frequency-handling.patch) | 正确性修复 | link_freq 由时钟/PLL/lane 参数推导并提供给接收端；原固定表不表达本机模式的实际链路频率。 | data-flow; Kbuild |
| [upstream/0022](../patches/upstream/0022-media-hi846-Add-6MP-and-8MP-modes-support.patch) | 硬件接入 | 增加 V4L2 可枚举的 6MP/8MP 模式及实际寄存器表；属于分辨率扩展，基础 probe 不依赖这些模式。 | data-flow; Kbuild |
| [upstream/0023](../patches/upstream/0023-media-hi846-fix-modes-handling-for-different-lane-ca.patch) | 正确性修复 | 按 nr_lanes 选择模式表，限制枚举/格式选择到合法 lane 配置；与 0021/0022 的表结构一起维护。 | data-flow; Kbuild |
| [others/0001](../patches/others/0001-Bluetooth-btqca-only-set-USE_BDADDR_PROPERTY-when-ad.patch) | 默认策略 | 仅在读到无效 BDADDR 时设置 USE_BDADDR_PROPERTY；配合本仓库 NVM 地址修补方案。行为可从地址判断分支确认。 | control-flow; NVM tests |
| [others/0002](../patches/others/0002-drm-panel-himax-hx83121a-enable-DSC-by-default.patch) | 默认策略 | 只把已存在 enable_dsc 参数的默认值置 true；实现和开关均在 upstream，补丁用于默认显示策略。 | one-line default; Kbuild |
| [others/0003](../patches/others/0003-Input-touchscreen-add-Himax-HX83121A-SPI-driver.patch) | 硬件接入 | 增加 SPI 驱动、事件栈读取、触点追踪和 input 上报；本地 DTS 匹配该 compatible，GPIO174 在 reset 周期驱动。 | DT/consumer; Kbuild; GPIO mode tests |
| [others/0004](../patches/others/0004-usb-typec-ucsi-recover-Gaokun-initialization-and-DP.patch) | 硬件接入 | 补齐 UCSI 初始化 work 重试、EC sideband ACK、端口及 mux/HPD 状态同步；这些调用仍不在基线驱动中。 | control-flow; UCSI regression |
| [others/0005](../patches/others/0005-drm-msm-dpu-fix-DSC-timing-width-truncation.patch) | 正确性修复 | DSC width 由 dce_bytes_per_line 向上取整；800 pixels/8bpp/8bpc 得 267，原整数公式得 266，与 DSI timing 不一致。 | arithmetic; Kbuild |
| [others/0007](../patches/others/0007-drm-msm-dsi-restore-bonded-PLL-initialization.patch) | workaround | PLL bias 引用移到 PLL 使用路径，可在 PHY enable 前编程共享 PLL。v7.3 保留上游 revert 后行为；本地原生测试覆盖两次共享使用，实际显示需 A/B。 | native resource sequence; hardware A/B pending |
| [others/0008](../patches/others/0008-firmware-qcom-add-Gaokun-QSEE-TPM-validation.patch) | opt-in 实验 | 新增 QSEE fTPM transport；默认 allow_probe=0，不承担普通 Fedora 启动功能。作为显式 opt-in 验证功能保留。 | protocol/native tests; runtime opt-in |
| [others/0009](../patches/others/0009-media-i2c-ov13b10-support-Gaokun-camera-power.patch) | 硬件接入 | OF compatible 匹配本机 OV13B10，消费共享供电并执行相应启动顺序；DTS 中传感器为 enabled。 | DT/consumer; camera tests; Kbuild |
| [others/0010](../patches/others/0010-clk-qcom-camcc-sc8280xp-park-camera-clocks.patch) | workaround | 将 CAMNOC/AHB 的时钟操作换为停泊 XO 的 shared ops；运行时会改变 disable/re-enable 的父时钟选择。再次开摄像头的收益需 v7.3 A/B。 | clock ops selection; hardware A/B pending |
| [others/0011](../patches/others/0011-drm-msm-dpu-pin-Gaokun3-primary-planes.patch) | workaround | Gaokun primary plane 的 mask=BIT(primary_idx)，限制跨 CRTC 分配；硬件适配策略，依赖 0013 才能到达 DRM 对象。 | native mask tests; GDM/external-display A/B pending |
| [others/0012](../patches/others/0012-ASoC-qcom-audioreach-calibrate-Gaokun3-speaker-gain.patch) | 默认策略 | speaker graph 1 的 Q13 gain 乘 27/8 并饱和；mute=0 保持，其他 graph 和机器不变。属于声音调校。 | native gain tests |
| [others/0013](../patches/others/0013-drm-msm-dpu-honor-plane-possible-crtcs.patch) | 正确性修复 | 公共 plane allocator 原来丢弃 possible_crtcs 并硬编码 0xff；现在把调用者 mask 传到 DRM 注册。 | call-chain; mask regression |
| [others/0014](../patches/others/0014-platform-arm64-gaokun-fix-UCSI-ACK-negative-shift.patch) | 正确性修复 | ACK 的 -1 sentinel 在移位前被检查，避免 BIT(-1)；原生测试覆盖 sentinel/边界/端口组合。 | native UBSAN boundary tests |
| [others/0015](../patches/others/0015-phy-qcom-qmp-combo-fix-error-resource-ownership.patch) | 正确性修复 | USB power_on 超时不再归还 common owner 的 PIPE clock；force init 失败不再减少未取得的 init_count。 | native fault injection |
| [others/0016](../patches/others/0016-phy-qcom-qmp-combo-preserve-Gaokun-common-power.patch) | workaround | force Type-C 重配置保留 clocks/regulator votes，普通 init/final exit 保留原生命周期；v7.3 新 aon_toggle 初始化必须在跳转前执行。 | native resource tests; current-kernel USB A/B pending |
| [others/0017](../patches/others/0017-platform-arm64-huawei-gaokun-ec-set-wakeup-source-pr.patch) | 硬件接入 | 以 EC IRQ 注册 wake source，配合 enable GPIO 和 PM 回调顺序；EC 是本机合盖/电池/Type-C 事件入口。 | DT/consumer; Kbuild |
| [media/0004](../patches/media/0004-media-iris-Gaokun-EL2-firmware-and-restart.patch) | 硬件接入 | EL2 firmware_direct=1 时创建独立 firmware IOMMU device，加载 OEM 镜像并写 VPU2 reset；普通路径使用 upstream PAS。移植保留 upstream firmware detection/HFI descriptor 初始化。 | runtime opt-in; Kbuild; new-baseline decode pending |
| [media/0005](../patches/media/0005-media-iris-fix-decoder-metadata-EOS-and-restart.patch) | 正确性修复 | metadata_idx 在 input 环回后被 output fallback 直接用作数组索引；原函数边界复现。另保留 Gen1 空 EOS、scratch 替换和 stopped-state/IRQ teardown 修复。 | native timestamp before/after; Kbuild; lifecycle hardware pending |
| [0099](../patches/0099-arm64-gaokun3-import-local-dts-and-defconfig.patch) | 接入/配置/展示 | 板级 DTS 连接上述驱动与供电/中断/端点；采用 upstream PCIe port reset GPIO 和 Iris label。standalone defconfig 为兼容入口，CPU model 字符串只作展示。 | DTB/EL2 overlay; mirror checks; CPU string tests |
| [el2/0001](../patches/el2/0001-soc-qcom-smp2p-Kick-after-requesting-interrupt.patch) | 正确性修复 | 先注册接收 IRQ 再 kick 远端，避免 DSP 立即回应时本端尚无 handler。 | call ordering; Kbuild |
| [el2/0002](../patches/el2/0002-soc-qcom-smp2p-Ensure-there-is-enough-space-for-outb.patch) | 正确性修复 | 新增 outbound entry 前检查 valid_entries==total_entries，阻止写到 entries 数组之后。 | bounds/control-flow |
| [el2/0003](../patches/el2/0003-soc-qcom-smp2p-Use-length-limited-strncmp-for-compar.patch) | 正确性修复 | 固定长度 SMEM name 未必 NUL 结尾；strncmp 上界为 SMP2P_MAX_ENTRY_NAME，避免 strcmp 越界读。 | bounds/control-flow |
| [el2/0004](../patches/el2/0004-soc-qcom-smp2p-Drop-redundant-stack-copies-of-entry-.patch) | 依赖性重构 | 将 name 改 char[] 并去掉栈拷贝；单独不增加设备能力，为 0005 的原位条目复用提供实现结构。 | dependency of el2/0005 |
| [el2/0005](../patches/el2/0005-soc-qcom-smp2p-Take-over-outgoing-SMEM-items-from-bo.patch) | 硬件接入 | 按旧 SMEM header/entry name 复用条目，保留初始 inbound 和 SSR ACK 状态；避免 attach 时重新分配 boot firmware 的 entry。 | SMEM data-flow; Kbuild |
| [el2/0007](../patches/el2/0007-remoteproc-qcom_q6v5-Allow-detecting-detached-state-.patch) | 硬件接入 | 读取 ready/handover/fatal/stop IRQ level 决定 RPROC_DETACHED；running DSP 的 attach 入口由此可达。 | native state matrix |
| [el2/0008](../patches/el2/0008-remoteproc-qcom_q6v5-Add-qcom_q6v5_attach.patch) | 硬件接入 | attach 只建立 load-state/completion/running 状态，不取得启动代理投票；使用 v7.3 handover IRQ 引用管理 helper。 | call-chain; Kbuild |
| [el2/0009](../patches/el2/0009-remoteproc-qcom_q6v5-Send-SMP2P-stop-signal-in-attac.patch) | 正确性修复 | stop 对 ATTACHED 与 RUNNING 都发送 SMP2P 停止信号；保留有效已停止状态的快捷返回。 | native stop-state tests |
| [el2/0010](../patches/el2/0010-remoteproc-qcom_q6v5_pas-Attach-running-remoteproc-i.patch) | 硬件接入 | 只保留 PAS attach helper/错误清理和初始 SMP2P 探测；已删除本机不使用的 lite shutdown 和 restart policy。 | native state tests; boolean auto_boot retained |
| [el2/0011](../patches/el2/0011-dt-bindings-firmware-qcom-scm-Add-qcom-shm-bridge-vm.patch) | 硬件接入 | 定义 SHM bridge VMID/SELF_OWNER binding 值供 0012/0014 消费；单独没有执行行为。 | dependency of el2/0012,0014 |
| [el2/0012](../patches/el2/0012-wip-firmware-qcom-tzmem-Use-self-owner-bits-when-run.patch) | 硬件接入 | 读取 shm-bridge-vmid 后改变 bridge owner bits；SELF_OWNER 路径用于 EL2 下 Linux 持有的内存。 | DT/consumer; Kbuild |
| [el2/0014](../patches/el2/0014-arm64-dts-qcom-sc8280xp-el2-Set-correct-owner-for-SC.patch) | 硬件接入 | SC8280XP overlay 把 SELF_OWNER 写入 scm 节点，使 0012 的分支在 EL2 DTB 中生效。 | compiled overlay |
| [el2/0016](../patches/el2/0016-wip-remoteproc-qcom_q6v5_pas-Avoid-using-broken-rese.patch) | 硬件接入 | broken-reset 选择没有 start/load 的 ops，仅 attach/stop；保留 devm_rproc 生命周期和 upstream bool auto_boot。 | DT/ops reachability; Kbuild |
| [el2/0018](../patches/el2/0018-arm64-dts-qcom-sc8280xp-el2-Add-qcom-broken-reset-fo.patch) | 硬件接入 | 为 ADSP/SLPI/NSP0/NSP1 标记 broken-reset；本机四个 DSP 因而不会选择 reset/restart 分支。 | compiled overlay; reason to remove el2/0006 |
| [el2/0020](../patches/el2/0020-rpmsg-core-Call-announce_destroy-only-after-announce.patch) | 正确性修复 | 只对真正 announce_create 的 endpoint 调 announce_destroy，匹配创建/销毁生命周期。 | control-flow; Kbuild |
| [el2/0021](../patches/el2/0021-rpmsg-core-Make-it-easier-to-manually-create-endpoin.patch) | 依赖性重构 | 允许 QRTR 显式创建 endpoint；与 0022 的打开/关闭状态机一组维护。 | dependency of el2/0022 |
| [el2/0022](../patches/el2/0022-net-qrtr-smd-Fix-race-conditions-while-opening-closi.patch) | 正确性修复 | QRTR 在 endpoint 有效区间注册/解除 node，调整回调并发与释放顺序，避免打开/关闭竞态。 | lifetime/control-flow; Kbuild |
| [el2/0023](../patches/el2/0023-remoteproc-qcom-report-attach-errors-and-SMP2P-state.patch) | 错误处理/诊断 | IRQ read error 向 probe 传播；有效 offline 与读取失败分别处理。附带日志用于观察同一状态机，尚保留。 | native 64 level/error cases |
| [el2/0024](../patches/el2/0024-remoteproc-qcom-wait-for-SMP2P-boot-state.patch) | workaround | 仅 no-reset 且映射返回 ENODEV 时在 probe 内等待，预算 100ms；有效 offline 不强制改成 running。等待机制通过测试，100ms 对所有启动是否足够尚待实测。 | native delayed mappings/timeouts; hardware A/B pending |

## 构建入口与验证

[kernel-source.env](../kernel-source.env) 固定仓库、tag 和 SHA；CI/本地脚本在应用前验证 pristine HEAD。清单检查会拒绝未登记、缺失或内容哈希改变的补丁。本地复用源码还检查补丁清单摘要，旧源码需使用新的 KERN_SRC 目录。RPM/DEB manifest 增加 upstream repository/commit，并附带 patch-inventory.json。

已完成：

- pristine v7.3 上标准链与 EL2 链完整应用，DTS/驱动镜像一致性检查通过。
- 137 项 Python 测试：135 通过、2 跳过。包含 11 项完整补丁链/原生 C 检查，以及 RPM/DEB 包装流程 fixture；fixture 不表示已经生成完整发行包。
- 原始与修补后的 HI846 函数对照：正数 PM 返回值 + 成功 I2C 写的错误被复现并消除；错误 I2C 与已有负错误保持正确。
- 原始与修补后的 Iris 时间戳函数对照：input 写满环后，output fallback 使用的索引在原函数中越界，修改后有效。
- 两个 GPIO acquisition/error 代码块：`-EPROBE_DEFER`、`-EIO` 原样返回，可选 GPIO 为 NULL 时继续。
- 原生测试覆盖 QMP 超时/资源归还、PLL 引用、plane mask、ACK 边界、remoteproc stop，以及 SMP2P 64 种 level/error、延迟映射和超时边界。
- Fedora/Ubuntu × standard/EL2 四组配置均通过原有严格审计，保持 `CONFIG_RUST=y`。
- Fedora standard/EL2 的关键 Kbuild 对象编译成功；EL2 侧覆盖所有现存补丁涉及的 Gaokun 驱动，含完整 MSM、Iris、remoteproc 目录，以及触屏、双摄、EC/电池、QMP、UCSI、时钟、蓝牙、TZMEM、RPMsg/QRTR、AudioReach 和 QSEE TPM。最终日志无 compiler warning/error。
- 普通与 EL2 DTB 编译成功；解包确认 Iris compatible/OEM firmware，四个 DSP 的 `qcom,broken-reset`，以及 EL2 overlay 应用。
- shell 语法、清单一致性、`git diff --check` 通过。

本轮产物是可应用且完成关键对象编译的 v7.3 补丁树。完整 Image/modules/RPM 的发行构建及 v7.3 实机启动/A/B 尚未执行。

验证源、工具链与日志保存在本机 `/home/zhzy0077/.cache/gaokun-rebuild/`；Rust/libclang/bindgen 从 Fedora RPM 解包至该目录，没有安装到系统。配置日志为 `configure-*.log`，最终编译日志为 `kbuild-final-{standard,el2}.log`，测试日志为 `unit-tests-final.log`。摘要见 [验证记录](kernel_v7.3_validation.json)。

复核入口：

```bash
python3 tools/kernel/check-patch-inventory.py
# GAOKUN_KERNEL_SRC 指向完整、未修改的 v7.3 源码
GAOKUN_KERNEL_SRC=/path/to/pristine-linux-v7.3 python3 -B tests/test_kernel_patches.py -v
```

下一轮硬件验收按清单中 7 项 workaround 的触发条件做对照；同时覆盖上游背光状态管理、EL2 DSP attach、Iris 重复解码和 PCIe/USB 恢复。每轮固定内核 SHA、补丁清单摘要和单一变量，以实际结果决定删除或保留。
