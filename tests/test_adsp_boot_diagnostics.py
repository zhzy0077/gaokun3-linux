"""Native tests of the actual functions shipped in EL2 patch 0023."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/el2/0023-remoteproc-qcom-report-attach-errors-and-SMP2P-state.patch'
FUNCTIONS = {
    'drivers/remoteproc/qcom_q6v5.c': ('qcom_q6v5_read_smp2p_state', 'q6v5_ready_interrupt'),
    'drivers/remoteproc/qcom_q6v5_pas.c': ('qcom_pas_check_boot_state',),
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
    postimage = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith((' ', '+')) and not line.startswith('+++'))
    return {(path, name): extract_function(postimage, name)
            for path, names in FUNCTIONS.items() for name in names}


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
            memset(messages, 0, sizeof(messages)); reads = 0;
            r.state = RPROC_OFFLINE; q->running = false;
            for (unsigned j = 0; j < 4; ++j) levels[j] = !!(mask & BIT(j));
            int ret = qcom_pas_check_boot_state(&pas);
            bool attachable = mask == 3;
            assert(reads == 4);
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
                memset(messages, 0, sizeof(messages)); reads = 0;
                memset(errors, 0, sizeof(errors)); errors[pos] = errnos[e];
                levels[0] = levels[1] = true; levels[2] = levels[3] = false;
                r.state = RPROC_OFFLINE; q->running = false;
                int ret = qcom_pas_check_boot_state(&pas);
                assert(ret == (reset ? 0 : errnos[e]));
                assert(reads == 4 && !q->running && r.state == RPROC_OFFLINE);
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
    puts("PASS: 32 level cases, 32 error cases, error precedence, ready IRQ and SMP2P diagnostics");
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
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
