# Gaokun3 internal microphone default

The capture gain belongs to the platform ALSA UCM configuration. UCM writes VA_DEC0/1 every time the internal microphone device is enabled, overriding a kernel initial value.

`tools/audio/ucm2/Qualcomm/gaokun3-mic/` supplies a board-private profile with VA_DEC0/1 Volume106: +22dB, 6dB above the generic value100 (+16dB). Only the internal microphone enable sequences differ from the existing HiFi routes. Lenovo, headset-microphone, headphone and speaker settings retain their original configuration.

The Huawei DMI selector and the normal-board branch of the isolated DP-test selector use this profile. The isolated DP-test model deliberately retains its existing experimental profiles and microphone gain100.

The platform RPM (release6) installs this profile into `/usr/share/gaokun3/ucm2`; shared image builds install it into `/usr/share/alsa/ucm2`. The platform package's existing PipeWire and WirePlumber service environment selects its private UCM tree.

Validation: three static calibration/packaging tests, DP-selector regression tests and real-libasound parsing across both root trees and both boot models. Live validation of the equivalent `/etc/alsa/ucm2-gaokun3` overlay restored both gains to106 after resetting them to100 and restarting audio services. A15-second speaker-video microphone capture transcribed coherently with the installed Handy whisper-medium model on CPU. The GPU Vulkan backend produced incorrect transcription for the same recording; Handy's CPU preference is an application setting, separate from this platform calibration.

The repository change does not itself install a new RPM. The validated `/etc` overlay remains active on the current system.
