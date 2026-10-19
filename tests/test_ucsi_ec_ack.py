"""Compile the real EC ACK encoder with UBSAN; no hardware access."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'drivers/gaokun-ec/huawei-gaokun-ec.c'


@unittest.skipUnless(shutil.which('cc'), 'native C compiler required')
class EcAckTests(unittest.TestCase):
    def test_real_ack_encoder_and_invalid_ports(self):
        source = SOURCE.read_text()
        encoder = re.search(r'int gaokun_ec_ucsi_pan_ack\(.*?\n}', source, re.S).group(0)
        mkreq = source[source.index('#define MKREQ('):source.index('#define MKRESP(')]
        refill = re.search(r'static inline void refill_req_byte\(.*?\n}', source, re.S).group(0)
        code = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
typedef uint8_t u8;
#define GAOKUN_UCSI_NO_PORT_UPDATE (-1)
#define REQ_HDR_SIZE 3
#define UCSI_REG_WRITE 0xd2
struct gaokun_ec { int unused; };
static int writes, write_result;
static u8 payload;
static int gaokun_ec_write(struct gaokun_ec *ec, const u8 *req)
{
    (void)ec;
    assert(req[0] == 3 && req[1] == UCSI_REG_WRITE && req[2] == 1);
    payload = req[3];
    writes++;
    return write_result;
}
''' + mkreq + refill + encoder + r'''
int main(void)
{
    struct gaokun_ec ec = {0};
    assert(gaokun_ec_ucsi_pan_ack(&ec, -1) == 0);
    assert(writes == 1 && payload == 0);
    for (int port = 0; port < 8; port++) {
        assert(gaokun_ec_ucsi_pan_ack(&ec, port) == 0);
        assert(payload == (1U << port));
    }
    int before = writes;
    int invalid[] = {INT_MIN, -2, 8, 31, 32, INT_MAX};
    for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); i++)
        assert(gaokun_ec_ucsi_pan_ack(&ec, invalid[i]) == -EINVAL);
    assert(writes == before);
    write_result = -EIO;
    assert(gaokun_ec_ucsi_pan_ack(&ec, 0) == -EIO);
    assert(gaokun_ec_ucsi_pan_ack(&ec, -1) == -EIO);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ack.c'
            binary = Path(directory) / 'ack'
            path.write_text(code)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
                            str(path), '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
