# Gaokun3 FTE7001 指纹支持

Gaokun3 的 FTE7001 指纹器通过 Qualcomm TEE 中的原厂 `fingerpr.mbn` 访问。
用户态客户端使用固定提交 `736419e25a2036aac3292a10a93e394a90750ca3`
的 quic-teec，注册 GPFS listener，并通过 UID 122 加载原厂 TA。

`qcomtee` 对用户 listener 内存使用平台默认 bridge 策略时，TA 的 GPFS 内存对象
不可用。`qtee-user-memory-vmid.patch` 为非 `TEE_SHM_PRIV` 内存增加受控 VMID 策略：
`qcomtee.user_bridge_mode=1` 使用 HLOS，`=2` 使用 SELF_OWNER+HLOS。私有调用缓冲
继续使用平台策略。真机使用模式 1。

指纹客户端只提供 fprintd 所需的模板计数、24 样本录入、验证和删除操作。GPFS 数据保存在
`/var/lib/gaokun3-fingerprint/secure-files`，目录权限为 0700，文件权限为 0600。
SELinux 模块将 TEE 设备、GPIO 和客户端 memfd 访问限定给 `fprintd_t`。

libfprint 驱动基于提交 `80a4b5ec612892c5c056c48dddaa561452cf37ec`，通过
`FP_FTE7001_QTEE=enabled` 提供一个硬件模板槽位。fprintd override 从
`/opt/gaokun3-fingerprint/libfprint` 加载该库，并将存储目录限定为可写路径。

## 构建和安装

实验内核通过现有 `scripts/ci/20_build_kernel_variants.sh` 和
`scripts/ci/configure_kernel.sh` 构建。实验版本使用独立模块目录。

```sh
bash tools/fingerprint/build-qtee-client.sh /path/to/quic-teec /path/to/native-output
bash tools/fingerprint/build-libfprint.sh /path/to/libfprint /path/to/libfprint-output
sudo bash tools/fingerprint/install-libfprint.sh \
  /path/to/libfprint-output/stage /path/to/native-output
```

`build-qtee-client.sh` 锁定 quic-teec 提交并生成原生客户端与 MCU 复位程序。
`build-libfprint.sh` 在 Fedora 45 容器中构建固定版本 libfprint，并运行
`fpi-device`、`fpi-ssm`、`fpi-assembling` 测试。安装程序验证固件 SHA256、部署
SELinux 模块和 systemd override，并启动 fprintd。

真机已完成 fprintd 录入、已录入手指验证、未录入手指拒绝和重启后验证。实验内核启动项为
`Gaokun3 fingerprint experiment`；Fedora 原内核保持默认启动项。
