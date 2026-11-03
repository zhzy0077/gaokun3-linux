/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Experimental Gaokun3 FTE7001 match-on-chip driver, one template slot. */
#define FP_COMPONENT "fte7001"
#include "drivers_api.h"
#include <signal.h>

typedef struct _FpDeviceFte7001 {
  FpDevice parent;
  GSubprocess *child;
  GDataInputStream *stream;
  gint result;
  gboolean committed, identity, deleted;
} FpDeviceFte7001;
typedef FpDeviceClass FpDeviceFte7001Class;
GType fpi_device_fte7001_get_type (void);
G_DEFINE_TYPE (FpDeviceFte7001, fpi_device_fte7001, FP_TYPE_DEVICE)

static const FpIdEntry id_table[] = {
  { .virtual_envvar = "FP_FTE7001_QTEE" }, { .virtual_envvar = NULL }
};

static void read_line (FpDeviceFte7001 *self);

static void
finish (GObject *source, GAsyncResult *res, gpointer data)
{
  FpDevice *dev = data;
  FpDeviceFte7001 *self = (FpDeviceFte7001 *) dev;
  g_autoptr(GError) error = NULL;
  gboolean waited = g_subprocess_wait_finish (self->child, res, &error);
  FpiDeviceAction action = fpi_device_get_current_action (dev);
  (void) source;
  if (fpi_device_action_is_cancelled (dev))
    { g_clear_error (&error); error = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_CANCELLED, "Fingerprint operation cancelled"); }
  else if (!waited || !g_subprocess_get_if_exited (self->child))
    { if (!error) error = fpi_device_error_new (FP_DEVICE_ERROR_GENERAL); }
  else if (action == FPI_DEVICE_ACTION_VERIFY && self->result != G_MININT)
    {
      if (self->result == 0 && !self->identity)
        error = fpi_device_error_new_msg (FP_DEVICE_ERROR_DATA_INVALID, "Template identity mismatch");
    }
  else if (!g_subprocess_get_successful (self->child))
    error = fpi_device_error_new_msg (FP_DEVICE_ERROR_GENERAL, "Fingerprint helper failed");
  g_clear_object (&self->stream);
  g_clear_object (&self->child);
  fpi_device_report_finger_status (dev, FP_FINGER_STATUS_NONE);
  switch (action)
    {
    case FPI_DEVICE_ACTION_OPEN:
      fpi_device_open_complete (dev, g_steal_pointer (&error));
      break;
    case FPI_DEVICE_ACTION_ENROLL:
      {
        FpPrint *print = NULL;
        if (!error && !self->committed) error = fpi_device_error_new (FP_DEVICE_ERROR_GENERAL);
        if (!error)
          {
            fpi_device_get_enroll_data (dev, &print);
            fpi_print_set_type (print, FPI_PRINT_RAW);
            fpi_print_set_device_stored (print, TRUE);
            g_object_set (print, "fpi-data", g_variant_new_string ("gaokun3-linux-experiment"), NULL);
          }
        fpi_device_enroll_complete (dev, print ? g_object_ref (print) : NULL, g_steal_pointer (&error));
        break;
      }
    case FPI_DEVICE_ACTION_VERIFY:
      if (!error && self->result == G_MININT) error = fpi_device_error_new (FP_DEVICE_ERROR_GENERAL);
      if (!error) fpi_device_verify_report (dev, self->result == 0 ? FPI_MATCH_SUCCESS : FPI_MATCH_FAIL, NULL, NULL);
      fpi_device_verify_complete (dev, g_steal_pointer (&error));
      break;
    case FPI_DEVICE_ACTION_DELETE:
      if (!error && !self->deleted) error = fpi_device_error_new (FP_DEVICE_ERROR_GENERAL);
      fpi_device_delete_complete (dev, g_steal_pointer (&error));
      break;
    default:
      fpi_device_action_error (dev, error ? g_steal_pointer (&error) : fpi_device_error_new (FP_DEVICE_ERROR_GENERAL));
    }
  g_object_unref (dev);
}

static void
line_ready (GObject *source, GAsyncResult *res, gpointer data)
{
  FpDeviceFte7001 *self = data;
  FpDevice *dev = (FpDevice *) self;
  g_autoptr(GError) error = NULL;
  g_autofree gchar *line = g_data_input_stream_read_line_finish (self->stream, res, NULL, &error);
  (void) source;
  if (!line)
    {
      if (error) g_subprocess_send_signal (self->child, SIGTERM);
      g_subprocess_wait_async (self->child, NULL, finish, dev);
      return;
    }
  if (g_str_has_prefix (line, "enrollment_progress="))
    fpi_device_enroll_progress (dev, (gint) g_ascii_strtoll (line + 20, NULL, 10), NULL, NULL);
  else if (g_str_has_prefix (line, "verify_result="))
    self->result = (gint) g_ascii_strtoll (line + 14, NULL, 10);
  else if (g_str_equal (line, "loaded_template_count_after_commit=1")) self->committed = TRUE;
  else if (g_str_equal (line, "matched_experiment_identity=1")) self->identity = TRUE;
  else if (g_str_equal (line, "template_count_after_delete=0")) self->deleted = TRUE;
  else if (g_str_equal (line, "await_finger=on")) fpi_device_report_finger_status (dev, FP_FINGER_STATUS_NEEDED);
  else if (g_str_equal (line, "await_finger=off")) fpi_device_report_finger_status (dev, FP_FINGER_STATUS_PRESENT);
  read_line (self);
}

static void
read_line (FpDeviceFte7001 *self)
{
  g_data_input_stream_read_line_async (self->stream, G_PRIORITY_DEFAULT, NULL, line_ready, self);
}

static void
start (FpDevice *dev, const char *mode)
{
  FpDeviceFte7001 *self = (FpDeviceFte7001 *) dev;
  g_autoptr(GError) error = NULL;
  self->result = G_MININT;
  self->committed = self->identity = self->deleted = FALSE;
  self->child = g_subprocess_new (G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_MERGE,
                                 &error, "/opt/gaokun3-fingerprint/fingerprint-helper", mode, NULL);
  if (!self->child) { fpi_device_action_error (dev, g_steal_pointer (&error)); return; }
  self->stream = g_data_input_stream_new (g_subprocess_get_stdout_pipe (self->child));
  g_object_ref (dev);
  read_line (self);
}

static gboolean
valid_print (FpPrint *print)
{
  g_autoptr(GVariant) data = NULL;
  g_object_get (print, "fpi-data", &data, NULL);
  return data && g_variant_is_of_type (data, G_VARIANT_TYPE_STRING) &&
         g_str_equal (g_variant_get_string (data, NULL), "gaokun3-linux-experiment");
}

static void dev_enroll (FpDevice *dev) { start (dev, "listener-enroll-series-wait"); }
static void dev_verify (FpDevice *dev) {
  FpPrint *print;
  fpi_device_get_verify_data (dev, &print);
  if (!valid_print (print)) { fpi_device_action_error (dev, fpi_device_error_new (FP_DEVICE_ERROR_DATA_INVALID)); return; }
  start (dev, "listener-verify-wait");
}
static void dev_delete (FpDevice *dev) {
  FpPrint *print;
  fpi_device_get_delete_data (dev, &print);
  if (!valid_print (print)) { fpi_device_action_error (dev, fpi_device_error_new (FP_DEVICE_ERROR_DATA_INVALID)); return; }
  start (dev, "listener-delete-template");
}
static void dev_cancel (FpDevice *dev) {
  FpDeviceFte7001 *self = (FpDeviceFte7001 *) dev;
  if (self->child) g_subprocess_send_signal (self->child, SIGTERM);
}
static void dev_open (FpDevice *dev) { start (dev, "listener-template-count"); }
static void dev_close (FpDevice *dev) { fpi_device_close_complete (dev, NULL); }

static void
dev_probe (FpDevice *dev)
{
  g_autofree gchar *board = NULL, *machine = NULL;
  gsize size = 0;
  if (!g_file_get_contents ("/sys/firmware/devicetree/base/compatible", &board, &size, NULL) ||
      !g_strstr_len (board, size, "huawei,gaokun3") ||
      !g_file_test ("/dev/tee0", G_FILE_TEST_EXISTS) ||
      !g_file_get_contents ("/etc/machine-id", &machine, NULL, NULL))
    { fpi_device_probe_complete (dev, NULL, NULL, fpi_device_error_new (FP_DEVICE_ERROR_NOT_SUPPORTED)); return; }
  g_strstrip (machine);
  fpi_device_probe_complete (dev, machine, "Gaokun3 FTE7001", NULL);
}

static void fpi_device_fte7001_init (FpDeviceFte7001 *self) { (void) self; }
static void
fpi_device_fte7001_class_init (FpDeviceFte7001Class *klass)
{
  klass->id = "fte7001";
  klass->full_name = "Gaokun3 FTE7001";
  klass->type = FP_DEVICE_TYPE_VIRTUAL;
  klass->id_table = id_table;
  klass->nr_enroll_stages = 24;
  klass->scan_type = FP_SCAN_TYPE_PRESS;
  klass->temp_hot_seconds = -1;
  klass->probe = dev_probe;
  klass->open = dev_open;
  klass->close = dev_close;
  klass->enroll = dev_enroll;
  klass->verify = dev_verify;
  klass->delete = dev_delete;
  klass->cancel = dev_cancel;
  fpi_device_class_auto_initialize_features (klass);
}
