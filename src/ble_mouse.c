#include "ble_mouse.h"
#include "esp_log.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "host/ble_store.h"
#include "store/config/ble_store_config.h"

// Forward declaration of NimBLE's config store init (omitted from public headers)
void ble_store_config_init(void);

static const char *TAG = "BLE_MOUSE";
static uint16_t conn_handle;
static bool ble_connected = false;
static uint16_t report_handle_mouse = 0;
static uint16_t report_handle_keyboard = 0;
static uint16_t report_handle_media = 0;

static int active_device_id = 1;
static char device_name[32] = "AirMouse_BLE_V2";

static const uint8_t hid_report_map[] = {
    // Mouse Report (ID 1)
    0x05, 0x01,       // USAGE_PAGE (Generic Desktop)
    0x09, 0x02,       // USAGE (Mouse)
    0xA1, 0x01,       // COLLECTION (Application)
    0x85, 0x01,       //   REPORT_ID (1)
    0x09, 0x01,       //   USAGE (Pointer)
    0xA1, 0x00,       //   COLLECTION (Physical)
    0x05, 0x09,       //     USAGE_PAGE (Button)
    0x19, 0x01,       //     USAGE_MINIMUM (Button 1)
    0x29, 0x05,       //     USAGE_MAXIMUM (Button 5)
    0x15, 0x00,       //     LOGICAL_MINIMUM (0)
    0x25, 0x01,       //     LOGICAL_MAXIMUM (1)
    0x95, 0x05,       //     REPORT_COUNT (5)
    0x75, 0x01,       //     REPORT_SIZE (1)
    0x81, 0x02,       //     INPUT (Data,Var,Abs)
    0x95, 0x01,       //     REPORT_COUNT (1)
    0x75, 0x03,       //     REPORT_SIZE (3)
    0x81, 0x03,       //     INPUT (Cnst,Var,Abs)
    0x05, 0x01,       //     USAGE_PAGE (Generic Desktop)
    0x09, 0x30,       //     USAGE (X)
    0x09, 0x31,       //     USAGE (Y)
    0x15, 0x81,       //     LOGICAL_MINIMUM (-127)
    0x25, 0x7F,       //     LOGICAL_MAXIMUM (127)
    0x75, 0x08,       //     REPORT_SIZE (8)
    0x95, 0x02,       //     REPORT_COUNT (2)
    0x81, 0x06,       //     INPUT (Data,Var,Rel)
    0x09, 0x38,       //     USAGE (Wheel)
    0x15, 0x81,       //     LOGICAL_MINIMUM (-127)
    0x25, 0x7F,       //     LOGICAL_MAXIMUM (127)
    0x75, 0x08,       //     REPORT_SIZE (8)
    0x95, 0x01,       //     REPORT_COUNT (1)
    0x81, 0x06,       //     INPUT (Data,Var,Rel)
    0xC0,             //   END_COLLECTION
    0xC0,             // END_COLLECTION

    // Keyboard Report (ID 2)
    0x05, 0x01,       // Usage Page (Generic Desktop)
    0x09, 0x06,       // Usage (Keyboard)
    0xA1, 0x01,       // Collection (Application)
    0x85, 0x02,       //   Report ID (2)
    0x05, 0x07,       //   Usage Page (Key Codes)
    0x19, 0xE0,       //   Usage Minimum (224)
    0x29, 0xE7,       //   Usage Maximum (231)
    0x15, 0x00,       //   Logical Minimum (0)
    0x25, 0x01,       //   Logical Maximum (1)
    0x75, 0x01,       //   Report Size (1)
    0x95, 0x08,       //   Report Count (8)
    0x81, 0x02,       //   Input (Data, Variable, Absolute)
    0x95, 0x01,       //   Report Count (1)
    0x75, 0x08,       //   Report Size (8)
    0x81, 0x01,       //   Input (Constant) reserved byte
    0x95, 0x06,       //   Report Count (6)
    0x75, 0x08,       //   Report Size (8)
    0x15, 0x00,       //   Logical Minimum (0)
    0x25, 0x65,       //   Logical Maximum (101)
    0x05, 0x07,       //   Usage Page (Key codes)
    0x19, 0x00,       //   Usage Minimum (0)
    0x29, 0x65,       //   Usage Maximum (101)
    0x81, 0x00,       //   Input (Data, Array) Key array (6 bytes)
    0xC0,             // End Collection

    // Consumer Report (ID 3)
    0x05, 0x0C,       // Usage Page (Consumer)
    0x09, 0x01,       // Usage (Consumer Control)
    0xA1, 0x01,       // Collection (Application)
    0x85, 0x03,       //   Report ID (3)
    0x15, 0x00,       //   Logical Minimum (0)
    0x25, 0x01,       //   Logical Maximum (1)
    0x75, 0x01,       //   Report Size (1)
    0x95, 0x08,       //   Report Count (8)
    0x09, 0xE9,       //   Usage (Volume Increment)
    0x09, 0xEA,       //   Usage (Volume Decrement)
    0x09, 0xE2,       //   Usage (Mute)
    0x09, 0xCD,       //   Usage (Play/Pause)
    0x09, 0xB5,       //   Usage (Scan Next Track)
    0x09, 0xB6,       //   Usage (Scan Previous Track)
    0x0A, 0x24, 0x02, //   Usage (AC Back)
    0x0A, 0x23, 0x02, //   Usage (AC Home)
    0x81, 0x02,       //   Input (Data, Variable, Absolute)
    0xC0              // End Collection
};

// GATT read callbacks
static int gatt_read_char(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    const char *data = (const char *)arg;
    int rc = os_mbuf_append(ctxt->om, data, strlen(data));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_report_map(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    int rc = os_mbuf_append(ctxt->om, hid_report_map, sizeof(hid_report_map));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_hid_info(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t hid_info[] = {0x11, 0x01, 0x00, 0x03}; // bcdHID = 1.11, bCountryCode = 0, Flags = 3
    int rc = os_mbuf_append(ctxt->om, hid_info, sizeof(hid_info));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_pnp_id(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t pnp_id[] = {0x01, 0x0d, 0x0d, 0x12, 0x34, 0x56, 0x78}; // Vendor ID Source = 1, Vendor ID = 0x0D0D, Product ID = 0x1234, Product Version = 0x5678
    int rc = os_mbuf_append(ctxt->om, pnp_id, sizeof(pnp_id));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_report_ref_mouse(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t report_ref[] = {0x01, 0x01}; // Report ID = 1, Report Type = 1 (Input)
    int rc = os_mbuf_append(ctxt->om, report_ref, sizeof(report_ref));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_report_ref_keyboard(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t report_ref[] = {0x02, 0x01}; // Report ID = 2, Report Type = 1 (Input)
    int rc = os_mbuf_append(ctxt->om, report_ref, sizeof(report_ref));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_report_ref_media(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t report_ref[] = {0x03, 0x01}; // Report ID = 3, Report Type = 1 (Input)
    int rc = os_mbuf_append(ctxt->om, report_ref, sizeof(report_ref));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_access_report_mouse(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t temp[4] = {0, 0, 0, 0};
    int rc = os_mbuf_append(ctxt->om, temp, sizeof(temp));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_access_report_keyboard(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t temp[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    int rc = os_mbuf_append(ctxt->om, temp, sizeof(temp));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_access_report_media(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t temp[1] = {0};
    int rc = os_mbuf_append(ctxt->om, temp, sizeof(temp));
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int gatt_read_battery(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t batt = 100;
    int rc = os_mbuf_append(ctxt->om, &batt, 1);
    return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static const struct ble_gatt_svc_def ble_mouse_svcs[] = {
    {
        // Device Information Service
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0x180A),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0x2A29), // Manufacturer Name
                .access_cb = gatt_read_char,
                .arg = "S3 HID",
                .flags = BLE_GATT_CHR_F_READ,
            },
            {
                .uuid = BLE_UUID16_DECLARE(0x2A50), // PnP ID
                .access_cb = gatt_read_pnp_id,
                .flags = BLE_GATT_CHR_F_READ,
            },
            {0}
        }
    },
    {
        // Human Interface Device
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0x1812),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0x2A4A), // HID Information
                .access_cb = gatt_read_hid_info,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC,
            },
            {
                .uuid = BLE_UUID16_DECLARE(0x2A4B), // Report Map
                .access_cb = gatt_read_report_map,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC,
            },
            {
                .uuid = BLE_UUID16_DECLARE(0x2A4C), // HID Control Point
                .access_cb = gatt_read_hid_info,
                .flags = BLE_GATT_CHR_F_WRITE_NO_RSP | BLE_GATT_CHR_F_WRITE_ENC,
            },
            {
                // Mouse Report
                .uuid = BLE_UUID16_DECLARE(0x2A4D),
                .access_cb = gatt_access_report_mouse,
                .val_handle = &report_handle_mouse,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_NOTIFY,
                .descriptors = (struct ble_gatt_dsc_def[]) {
                    {
                        .uuid = BLE_UUID16_DECLARE(0x2908),
                        .att_flags = BLE_ATT_F_READ,
                        .access_cb = gatt_read_report_ref_mouse,
                    },
                    {0}
                }
            },
            {
                // Keyboard Report
                .uuid = BLE_UUID16_DECLARE(0x2A4D),
                .access_cb = gatt_access_report_keyboard,
                .val_handle = &report_handle_keyboard,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_NOTIFY,
                .descriptors = (struct ble_gatt_dsc_def[]) {
                    {
                        .uuid = BLE_UUID16_DECLARE(0x2908),
                        .att_flags = BLE_ATT_F_READ,
                        .access_cb = gatt_read_report_ref_keyboard,
                    },
                    {0}
                }
            },
            {
                // Media Report
                .uuid = BLE_UUID16_DECLARE(0x2A4D),
                .access_cb = gatt_access_report_media,
                .val_handle = &report_handle_media,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_NOTIFY,
                .descriptors = (struct ble_gatt_dsc_def[]) {
                    {
                        .uuid = BLE_UUID16_DECLARE(0x2908),
                        .att_flags = BLE_ATT_F_READ,
                        .access_cb = gatt_read_report_ref_media,
                    },
                    {0}
                }
            },
            {
                .uuid = BLE_UUID16_DECLARE(0x2A4E), // Protocol Mode
                .access_cb = gatt_read_hid_info,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_WRITE_NO_RSP | BLE_GATT_CHR_F_WRITE_ENC,
            },
            {0}
        }
    },
    {
        // Battery Service
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0x180F),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0x2A19),
                .access_cb = gatt_read_battery,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_READ_ENC,
            },
            {0}
        }
    },
    {0}
};

static int ble_mouse_gap_event(struct ble_gap_event *event, void *arg);

static void ble_mouse_advertise(void) {
    struct ble_gap_adv_params adv_params;
    struct ble_hs_adv_fields fields;
    int rc;

    memset(&fields, 0, sizeof fields);
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (uint8_t *)device_name;
    fields.name_len = strlen(device_name);
    fields.name_is_complete = 1;
    fields.appearance = 0x03C2; // Explicitly declare as Mouse (0x03C2) for Google TV compatibility
    fields.appearance_is_present = 1;

    static ble_uuid16_t uuids16_list[] = {
        BLE_UUID16_INIT(0x1812) // HID Service UUID (Critical for Google TV discovery)
    };
    fields.uuids16 = uuids16_list;
    fields.num_uuids16 = 1;
    fields.uuids16_is_complete = 1;

    rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "error setting advertisement data; rc=%d", rc);
        return;
    }

    memset(&adv_params, 0, sizeof adv_params);
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    // 200ms intervals give WiFi coex enough airtime slots
    adv_params.itvl_min = BLE_GAP_ADV_ITVL_MS(200);
    adv_params.itvl_max = BLE_GAP_ADV_ITVL_MS(250);
    rc = ble_gap_adv_start(BLE_OWN_ADDR_PUBLIC, NULL, BLE_HS_FOREVER, &adv_params, ble_mouse_gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "error enabling advertisement; rc=%d", rc);
    }
}

static int ble_mouse_gap_event(struct ble_gap_event *event, void *arg) {
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT:
            if (event->connect.status == 0) {
                conn_handle = event->connect.conn_handle;
                ble_connected = true;
                ESP_LOGI(TAG, "Connected!");
            } else {
                ble_mouse_advertise();
            }
            break;

        case BLE_GAP_EVENT_DISCONNECT:
            ble_connected = false;
            ESP_LOGI(TAG, "Disconnected! Advertising again...");
            ble_mouse_advertise();
            break;

        case BLE_GAP_EVENT_ADV_COMPLETE:
            ESP_LOGI(TAG, "ADV Complete reason: %d", event->adv_complete.reason);
            if (event->adv_complete.reason != 0) {
                vTaskDelay(pdMS_TO_TICKS(1000));
            }
            ble_mouse_advertise();
            break;

        case BLE_GAP_EVENT_MTU:
            ESP_LOGI(TAG, "MTU update; conn_handle=%d mtu=%d",
                     event->mtu.conn_handle, event->mtu.value);
            break;

        case BLE_GAP_EVENT_REPEAT_PAIRING: {
            struct ble_gap_conn_desc desc;
            int rc = ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc);
            if (rc == 0) {
                ble_store_util_delete_peer(&desc.peer_id_addr);
            }
            return BLE_GAP_REPEAT_PAIRING_RETRY;
        }
    }
    return 0;
}

void ble_mouse_send_report(int8_t dx, int8_t dy, int8_t wheel, uint8_t buttons) {
    if (!ble_connected) return;
    struct os_mbuf *om = ble_hs_mbuf_from_flat((uint8_t[]){buttons, (uint8_t)dx, (uint8_t)dy, (uint8_t)wheel}, 4);
    if (om) {
        ble_gatts_notify_custom(conn_handle, report_handle_mouse, om);
    }
}

void ble_mouse_send_keyboard(uint8_t modifier, uint8_t key1) {
    if (!ble_connected) return;
    struct os_mbuf *om = ble_hs_mbuf_from_flat((uint8_t[]){modifier, 0, key1, 0, 0, 0, 0, 0}, 8);
    if (om) {
        ble_gatts_notify_custom(conn_handle, report_handle_keyboard, om);
    }
}

// Media keys bitmap:
// Bit 0: Vol Up
// Bit 1: Vol Down
// Bit 2: Mute
// Bit 3: Play/Pause
// Bit 4: Next Track
// Bit 5: Prev Track
void ble_mouse_send_media(uint8_t media_keys) {
    if (!ble_connected) return;
    struct os_mbuf *om = ble_hs_mbuf_from_flat(&media_keys, 1);
    if (om) {
        ble_gatts_notify_custom(conn_handle, report_handle_media, om);
    }
}

bool ble_mouse_is_connected(void) {
    return ble_connected;
}

static void ble_mouse_host_task(void *param) {
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void ble_mouse_init(int device_id) {
    active_device_id = device_id;
    snprintf(device_name, sizeof(device_name), "S3-Air-Mouse-D%d", device_id);

    int rc = nimble_port_init();
    if (rc != 0) return;

    ble_hs_cfg.sync_cb = ble_mouse_advertise;
    ble_hs_cfg.gatts_register_cb = NULL;
    ble_hs_cfg.store_read_cb = ble_store_config_read;
    ble_hs_cfg.store_write_cb = ble_store_config_write;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_NO_IO;
    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_mitm = 0;
    ble_hs_cfg.sm_sc = 1;
    ble_hs_cfg.sm_our_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;

    rc = ble_gatts_count_cfg(ble_mouse_svcs);
    rc = ble_gatts_add_svcs(ble_mouse_svcs);

    ble_svc_gap_device_name_set(device_name);
    ble_svc_gap_device_appearance_set(0x03C2);

    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_store_config_init();

    xTaskCreate(ble_mouse_host_task, "ble_mouse_host", 4096, NULL, 5, NULL);
}
