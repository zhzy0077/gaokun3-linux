"""Native execution of common/USB power functions from the patched kernel.

Invoked by test_kernel_patches with pristine source + the complete series.
Mocks count real resource calls; no device access is performed.
"""
from pathlib import Path
import re
import subprocess
import tempfile


def body(source, name):
    return re.search(r'static (?:bool|int) ' + name + r'\(.*?\n}', source, re.S).group(0)


def exercise_qmp_resources(source):
    parameter = re.search(r'static bool gaokun_keep_common_power[^;]*;', source).group(0)
    functions = '\n'.join(body(source, name) for name in (
        'qmp_combo_keep_common_power', 'qmp_combo_com_init',
        'qmp_combo_com_exit', 'qmp_combo_usb_power_on'))
    constants = sorted(set(re.findall(r'\b(?:QPHY_\w+|SW_\w+|USB3_MODE|DP_MODE|'
                                      r'INVERT_CC_POLARITY|SERDES_START|PCS_START|'
                                      r'PHYSTATUS|PHY_INIT_COMPLETE_TIMEOUT)\b', functions)))
    defines = '\n'.join(f'#define {name} {i + 1}' for i, name in enumerate(constants))
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
#define __iomem
static bool gaokun_keep_common_power;
static const char *board = "huawei,gaokun3";
static bool of_machine_is_compatible(const char *s) { return !strcmp(board, s); }
enum { QMPPHY_MODE_USB3DP, QMPPHY_MODE_DP_ONLY, QMPPHY_MODE_USB3_ONLY };
#define TYPEC_ORIENTATION_REVERSE 2
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
#define qmp_configure(...) ((void)0)
#define qmp_configure_lane(...) ((void)0)
#define usleep_range(...) ((void)0)
#define readl_poll_timeout(addr, val, cond, delay, timeout) \
    ((void)(addr), (void)(&(val)), poll_error)
struct qmp_phy_cfg {
    int num_vregs, num_resets;
    unsigned regs[128];
    bool invert_cc_polarity, has_pwrdn_delay;
};
struct qmp_combo {
    const struct qmp_phy_cfg *cfg;
    void *dev, *com, *pcs_aon, *pcs, *pcs_usb, *pcs_misc, *aon_toggle;
    void *serdes, *tx, *rx, *tx2, *rx2;
    void *vregs, *resets, *clks, *pipe_clk;
    int init_count, usb_init_count, dp_init_count, num_clks;
    unsigned orientation, qmpphy_mode;
};
struct phy { struct qmp_combo *qmp; };
static struct qmp_combo *phy_get_drvdata(struct phy *p) { return p->qmp; }
static int regulators, clocks, pipes, reset_calls, writes;
static int regulator_error, clock_error, pipe_error, poll_error;
static int regulator_bulk_enable(int n, void *p)
{ (void)n; (void)p; if (regulator_error) return regulator_error; regulators++; return 0; }
static void regulator_bulk_disable(int n, void *p)
{ (void)n; (void)p; assert(regulators > 0); regulators--; }
static int clk_bulk_prepare_enable(int n, void *p)
{ (void)n; (void)p; if (clock_error) return clock_error; clocks++; return 0; }
static void clk_bulk_disable_unprepare(int n, void *p)
{ (void)n; (void)p; assert(clocks > 0); clocks--; }
static int clk_prepare_enable(void *p)
{ (void)p; if (pipe_error) return pipe_error; pipes++; return 0; }
static void clk_disable_unprepare(void *p)
{ (void)p; assert(pipes > 0); pipes--; }
static int reset_control_bulk_assert(int n, void *p)
{ (void)n; (void)p; reset_calls++; return 0; }
static int reset_control_bulk_deassert(int n, void *p)
{ (void)n; (void)p; reset_calls++; return 0; }
static void qphy_setbits(void *p, unsigned reg, unsigned mask)
{ (void)p; (void)reg; (void)mask; writes++; }
static void qphy_clrbits(void *p, unsigned reg, unsigned mask)
{ (void)p; (void)reg; (void)mask; writes++; }
static void writel(unsigned val, void *p) { (void)val; (void)p; writes++; }
''' + defines + '\n' + functions + r'''
int main(void)
{
    char mmio[4096] = {0};
    struct qmp_phy_cfg cfg = {0};
    struct qmp_combo q = {.cfg = &cfg, .com = mmio, .pcs = mmio,
        .pcs_aon = mmio, .pcs_usb = mmio};
    struct phy phy = {&q};
    /* The real initializer defaults on; board and force guards still apply. */
    assert(gaokun_keep_common_power);
    assert(qmp_combo_keep_common_power(true));
    assert(!qmp_combo_keep_common_power(false));
    board = "lenovo,thinkpad-x13s";
    assert(!qmp_combo_keep_common_power(true));
    board = "huawei,gaokun3";
    gaokun_keep_common_power = false;
    /* Normal init acquires once even with two users. */
    assert(qmp_combo_com_init(&q, false) == 0);
    assert(qmp_combo_com_init(&q, false) == 0);
    assert(q.init_count == 2 && pipes == 1 && regulators == 1 && clocks == 1);
    /* USB timeout must not steal the shared PIPE clock from common/DP. */
    poll_error = -110;
    assert(qmp_combo_usb_power_on(&phy) == -110 && pipes == 1);
    qmp_combo_com_exit(&q, false);
    assert(q.init_count == 1 && pipes == 1);
    qmp_combo_com_exit(&q, false);
    assert(q.init_count == 0 && !pipes && !regulators && !clocks);
    poll_error = 0;
    /* Forced init failures do not decrement unacquired references. */
    for (int force = 0; force < 2; force++) {
        for (int failure = 0; failure < 3; failure++) {
            q.init_count = force ? 2 : 0;
            regulator_error = failure == 0 ? -5 : 0;
            clock_error = failure == 1 ? -5 : 0;
            pipe_error = failure == 2 ? -5 : 0;
            assert(qmp_combo_com_init(&q, force) == -5);
            assert(q.init_count == (force ? 2 : 0));
            assert(!pipes && !clocks && !regulators);
        }
    }
    regulator_error = clock_error = pipe_error = 0;
    /* A/B behavior: opt-in + exact board only; resources remain balanced. */
    for (int enable = 0; enable < 2; enable++) {
        gaokun_keep_common_power = enable;
        for (int gaokun = 0; gaokun < 2; gaokun++) {
            board = gaokun ? "huawei,gaokun3" : "lenovo,thinkpad-x13s";
            q.init_count = 0;
            assert(qmp_combo_com_init(&q, false) == 0);
            assert(qmp_combo_com_init(&q, false) == 0);
            int resets_before = reset_calls, writes_before = writes;
            qmp_combo_com_exit(&q, true);
            assert(q.init_count == 2);
            if (enable && gaokun) {
                assert(pipes == 1 && regulators == 1 && clocks == 1);
                assert(reset_calls == resets_before && writes > writes_before);
            } else {
                assert(!pipes && !regulators && !clocks);
                assert(reset_calls > resets_before);
            }
            for (unsigned mode = 0; mode < 3; mode++) {
                q.qmpphy_mode = mode;
                assert(qmp_combo_com_init(&q, true) == 0);
                assert(q.init_count == 2 && pipes == 1 && clocks == 1 && regulators == 1);
                if (enable && gaokun) assert(reset_calls == resets_before);
                if (mode != 2) qmp_combo_com_exit(&q, true);
            }
            assert(qmp_combo_usb_power_on(&phy) == 0);
            qmp_combo_com_exit(&q, false);
            qmp_combo_com_exit(&q, false);
            assert(!q.init_count && !pipes && !regulators && !clocks);
        }
    }
    return 0;
}
'''
    harness = harness.replace('static bool gaokun_keep_common_power;', parameter)
    with tempfile.TemporaryDirectory(prefix='gaokun-qmp-test-') as directory:
        path = Path(directory) / 'qmp.c'
        binary = Path(directory) / 'qmp'
        path.write_text(harness)
        result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-variable', '-fsanitize=undefined',
                                 '-fno-sanitize-recover=undefined', str(path), '-o', str(binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
