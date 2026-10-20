"""Apply the complete series to pristine Linux 7.3 without editing the input.

Set GAOKUN_KERNEL_SRC to an unpacked kernel.org tarball or pristine checkout.
Only paths touched by the patches are copied to a temporary Git repository.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SRC = os.environ.get('GAOKUN_KERNEL_SRC')


@unittest.skipUnless(KERNEL_SRC, 'set GAOKUN_KERNEL_SRC to pristine Linux 7.3')
class KernelPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='gaokun-patch-test-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.tree = Path(cls.directory.name)
        upstream = Path(KERNEL_SRC)
        version = dict(re.findall(r'^(VERSION|PATCHLEVEL|SUBLEVEL) = (\d+)$',
                                 (upstream / 'Makefile').read_text(), re.MULTILINE))
        if version != {'VERSION': '7', 'PATCHLEVEL': '3', 'SUBLEVEL': '0'}:
            raise ValueError('GAOKUN_KERNEL_SRC must contain Linux 7.3')
        cls.standard = [p for group in ('upstream', 'others', 'media')
                        for p in sorted((ROOT / 'patches' / group).glob('*.patch'))]
        cls.standard.append(ROOT / 'patches/0099-arm64-gaokun3-import-local-dts-and-defconfig.patch')
        cls.el2 = sorted((ROOT / 'patches/el2').glob('*.patch'))
        paths = {path for patch in cls.standard + cls.el2
                 for path in re.findall(r'^diff --git a/(\S+) b/\S+$',
                                        patch.read_text(), re.MULTILINE)}
        paths.add('drivers/remoteproc/remoteproc_core.c')
        paths.update('drivers/media/platform/qcom/iris/' + name for name in
                     ('iris_platform_sm8250.h', 'iris_platform_vpu2.c'))
        for path in paths:
            source = upstream / path
            if source.exists():
                target = cls.tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        cls.git('init', '-q')
        # Detached housekeeping must not outlive this disposable repository.
        cls.git('config', 'maintenance.auto', 'false')
        cls.git('config', 'gc.auto', '0')
        cls.git('config', 'user.name', 'Patch regression test')
        cls.git('config', 'user.email', 'test@localhost')
        cls.git('config', 'commit.gpgsign', 'false')
        cls.git('add', '-A')
        cls.git('commit', '-qm', 'Pristine Linux 7.3 patch targets')
        # Same order and commands as scripts/ci/20_build_kernel_variants.sh.
        for group in ('upstream', 'others', 'media'):
            cls.git('am', *sorted((ROOT / 'patches' / group).glob('*.patch')))
        cls.git('am', cls.standard[-1])

    @classmethod
    def git(cls, *args):
        result = subprocess.run(['git', *map(str, args)], cwd=cls.tree,
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(f'git {args[0]} failed:\n{result.stdout}{result.stderr}')
        return result.stdout

    def test_automatic_git_housekeeping_is_disabled(self):
        self.assertEqual(self.git('config', '--local', '--bool', '--get',
                                  'maintenance.auto').strip(), 'false')
        self.assertEqual(self.git('config', '--local', '--int', '--get',
                                  'gc.auto').strip(), '0')

    @unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
    def test_bonded_pll_can_be_programmed_before_phy_enable(self):
        source = (self.tree / 'drivers/gpu/drm/msm/dsi/phy/dsi_phy_7nm.c').read_text()
        enable = re.search(r'static void dsi_pll_enable_pll_bias\([^;]*?\)\n\{.*?\n\}',
                           source, re.DOTALL).group(0)
        for name in ('dsi_7nm_phy_enable', 'dsi_7nm_phy_disable'):
            body = re.search(r'static (?:int|void) ' + name + r'\(.*?\n\}', source, re.DOTALL).group(0)
            self.assertNotIn('pll_enable_cnt', body, name)
        harness = r'''
#include <assert.h>
#include <limits.h>
#include <stdint.h>
typedef uint32_t u32;
#define REG_DSI_7nm_PHY_CMN_CTRL_0 0
#define REG_DSI_7nm_PHY_PLL_SYSTEM_MUXES 0
#define DSI_7nm_PHY_CMN_CTRL_0_PLL_SHUTDOWNB 1U
#define spin_lock_irqsave(lock, flags) do { (void)(lock); (flags) = 0; } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(lock); (void)(flags); } while (0)
#define WARN_ON(condition) assert(!(condition))
struct phy { u32 *base, *pll_base; };
struct dsi_pll_7nm { struct phy *phy; int pll_enable_lock, pll_enable_cnt; };
static u32 readl(u32 *reg) { return *reg; }
static void writel(u32 value, u32 *reg) { *reg = value; }
static void ndelay(unsigned n) { (void)n; }
''' + enable + r'''
int main(void) {
    u32 control = 0, mux = 0;
    struct phy phy = {&control, &mux};
    struct dsi_pll_7nm pll = {.phy = &phy};
    dsi_pll_enable_pll_bias(&pll);
    assert(pll.pll_enable_cnt == 1 && control == 1 && mux == 0xc0);
    /* A second host must still program shared PLL state, not return early. */
    control = mux = 0;
    dsi_pll_enable_pll_bias(&pll);
    assert(pll.pll_enable_cnt == 2 && control == 1 && mux == 0xc0);
    return 0;
}
'''
        path = self.tree / 'pll-test.c'
        binary = self.tree / 'pll-test'
        path.write_text(harness)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)],
                       check=True, capture_output=True)
        subprocess.run([str(binary)], check=True)

    def test_gaokun_primary_plane_pairing(self):
        from test_dpu_plane_ownership import mask_function
        source = (self.tree / 'drivers/gpu/drm/msm/disp/dpu1/dpu_kms.c').read_text()
        self.assertIn(mask_function(), source)
        objects = re.search(r'static int _dpu_kms_drm_obj_init\(.*?\n}',
                            source, re.S).group(0)
        mask = objects.index('dpu_plane_possible_crtcs(type, primary_planes_idx,')
        increment = objects.index('primary_planes[primary_planes_idx++] = plane;')
        self.assertLess(mask, increment)
        self.assertIn('dpu_crtc_init(dev, primary_planes[i], cursor_planes[i])', objects)
        self.assertIn('encoder->possible_crtcs = (1 << dev->mode_config.num_crtc) - 1;', objects)

    @unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
    def test_qmp_resource_ownership_and_board_scoped_reconfiguration(self):
        from test_qmp_common_power import exercise_qmp_resources
        source = (self.tree / 'drivers/phy/qualcomm/phy-qcom-qmp-combo.c').read_text()
        self.assertIn('static bool gaokun_keep_common_power = true;', source)
        self.assertIn('module_param(gaokun_keep_common_power, bool, 0444)', source)
        exercise_qmp_resources(source)

    def test_ec_ack_encoder_matches_tested_mirror(self):
        pattern = r'int gaokun_ec_ucsi_pan_ack\(.*?\n}'
        patched = (self.tree / 'drivers/platform/arm64/huawei-gaokun-ec.c').read_text()
        mirror = (ROOT / 'drivers/gaokun-ec/huawei-gaokun-ec.c').read_text()
        self.assertEqual(re.search(pattern, patched, re.S).group(0),
                         re.search(pattern, mirror, re.S).group(0))

    @unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
    def test_hi846_success_clears_runtime_pm_positive_result(self):
        name = 'drivers/media/i2c/hi846.c'
        pattern = r'static void hi846_write_reg_16\(.*?\n}'
        before = re.search(pattern, (Path(KERNEL_SRC) / name).read_text(), re.S).group()
        after = re.search(pattern, (self.tree / name).read_text(), re.S).group()
        harness = r'''
#include <stdint.h>
#include <errno.h>
#include <stddef.h>
typedef uint16_t u16;
typedef uint8_t u8;
struct i2c_client { int dev; };
struct hi846 { struct i2c_client sd; };
#define v4l2_get_subdevdata(p) (p)
#define dev_err(...) ((void)0)
static int result = 4, calls;
static void put_unaligned_be16(u16 n, u8 *p) { p[0] = n >> 8; p[1] = n; }
static int i2c_master_send(struct i2c_client *c, u8 *p, size_t n)
{ (void)c; (void)p; (void)n; ++calls; return result; }
''' + '\n{function}\n' + r'''
int main(void) {
    struct hi846 sensor = {0};
    int ret = 1;
    hi846_write_reg_16(&sensor, 0x1234, 0x5678, &ret);
    if (ret != 0 || calls != 1) return 1;
    result = 2;
    hi846_write_reg_16(&sensor, 0, 0, &ret);
    if (ret != -EIO) return 2;
    hi846_write_reg_16(&sensor, 0, 0, &ret);
    return calls == 2 && ret == -EIO ? 0 : 3;
}
'''
        for label, function, expected in [('upstream', before, 1), ('patched', after, 0)]:
            source = self.tree / f'hi846-{label}.c'
            binary = source.with_suffix('')
            source.write_text(harness.replace('{function}', function))
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            self.assertEqual(subprocess.run([str(binary)]).returncode, expected, label)

    @unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
    def test_gpio_probe_errors_are_returned(self):
        # Execute the actual acquisition/error blocks, including a NULL optional GPIO.
        for name, owner, field in [('huawei-gaokun-ec.c', 'ec', 'enable_gpio'),
                                    ('huawei-gaokun-battery.c', 'ecbat', 'bat_sta')]:
            text = (ROOT / 'drivers/gaokun-ec' / name).read_text()
            block = re.search(r'\t' + owner + r'->' + field +
                              r' = devm_gpiod_get_optional\(.*?"Failed to get .*?;\n',
                              text, re.S).group()
            harness = r'''
#include <stdint.h>
#define GPIOD_OUT_HIGH 1
#define GPIOD_OUT_LOW 0
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
static void *gpio;
#define devm_gpiod_get_optional(...) gpio
#define dev_err_probe(dev, err, ...) (err)
struct state { void *enable_gpio, *bat_sta; };
static int probe(struct state *OWNER) {
BLOCK
    return 23;
}
int main(void) {
    struct state s = {0};
    gpio = (void *)(intptr_t)-517;
    if (probe(&s) != -517) return 1;
    gpio = (void *)(intptr_t)-5;
    if (probe(&s) != -5) return 2;
    gpio = 0;
    return probe(&s) == 23 ? 0 : 3;
}
'''.replace('OWNER', owner).replace('BLOCK', block)
            source = self.tree / (name + '-probe.c')
            binary = source.with_suffix('')
            source.write_text(harness)
            subprocess.run(['cc', '-std=c11', str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)

    @unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
    def test_iris_timestamp_index_is_valid_between_input_and_output(self):
        name = 'drivers/media/platform/qcom/iris/iris_common.c'
        pattern = r'void iris_set_ts_metadata\(.*?\n}'
        before = re.search(pattern, (Path(KERNEL_SRC) / name).read_text(), re.S).group()
        after = re.search(pattern, (self.tree / name).read_text(), re.S).group()
        harness = r'''
#include <stdint.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define V4L2_BUF_FLAG_TIMECODE 1
#define V4L2_BUF_FLAG_TSTAMP_SRC_MASK 2
#define NSEC_PER_USEC 1000
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define do_div(n, d) ((n) /= (d))
struct vb2_buffer { u64 timestamp; };
struct vb2_v4l2_buffer { struct vb2_buffer vb2_buf; u32 flags, timecode; };
struct iris_inst { u32 metadata_idx; struct { u32 flags, tc; u64 ts_us, ts_ns; } tss[4]; };
FUNCTION
int main(void) {
    struct iris_inst inst = {0};
    struct vb2_v4l2_buffer vbuf = {0};
    for (unsigned i = 0; i < 20; ++i) {
        vbuf.vb2_buf.timestamp = i * 1000;
        iris_set_ts_metadata(&inst, &vbuf);
        /* iris_get_ts_metadata uses this index on an unmatched output timestamp. */
        if (inst.metadata_idx >= ARRAY_SIZE(inst.tss)) return 1;
    }
    return 0;
}
'''
        for label, function, expected in [('upstream', before, 1), ('patched', after, 0)]:
            source = self.tree / f'iris-ring-{label}.c'
            binary = source.with_suffix('')
            source.write_text(harness.replace('FUNCTION', function))
            subprocess.run(['cc', '-std=c11', str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            self.assertEqual(subprocess.run([str(binary)]).returncode, expected, label)

    def test_plane_allocator_preserves_crtc_masks(self):
        source = (self.tree / 'drivers/gpu/drm/msm/disp/dpu1/dpu_plane.c').read_text()
        common = re.search(r'static struct drm_plane \*dpu_plane_init_common\(.*?\n}',
                           source, re.S).group(0)
        self.assertRegex(common, r'drmm_universal_plane_alloc\(dev, struct dpu_plane, base,\s*'
                         r'possible_crtcs, &dpu_plane_funcs,')
        for name in ('dpu_plane_init', 'dpu_plane_init_virtual'):
            backend = re.search(r'struct drm_plane \*' + name + r'\(.*?\n}',
                                source, re.S).group(0)
            self.assertRegex(backend, r'dpu_plane_init_common\(dev, type, possible_crtcs,')

    def test_sc8280xp_codec_resources_match_iris(self):
        """Catch the missing match and resource-name failures of the old series."""
        iris = self.tree / 'drivers/media/platform/qcom/iris'
        probe = (iris / 'iris_probe.c').read_text()
        self.assertRegex(probe, r'"qcom,sm8250-venus",\s*\.data = &sm8250_data')
        platform = (iris / 'iris_platform_vpu2.c').read_text()
        data = re.search(r'const struct iris_platform_data sm8250_data = \{(.*?)\n};',
                         platform, re.S).group(1)
        self.assertIn('.num_vpp_pipe = 4', data)
        platform += (iris / 'iris_platform_sm8250.h').read_text()
        soc = (self.tree / 'arch/arm64/boot/dts/qcom/sc8280xp.dtsi').read_text()
        codec = soc.split('iris: video-codec@aa00000 {', 1)[1].split('iris_opp_table:', 1)[0]
        for field, prop in (('clk_rst_tbl', 'reset-names'), ('opp_pd_tbl', 'power-domain-names')):
            table = re.search(r'\.' + field + r' = (\w+),', data).group(1)
            names = re.findall(r'"([^"]+)"', re.search(
                re.escape(table) + r'\[\] = \{(.*?)\};', platform, re.S).group(1))
            dt_names = re.findall(r'"([^"]+)"', re.search(
                prop + r' = (.*?);', codec, re.S).group(1))
            self.assertTrue(set(names) <= set(dt_names), (field, names, dt_names))
        self.assertNotIn('venus-decoder', codec)
        self.assertNotIn('venus-encoder', codec)
        board = (ROOT / 'dts/sc8280xp-huawei-gaokun3.dts').read_text()
        override = re.search(r'&iris \{(.*?)\};', board, re.S).group(1)
        self.assertIn('status = "okay";', override)
        fw = re.search(r'firmware-name = "([^"]+)";', override).group(1)
        self.assertTrue((ROOT / 'firmware' / fw).is_file())

    def test_complete_standard_and_el2_series(self):
        for name in ('sc8280xp-huawei-gaokun3.dts', 'sc8280xp-huawei-gaokun3-camera.dtsi'):
            self.assertEqual((self.tree / 'arch/arm64/boot/dts/qcom' / name).read_bytes(),
                             (ROOT / 'dts' / name).read_bytes())
        self.assertEqual((self.tree / 'arch/arm64/configs/gaokun3_defconfig').read_bytes(),
                         (ROOT / 'defconfig/gaokun3_defconfig').read_bytes())
        for name in ('himax-spi-core.c', 'hx-algo.c', 'hx-algo.h'):
            self.assertEqual((self.tree / 'drivers/input/touchscreen' / name).read_bytes(),
                             (ROOT / 'drivers/touchscreen-hx83121a' / name).read_bytes())
        self.assertEqual((self.tree / 'drivers/char/tpm/tpm_qcom_qsee.c').read_bytes(),
                         (ROOT / 'drivers/tpm-qcom-qsee/tpm_qcom_qsee.c').read_bytes())
        self.assertEqual((self.tree / 'drivers/usb/typec/ucsi/ucsi_huawei_gaokun.c').read_bytes(),
                         (ROOT / 'drivers/gaokun-ec/ucsi_huawei_gaokun.c').read_bytes())
        for source, mirror in (
                ('drivers/platform/arm64/huawei-gaokun-ec.c', 'drivers/gaokun-ec/huawei-gaokun-ec.c'),
                ('drivers/power/supply/huawei-gaokun-battery.c', 'drivers/gaokun-ec/huawei-gaokun-battery.c'),
                ('drivers/gpu/drm/panel/panel-himax-hx83121a.c', 'drivers/panel-hx83121a/panel-himax-hx83121a.c'),
                ('drivers/gpu/drm/msm/dsi/dsi_host.c', 'drivers/panel-hx83121a/dsi_host.c')):
            self.assertEqual((self.tree / source).read_bytes(), (ROOT / mirror).read_bytes(), source)
        pinctrl = (self.tree / 'drivers/pinctrl/qcom/pinctrl-sc8280xp.c').read_text()
        self.assertNotRegex(pinctrl, r'\{\s*175,\s*237\s*\}')
        self.assertRegex(pinctrl, r'\{\s*174,\s*222\s*\}')
        self.git('apply', *self.el2)
        pas = (self.tree / 'drivers/remoteproc/qcom_q6v5_pas.c').read_text()
        self.assertEqual(pas.count('static int qcom_pas_attach('), 1)
        for name in ('qcom_pas_ops', 'qcom_pas_minidump_ops', 'qcom_pas_ops_no_reset'):
            ops = re.search(r'static const struct rproc_ops ' + name + r' = \{(.*?)\n\};',
                            pas, re.DOTALL).group(1)
            self.assertEqual(ops.count('.attach ='), 1, name)
        attach = re.search(r'static int qcom_pas_attach\(.*?\n\}', pas, re.DOTALL).group(0)
        self.assertIn('qcom_q6v5_attach(&pas->q6v5)', attach)
        self.assertIn('qcom_q6v5_unprepare(&pas->q6v5)', attach)
        self.assertIn('qcom_sysmon_shutdown_irq_state(pas->sysmon)', attach)
        core = (self.tree / 'drivers/remoteproc/remoteproc_core.c').read_text()
        self.assertIn('schedule_work(&rproc->attach_work)', core)
        self.assertNotIn('RPROC_AUTO_BOOT_RESTART_IF_FW_AVAILABLE', core)
        self.assertIn('rproc->auto_boot = desc->auto_boot;', pas)
        self.check_stop_behavior()
        from test_adsp_boot_diagnostics import extract_function, functions_from_patch
        for (path, name), function in functions_from_patch().items():
            self.assertEqual(extract_function((self.tree / path).read_text(), name),
                             function, name)

    def check_stop_behavior(self):
        if not shutil.which('cc'):
            self.skipTest('native C compiler required for stop-state behavior')
        source = (self.tree / 'drivers/remoteproc/qcom_q6v5.c').read_text()
        stop = re.search(r'int qcom_q6v5_request_stop\(.*?\n\}', source, re.DOTALL).group(0)
        detect = re.search(r'int qcom_q6v5_read_smp2p_state\(.*?\n\}', source, re.DOTALL).group(0)
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#define RPROC_DETACHED 1
#define RPROC_ATTACHED 2
#define RPROC_RUNNING 3
#define RPROC_CRASHED 4
#define IRQCHIP_STATE_LINE_LEVEL 0
#define dev_info(...) ((void)0)
#define HZ 100
#define BIT(n) (1U << (n))
struct rproc { int state; };
struct qcom_sysmon { bool ack; };
struct qcom_q6v5 {
    bool running;
    struct rproc *rproc;
    int state, stop_bit, stop_done;
    int handover_irq, ready_irq, fatal_irq, stop_irq;
};
static bool lines[4];
static int signals;
static bool qcom_sysmon_shutdown_acked(struct qcom_sysmon *s) { return s && s->ack; }
static int irq_get_irqchip_state(int irq, int kind, bool *value)
{ (void)kind; *value = lines[irq]; return 0; }
static void qcom_smem_state_update_bits(int state, unsigned mask, unsigned value)
{ (void)state; (void)mask; if (value) ++signals; }
static int wait_for_completion_timeout(int *completion, int timeout)
{ (void)completion; (void)timeout; return 1; }
''' + detect + '\n' + stop + r'''
int main(void)
{
    struct rproc r = {0};
    struct qcom_q6v5 q = {.rproc = &r, .handover_irq = 0, .ready_irq = 1,
                         .fatal_irq = 2, .stop_irq = 3};
    struct qcom_sysmon sysmon = {false};
    lines[0] = lines[1] = true;
    qcom_q6v5_read_smp2p_state(&q);
    assert(r.state == RPROC_DETACHED && q.running);
    assert(qcom_q6v5_request_stop(&q, &sysmon) == 0 && signals == 1);
    assert(!q.running);
    qcom_q6v5_request_stop(&q, &sysmon);
    assert(signals == 1); /* Do not send a second stop. */
    int states[] = {RPROC_ATTACHED, RPROC_RUNNING, RPROC_CRASHED};
    for (unsigned i = 0; i < sizeof(states) / sizeof(states[0]); ++i) {
        r.state = states[i]; q.running = true;
        qcom_q6v5_request_stop(&q, &sysmon);
        assert(signals == (int)i + 2); /* Logical crash still needs a stop. */
    }
    q.running = true; sysmon.ack = true;
    qcom_q6v5_request_stop(&q, &sysmon);
    assert(signals == 4); /* Sysmon already shut down. */
    q.running = false; sysmon.ack = false; r.state = RPROC_CRASHED;
    qcom_q6v5_request_stop(&q, &sysmon);
    assert(signals == 4); /* Watchdog/fatal cleared running. */
    lines[2] = true; r.state = 0;
    qcom_q6v5_read_smp2p_state(&q);
    assert(!q.running && r.state == 0);
    return 0;
}
'''
        path = self.tree / 'stop-test.c'
        binary = self.tree / 'stop-test'
        path.write_text(harness)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)],
                       check=True, capture_output=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
