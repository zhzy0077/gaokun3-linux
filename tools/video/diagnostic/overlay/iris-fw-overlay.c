// SPDX-License-Identifier: GPL-2.0-only
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>

static int overlay_id;

static int __init iris_overlay_init(void)
{
	const struct firmware *fw;
	int ret;

	if (!of_machine_is_compatible("huawei,gaokun3"))
		return -ENODEV;
	ret = request_firmware_direct(&fw, "gaokun-iris-fw-test.dtbo", NULL);
	if (ret)
		return ret;
	ret = of_overlay_fdt_apply(fw->data, fw->size, &overlay_id, NULL);
	release_firmware(fw);
	return ret;
}

static void __exit iris_overlay_exit(void)
{
	int ret = of_overlay_remove(&overlay_id);

	if (ret)
		pr_err("iris firmware diagnostic overlay removal failed: %d\n", ret);
}

module_init(iris_overlay_init);
module_exit(iris_overlay_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary Gaokun Iris firmware DT overlay loader");
