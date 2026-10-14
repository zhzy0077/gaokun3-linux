# Gaokun3 扬声器默认音量校准

补丁：`patches/others/0012-ASoC-qcom-audioreach-calibrate-Gaokun3-speaker-gain.patch`。

## 目标和实现

使桌面 100% 输出约等于原内核的 150% 输出。PulseAudio/PipeWire 的音量百分比使用立方映射，150% 对应 `1.5^3 = 27/8` 倍线性增益，即约 +10.57 dB。

补丁在 Audioreach 向 DSP 发送主增益时增加这个倍率，仅匹配：

- 根设备树 compatible：`huawei,gaokun3`。
- 播放 graph ID：1，即当前原生与 DP 扩展 topology 中连接内置扬声器的 MultiMedia2。

用户可见的 ALSA 主增益保持原值（unity 8192），发往 DSP 的实际 Q13 值变为 27648。静音 0 保持为 0，结果按 16 位无符号 Q13 上限 65535 饱和。其他设备、耳机、麦克风和 DP graph 不变；WSA 和功放音量保护上限不变。

该修改不实现 Windows Histen 或主动扬声器保护。软件放大与 DSP 放大位于信号链不同位置，因此正常内容的相对响度应在新内核启动后复测，不能把源代码编译通过当成声学校准完成。接近满幅的音频可能削波，与原先软件 150% 的情况类似。

## 构建与验证

现有 CI 和本地构建脚本会自动应用 `patches/others/*.patch`，无需修改构建脚本；标准与 EL2 构建均包含此补丁。

```sh
python3 -m unittest discover -s tests -p test_speaker_gain.py -v
```

测试从补丁提取实际 C 函数并编译，遍历全部 65536 个增益值、8 个 graph 和目标/非目标设备，验证倍率、范围限制、静音和路径隔离。

已在本机 Linux 7.2.9 构建树验证补丁可应用，并编译通过 `sound/soc/qcom/qdsp6/audioreach.o`。检查期间临时修改的构建树源码及对象已恢复。本次未安装新内核，也未重启。

## 新内核启动后的设置

旧内核的 150% 软件音量是本次校准参考。启动包含补丁的新内核后，将软件音量设为 100%，避免继续使用 150% 时两个倍率叠加：

```sh
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.00
```

逐步复测常用音乐、视频与低电平测试音。当前 topology 的 graph 分配是实现前提；将来更换 topology 后应重新确认 MultiMedia2 的扬声器路由。
