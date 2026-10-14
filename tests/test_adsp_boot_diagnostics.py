"""Native tests of the actual functions shipped in EL2 patch 0023."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/el2/0023-remoteproc-qcom-report-attach-errors-and-SMP2P-state.patch'
WAIT_PATCH = ROOT / 'patches/el2/0024-remoteproc-qcom-wait-for-SMP2P-boot-state.patch'
FUNCTIONS = {
    'drivers/remoteproc/qcom_q6v5.c': ('qcom_q6v5_read_smp2p_state', 'q6v5_ready_interrupt'),
    'drivers/remoteproc/qcom_q6v5_pas.c': ('qcom_pas_read_boot_state', 'qcom_pas_check_boot_state'),
    'drivers/soc/qcom/smp2p.c': ('qcom_smp2p_boot_state', 'smp2p_irq_get_irqchip_state'),
}


def extract_function(source, name):
    match = re.search(r'^(?:static )?(?:int|void|irqreturn_t) ' + name +
                      r'\([^;]*?\)\n\{.*?^\}', source, re.M | re.S)
    if not match:
        raise AssertionError(f'Complete function missing from patch: {name}')
    return match.group(0)


def functions_from_patch():
    # Include context, so these are postimage functions, not fabricated models.
    sources = ['\n'.join(line[1:] for line in patch.read_text().splitlines()
                         if line.startswith((' ', '+')) and not line.startswith('+++'))
               for patch in (PATCH, WAIT_PATCH)]
    result = {}
    for path, names in FUNCTIONS.items():
        for name in names:
            for source in reversed(sources):
                if re.search(r'^(?:static )?(?:int|void|irqreturn_t) ' + name + r'\(', source, re.M):
                    result[path, name] = extract_function(source, name)
                    break
            else:
                raise AssertionError('Missing final function: ' + name)
    return result


class AdspBootDiagnosticsTests(unittest.TestCase):
    def test_probe_propagates_failure_to_existing_unwind(self):
        patch = PATCH.read_text()
        self.assertIn('+int qcom_q6v5_read_smp2p_state(struct qcom_q6v5 *q6v5);', patch)
        self.assertIn('+\tret = qcom_pas_check_boot_state(pas);\n+\tif (ret)\n \t\tgoto deinit_q6v5;', patch)
        self.assertIn('+\tsmp2p->boot_diagnostics = of_machine_is_compatible("huawei,gaokun3");', patch)
        self.assertIn('+\t\tqcom_smp2p_boot_state(entry, "notify", val);', patch)
        additions = '\n'.join(line for line in patch.splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        for unwanted in ('+\t\tret = 0;', 'schedule_delayed_work', 'msleep(', '-EPROBE_DEFER'):
            self.assertNotIn(unwanted, additions)

    def test_wait_stays_in_probe_context_and_has_a_fixed_budget(self):
        patch = WAIT_PATCH.read_text()
        additions = '\n'.join(line[1:] for line in patch.splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        self.assertIn('#define QCOM_PAS_SMP2P_WAIT_MS\t\t100', additions)
        self.assertIn('#include <linux/ktime.h>', additions)
        wait = functions_from_patch()['drivers/remoteproc/qcom_q6v5_pas.c',
                                      'qcom_pas_read_boot_state']
        self.assertIn('ret != -ENODEV || pas->rproc->ops->start', wait)
        self.assertIn('usleep_range(5000, 10000)', wait)
        self.assertEqual(wait.count('deadline ='), 1)
        self.assertIn('ret == -ENODEV && ktime_before(ktime_get(), deadline)', wait)
        for forbidden in ('RPROC_DETACHED', 'rproc_boot(', 'schedule_delayed_work', '-EPROBE_DEFER'):
            self.assertNotIn(forbidden, additions)
        self.assertNotIn('drivers/soc/qcom/smp2p.c', patch)

    @unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
    def test_read_errors_levels_probe_returns_and_diagnostics(self):
        functions = functions_from_patch()
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define RPROC_OFFLINE 0
#define RPROC_DETACHED 5
#define BIT(n) (1UL << (n))
#define READ_ONCE(v) (v)
#define IRQ_HANDLED 1
#define QCOM_PAS_SMP2P_WAIT_MS 100
typedef long long ktime_t;
static ktime_t fake_us, mapping_ready_us;
static unsigned sleep_calls, clock_reads;
static bool oversleep;
static ktime_t ktime_get(void) { ++clock_reads; return fake_us; }
static ktime_t ktime_add_ms(ktime_t t, unsigned ms) { return t + ms * 1000; }
static bool ktime_before(ktime_t a, ktime_t b) { return a < b; }
static long long ktime_us_delta(ktime_t a, ktime_t b) { return a - b; }
static void usleep_range(unsigned low, unsigned high)
{
    assert(low == 5000 && high == 10000);
    ++sleep_calls;
    fake_us += oversleep ? 200000 : low;
}
typedef int irqreturn_t;
typedef uint32_t u32;
enum irqchip_irq_state { IRQCHIP_STATE_LINE_LEVEL = 3 };
static char messages[8192];
static unsigned message_count;
static void log_message(void *dev, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void log_message(void *dev, const char *fmt, ...)
{
    (void)dev;
    va_list ap;
    va_start(ap, fmt);
    size_t used = strlen(messages);
    int n = vsnprintf(messages + used, sizeof(messages) - used, fmt, ap);
    assert(n >= 0 && (size_t)n < sizeof(messages) - used);
    va_end(ap);
    ++message_count;
}
#define dev_info log_message
#define dev_warn log_message
#define dev_err log_message
struct rproc_ops { void (*start)(void); };
struct rproc { unsigned state; struct rproc_ops *ops; };
struct qcom_q6v5 {
    void *dev;
    struct rproc *rproc;
    bool running;
    unsigned start_done;
    int handover_irq, ready_irq, fatal_irq, stop_irq;
};
struct qcom_pas { void *dev; struct rproc *rproc; struct qcom_q6v5 q6v5; };
static bool levels[4];
static int errors[4], reads;
static bool completion_done(unsigned *c) { return *c != 0; }
static void complete(unsigned *c) { ++*c; }
static int irq_get_irqchip_state(int irq, int kind, bool *level)
{
    assert(irq >= 0 && irq < 4 && kind == IRQCHIP_STATE_LINE_LEVEL);
    ++reads;
    if (fake_us < mapping_ready_us) return -ENODEV;
    /* A failing provider's output is untrusted, even if it writes true. */
    *level = errors[irq] ? true : levels[irq];
    return errors[irq];
}
struct qcom_smp2p { void *dev; bool boot_diagnostics; };
struct smp2p_entry {
    struct qcom_smp2p *smp2p;
    const char *name;
    u32 *value, last_value;
    unsigned long irq_enabled[1];
};
struct irq_data { struct smp2p_entry *entry; unsigned long hwirq; };
static struct smp2p_entry *irq_data_get_irq_chip_data(struct irq_data *d) { return d->entry; }
static unsigned long irqd_to_hwirq(struct irq_data *d) { return d->hwirq; }
static unsigned mmio_reads;
static u32 readl(u32 *p) { ++mmio_reads; return *p; }
static void reset_capable_start(void) { assert(!"tests must never start hardware"); }
''' + '\n\n'.join(functions.values()) + r'''
int main(void)
{
    struct rproc_ops ops = {0};
    struct rproc r = {.ops = &ops};
    struct qcom_pas pas = {.rproc = &r,
        .q6v5 = {.rproc = &r, .handover_irq = 0, .ready_irq = 1, .fatal_irq = 2, .stop_irq = 3}};
    struct qcom_q6v5 *q = &pas.q6v5;

    /* All 16 valid level combinations, with and without a reset operation. */
    for (unsigned reset = 0; reset < 2; ++reset) {
        ops.start = reset ? reset_capable_start : NULL;
        for (unsigned mask = 0; mask < 16; ++mask) {
            memset(messages, 0, sizeof(messages)); reads = sleep_calls = clock_reads = 0;
            r.state = RPROC_OFFLINE; q->running = false;
            for (unsigned j = 0; j < 4; ++j) levels[j] = !!(mask & BIT(j));
            int ret = qcom_pas_check_boot_state(&pas);
            bool attachable = mask == 3;
            assert(reads == 4 && sleep_calls == 0 && clock_reads == 0);
            assert(ret == ((reset || attachable) ? 0 : -ENODEV));
            assert(r.state == (attachable ? RPROC_DETACHED : RPROC_OFFLINE));
            assert(q->running == attachable);
            if (!reset && !attachable) {
                assert(strstr(messages, "EL2 attach rejected:"));
                assert(strstr(messages, "smp2p_ret=0 probe_ret=-19"));
            }
        }
    }

    /* Every error position, including fatal/stop read failures: never attach. */
    const int errnos[] = {-ENODEV, -EINVAL, -EIO, -517};
    for (unsigned reset = 0; reset < 2; ++reset) {
        ops.start = reset ? reset_capable_start : NULL;
        for (unsigned pos = 0; pos < 4; ++pos) {
            for (unsigned e = 0; e < sizeof(errnos)/sizeof(errnos[0]); ++e) {
                memset(messages, 0, sizeof(messages)); reads = sleep_calls = 0;
                memset(errors, 0, sizeof(errors)); errors[pos] = errnos[e];
                levels[0] = levels[1] = true; levels[2] = levels[3] = false;
                r.state = RPROC_OFFLINE; q->running = false;
                int ret = qcom_pas_check_boot_state(&pas);
                assert(ret == (reset ? 0 : errnos[e]));
                unsigned expected_sleeps = !reset && errnos[e] == -ENODEV ? 20 : 0;
                assert(sleep_calls == expected_sleeps && reads == 4 * (int)(expected_sleeps + 1));
                assert(!q->running && r.state == RPROC_OFFLINE);
                if (expected_sleeps) assert(strstr(messages, "timed_out=1"));
                char expected[32]; snprintf(expected, sizeof(expected), "=-1/%d", errnos[e]);
                assert(strstr(messages, expected));
                if (reset) assert(strstr(messages, "reset-capable boot retained"));
            }
        }
    }
    errors[0] = -EINVAL; errors[1] = -ENODEV; errors[2] = -EIO; errors[3] = -EIO;
    assert(qcom_q6v5_read_smp2p_state(q) == -EINVAL); /* First read error wins. */
    memset(errors, 0, sizeof(errors));
    memset(messages, 0, sizeof(messages));
    assert(q6v5_ready_interrupt(0, q) == IRQ_HANDLED);
    assert(q->start_done == 1 && strstr(messages, "SMP2P ready IRQ:"));
    assert(qcom_q6v5_read_smp2p_state(q) == 0);
    assert(strstr(messages, "ready_seen=1"));

    /* Reproduce the actual race: mapping appears after the initial read.
     * There is no consumer ready edge/completion in this model. */
    ops.start = NULL;
    for (unsigned delay = 5000; delay <= 100000; delay += 5000) {
        memset(messages, 0, sizeof(messages)); reads = sleep_calls = 0;
        r.state = RPROC_OFFLINE; q->running = false; q->start_done = 0;
        levels[0] = levels[1] = true; levels[2] = levels[3] = false;
        mapping_ready_us = fake_us + delay;
        assert(qcom_pas_check_boot_state(&pas) == 0);
        assert(sleep_calls == delay / 5000 && reads == 4 * (int)(sleep_calls + 1));
        assert(q->running && r.state == RPROC_DETACHED && !q->start_done);
        assert(strstr(messages, "read_ret=0 timed_out=0"));
    }
    /* Mapping availability is not permission to ignore low/fatal/stop levels. */
    for (unsigned mask = 0; mask < 16; ++mask) {
        memset(messages, 0, sizeof(messages)); sleep_calls = 0;
        r.state = RPROC_OFFLINE; q->running = false;
        for (unsigned j = 0; j < 4; ++j) levels[j] = !!(mask & BIT(j));
        mapping_ready_us = fake_us + 5000;
        assert(qcom_pas_check_boot_state(&pas) == (mask == 3 ? 0 : -ENODEV));
        assert(sleep_calls == 1 && q->running == (mask == 3));
    }
    memset(messages, 0, sizeof(messages)); sleep_calls = 0;
    r.state = RPROC_OFFLINE; q->running = false;
    levels[0] = levels[1] = true; levels[2] = levels[3] = false;
    mapping_ready_us = fake_us + 5000; errors[2] = -EIO;
    assert(qcom_pas_check_boot_state(&pas) == -EIO && sleep_calls == 1 && !q->running);
    assert(strstr(messages, "read_ret=-5 timed_out=0"));
    memset(errors, 0, sizeof(errors));
    /* A delayed scheduler wakeup must not start another timeout budget. */
    memset(messages, 0, sizeof(messages)); sleep_calls = 0; oversleep = true;
    mapping_ready_us = fake_us + 1000000;
    assert(qcom_pas_check_boot_state(&pas) == -ENODEV && sleep_calls == 1);
    assert(strstr(messages, "elapsed_us=200000") && strstr(messages, "timed_out=1"));
    oversleep = false; mapping_ready_us = 0;

    /* Lower-level diagnostics retain raw samples and observe a released consumer. */
    memset(messages, 0, sizeof(messages)); message_count = 0;
    struct qcom_smp2p smp = {0};
    u32 value = 6;
    struct smp2p_entry entry = {.smp2p = &smp, .name = "slave-kernel", .value = &value};
    struct irq_data data = {.entry = &entry, .hwirq = 1};
    bool level = false;
    assert(smp2p_irq_get_irqchip_state(&data, IRQCHIP_STATE_LINE_LEVEL, &level) == 0);
    assert(level && mmio_reads == 1 && message_count == 0); /* Other boards stay quiet. */
    smp.boot_diagnostics = true;
    assert(smp2p_irq_get_irqchip_state(&data, IRQCHIP_STATE_LINE_LEVEL, &level) == 0);
    assert(strstr(messages, "sample=0x6 level=1 ret=0"));
    entry.value = NULL; level = true;
    assert(smp2p_irq_get_irqchip_state(&data, IRQCHIP_STATE_LINE_LEVEL, &level) == -ENODEV);
    assert(level && mmio_reads == 2); /* No memory access and no fabricated low level. */
    assert(strstr(messages, "unmapped ret=-19"));
    unsigned before = message_count;
    assert(smp2p_irq_get_irqchip_state(&data, (enum irqchip_irq_state)99, &level) == -EINVAL);
    assert(message_count == before && mmio_reads == 2);
    qcom_smp2p_boot_state(&entry, "notify", 6);
    assert(strstr(messages, "notify: entry=slave-kernel sample=0x6"));
    assert(strstr(messages, "enabled=0")); /* Late notification logged with consumer IRQs disabled. */
    puts("PASS: 64 level/error cases, 20 delayed mappings, 16 post-mapping states, error/timeout boundaries and diagnostics");
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='gaokun-adsp-native-') as directory:
            path = Path(directory) / 'test.c'
            binary = Path(directory) / 'test'
            path.write_text(source)
            result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                     '-Wno-unused-parameter', str(path), '-o', str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
