"""Compile and exercise the actual helper added by the Gaokun3 gain patch."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/others/0012-ASoC-qcom-audioreach-calibrate-Gaokun3-speaker-gain.patch"


class SpeakerGainTests(unittest.TestCase):
    def test_compiled_helper(self):
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("C compiler unavailable")
        added = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static u16 audioreach_playback_gain")
        end = added.index("\n}", start) + 2
        helper = added[start:end]
        harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
typedef uint16_t u16;
typedef uint32_t u32;
#define U16_MAX UINT16_MAX
#define min_t(type, a, b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
struct audioreach_graph_info { int id; };
struct audioreach_sub_graph { struct audioreach_graph_info *info; };
struct audioreach_container { struct audioreach_sub_graph *sub_graph; };
struct audioreach_module { struct audioreach_container *container; };
static bool gaokun3;
static bool of_machine_is_compatible(const char *name)
{
    assert(strcmp(name, "huawei,gaokun3") == 0);
    return gaokun3;
}
'''
        main = r'''
int main(void)
{
    struct audioreach_graph_info info = { .id = 1 };
    struct audioreach_sub_graph sg = { .info = &info };
    struct audioreach_container container = { .sub_graph = &sg };
    struct audioreach_module module = { .container = &container };
    for (unsigned int machine = 0; machine < 2; machine++) {
        gaokun3 = machine;
        for (int graph = 0; graph < 8; graph++) {
            info.id = graph;
            for (unsigned int gain = 0; gain <= UINT16_MAX; gain++) {
                unsigned int expected = gain;
                if (machine && graph == 1) {
                    expected = gain * 27 / 8;
                    if (expected > UINT16_MAX) expected = UINT16_MAX;
                }
                assert(audioreach_playback_gain(&module, gain) == expected);
            }
        }
    }
    gaokun3 = true;
    info.id = 1;
    assert(audioreach_playback_gain(&module, 0) == 0);
    assert(audioreach_playback_gain(&module, 8192) == 27648);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "test.c"
            binary = pathlib.Path(directory) / "test"
            source.write_text(harness + helper + main)
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_patch_retains_visible_gain_and_hardware_limits(self):
        patch = PATCH.read_text()
        self.assertIn("cfg->master_gain = audioreach_playback_gain(module, vol);", patch)
        self.assertNotIn("snd_soc_limit_volume", patch)
        self.assertNotIn("mod->gain =", patch)


if __name__ == "__main__":
    unittest.main()
