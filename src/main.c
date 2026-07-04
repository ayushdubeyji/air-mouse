#include <stdio.h>
#include "esp_timer.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "driver/i2c_master.h"
#include "driver/ledc.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "lvgl.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "ble_mouse.h"
#include "mahony.h"
#include <math.h>
#include <stdlib.h>
#include "nvs_flash.h"
#include "nvs.h"
#include "earth_texture.h"

// Fast atan2 approximation
static inline float fast_atan2(float y, float x) {
    float abs_y = fabsf(y) + 1e-10f;
    float r, angle;
    if (x >= 0.0f) {
        r = (x - abs_y) / (x + abs_y);
        angle = 0.78539816f - 0.78539816f * r;
    } else {
        r = (x + abs_y) / (abs_y - x);
        angle = 2.35619449f - 0.78539816f * r;
    }
    return (y < 0.0f) ? -angle : angle;
}

// Fast asin approximation
static inline float fast_asin(float x) {
    float abs_x = fabsf(x);
    if (abs_x > 1.0f) abs_x = 1.0f;
    float res = 1.57079633f - sqrtf(1.0f - abs_x) * (1.57079633f - 0.2146018f * abs_x);
    return (x >= 0.0f) ? res : -res;
}

// Fast inverse sqrt (Quake III / Newton-Raphson, ~1% error, ~4x faster than 1/sqrtf)
static inline float fast_rsqrt(float x) {
    float xhalf = 0.5f * x;
    int i;
    __builtin_memcpy(&i, &x, sizeof(i));
    i = 0x5f3759df - (i >> 1);
    __builtin_memcpy(&x, &i, sizeof(x));
    x = x * (1.5f - xhalf * x * x); // one Newton step, ~0.175% error
    return x;
}
static inline float fast_sqrt(float x) { return x * fast_rsqrt(x); }


#define EXAMPLE_PIN_NUM_SCLK 39
#define EXAMPLE_PIN_NUM_MOSI 38
#define EXAMPLE_PIN_NUM_MISO -1
#define EXAMPLE_SPI_HOST SPI2_HOST
#define EXAMPLE_I2C_NUM 1
#define EXAMPLE_PIN_NUM_I2C_SDA 48
#define EXAMPLE_PIN_NUM_I2C_SCL 47
#define EXAMPLE_LCD_PIXEL_CLOCK_HZ (60 * 1000 * 1000) // Pushed to 60MHz for high FPS
#define EXAMPLE_PIN_NUM_LCD_DC 42
#define EXAMPLE_PIN_NUM_LCD_RST -1
#define EXAMPLE_PIN_NUM_LCD_CS 45
#define EXAMPLE_LCD_H_RES 240
#define EXAMPLE_LCD_V_RES 320
#define EXAMPLE_PIN_NUM_BK_LIGHT 1

// Button & Jog Dial Pins (Waveshare ESP32-S3-Touch-LCD-2 confirmed pins)
#define CLUTCH_PIN 4      // Push to hover - GPIO 4 (ADC1_CH3 but we use it digital only)
#define BTN_L_PIN 21      // Left Click
#define JOG_SW_PIN 10     // Jog Switch
#define JOG_UP_PIN 7      // Jog Up
#define JOG_DN_PIN 20     // Jog Down
#define BOOT_BUTTON_PIN 0 // BOOT Button (Menu)
// Reverted back to GPIO 6 because GPIO 5 caused a screen conflict!
// You will need to wire the VBAT divider midpoint to GPIO 6 for battery reading to work.
// Default assumption: 100K/100K -> ratio = 2.0 (set in BAT_DIVIDER_RATIO below)
#define BAT_ADC_CHANNEL  ADC_CHANNEL_5   // GPIO 6 = ADC1_CH5
#define BAT_DIVIDER_RATIO 2.0f           // Change to 3.0f if divider is 200K/100K

// Power management thresholds
#define POWER_SAVE_TIMEOUT_MS  30000  // Screen off after 30s still (was 5s)
#define DEEP_SLEEP_TIMEOUT_MS  300000 // Deep sleep after 5m still (was 30s)
#define MOTION_THRESHOLD       0.3f   // Accel g change to count as motion

#define EXAMPLE_LVGL_TICK_PERIOD_MS 2

static const char *TAG = "S3_AIR_MOUSE";
static lv_disp_drv_t disp_drv;
static SemaphoreHandle_t lvgl_api_mux = NULL;
esp_lcd_panel_handle_t panel_handle;

// 3D Earth Canvas definitions
#define EARTH_RADIUS 64
#define EARTH_DIAM (EARTH_RADIUS * 2)
static lv_obj_t *earth_canvas;
static lv_color_t *earth_cbuf;

#define NUM_SPARKLES 40
static lv_obj_t *sparkles[NUM_SPARKLES];
static float sparkle_vx[NUM_SPARKLES];
static float sparkle_vy[NUM_SPARKLES];
static float sparkle_x[NUM_SPARKLES];
static float sparkle_y[NUM_SPARKLES];
static int sparkle_life[NUM_SPARKLES];

// State Variables
static bool is_screen_on = true;
static bool in_settings_menu = false;
static bool gyro_clutch_active = false;
static bool is_calibrating = true; // Auto-calibrate on boot to fix sliding offset

// Config
static bool cfg_invert_x = false;
static bool cfg_invert_y = true;
static bool cfg_swap_xy = false;
static bool cfg_z_axis = true;
static float cfg_sensitivity = 1.5f;
static float cfg_deadzone = 10.0f;
static int cfg_device_id = 1; // Multi-device channel (1, 2, or 3)
static int cfg_orientation = 0;      // Mouse axis rotation (0=default,1=0°,2=90°cw,3=180°)
static int cfg_display_rot = 0;      // Display rotation: 0=portrait,1=landscape,2=portrait flip,3=landscape flip
static int cfg_imu_remap = 0;        // IMU axis remap: 0=XYZ, 1=ZYX, 2=YXZ, 3=XZY
static int cfg_earth_spin = 0;       // Earth auto-spin speed: 0=off,1=slow,2=medium,3=fast
static int cfg_earth_theme = 0;      // 0=Normal, 1=Mars, 2=Matrix, 3=Ice, 4=Vaporwave, 5=Noir, 6=Lava, 7=Gold
static int cfg_twist_gesture = 0;    // 0=Volume, 1=Scroll, 2=Zoom, 3=Next/Prev, 4=Off
static bool jog_mode_left_right = false; // Toggled by shaking the board
static float earth_auto_lon = 0.0f;  // Cumulative auto-spin longitude offset

// UI Elements
static lv_obj_t *main_scr;
static lv_obj_t *mouse_hud_cont;
static lv_obj_t *hud_labels_cont;
static lv_obj_t *settings_cont;
static lv_obj_t *lbl_device_info;
static lv_obj_t *lbl_jog_mode;
static lv_obj_t *lbl_battery;

volatile int bat_pct = 100;
volatile bool is_charging = false;

static lv_obj_t *settings_list;
static lv_obj_t *items[14]; // 14 settings items
static int menu_idx = 0;

// Watchdog
volatile uint32_t imu_task_heartbeat = 0;

static i2c_master_dev_handle_t imu_dev_handle = NULL;
static float gyro_off_x = 0, gyro_off_y = 0, gyro_off_z = 0;

// Quaternion snapshot: written by IMU task (Core 0), read by gui_task (Core 1)
static volatile float rq0=1.0f, rq1=0.0f, rq2=0.0f, rq3=0.0f;

bool lvgl_lock(int timeout_ms) {
    const TickType_t timeout_ticks = (timeout_ms == -1) ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms);
    return xSemaphoreTakeRecursive(lvgl_api_mux, timeout_ticks) == pdTRUE;
}
void lvgl_unlock(void) { xSemaphoreGiveRecursive(lvgl_api_mux); }

static void toggle_screen(bool on) {
    is_screen_on = on;
    gpio_set_level(EXAMPLE_PIN_NUM_BK_LIGHT, on ? 1 : 0);
}

static void apply_glass_style(lv_obj_t * obj) {
    lv_obj_set_style_bg_color(obj, lv_color_hex(0xffffff), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_10, 0);
    lv_obj_set_style_border_color(obj, lv_color_hex(0x00FFFF), 0);
    lv_obj_set_style_border_width(obj, 1, 0);
    lv_obj_set_style_border_opa(obj, LV_OPA_50, 0);
    lv_obj_set_style_radius(obj, 10, 0);
    lv_obj_set_style_text_color(obj, lv_color_hex(0xffffff), 0);
}

static void update_settings_ui() {
    if(lvgl_lock(-1)) {
        static const char *disp_rot_names[] = {"Portrait", "Landscape", "Port.Flip", "Land.Flip"};
        static const char *imu_remap_names[] = {"XYZ", "ZYX", "YXZ", "XZY"};
        static const char *spin_names[]      = {"OFF", "Slow", "Med", "Fast"};
        static const char *theme_names[]     = {"Normal", "Mars", "Matrix", "Ice", "Vapor", "Noir", "Lava", "Gold"};
        static const char *twist_names[]     = {"Volume", "Scroll", "Zoom", "Track", "OFF"};
        for(int i=0; i<14; i++) {
            if (i == menu_idx) {
                lv_obj_set_style_bg_opa(items[i], LV_OPA_80, 0);
                lv_obj_set_style_bg_color(items[i], lv_color_hex(0x004080), 0);
                lv_obj_set_style_border_color(items[i], lv_color_hex(0x00FFFF), 0);
                lv_obj_set_style_border_width(items[i], 2, 0);
                lv_obj_set_style_shadow_color(items[i], lv_color_hex(0x00FFFF), 0);
                lv_obj_set_style_shadow_width(items[i], 15, 0);
            } else {
                lv_obj_set_style_bg_opa(items[i], LV_OPA_20, 0);
                lv_obj_set_style_bg_color(items[i], lv_color_hex(0x101020), 0);
                lv_obj_set_style_border_color(items[i], lv_color_hex(0x404040), 0);
                lv_obj_set_style_border_width(items[i], 1, 0);
                lv_obj_set_style_shadow_width(items[i], 0, 0);
            }
        }
        lv_label_set_text_fmt(lv_obj_get_child(items[0], 0),  LV_SYMBOL_SETTINGS  " Z-Axis (Yaw): %s",     cfg_z_axis        ? "#00FF00 ON#"  : "#FF0000 OFF#");
        lv_label_set_text_fmt(lv_obj_get_child(items[1], 0),  LV_SYMBOL_SETTINGS  " Invert X: %s",         cfg_invert_x      ? "#00FF00 ON#"  : "#FF0000 OFF#");
        lv_label_set_text_fmt(lv_obj_get_child(items[2], 0),  LV_SYMBOL_SETTINGS  " Invert Y: %s",         cfg_invert_y      ? "#00FF00 ON#"  : "#FF0000 OFF#");
        lv_label_set_text_fmt(lv_obj_get_child(items[3], 0),  LV_SYMBOL_LOOP      " Swap X/Y: %s",         cfg_swap_xy       ? "#00FF00 ON#"  : "#FF0000 OFF#");
        lv_label_set_text_fmt(lv_obj_get_child(items[4], 0),  LV_SYMBOL_VOLUME_MAX" Sensitivity: #00FFFF %.1f#", cfg_sensitivity);
        lv_label_set_text_fmt(lv_obj_get_child(items[5], 0),  LV_SYMBOL_CLOSE     " Deadzone: #00FFFF %.0f#",   cfg_deadzone);
        lv_label_set_text_fmt(lv_obj_get_child(items[6], 0),  LV_SYMBOL_REFRESH   " Calibrate Gyro");
        lv_label_set_text_fmt(lv_obj_get_child(items[7], 0),  LV_SYMBOL_KEYBOARD  " Active Device: #00FFFF D%d#", cfg_device_id);
        lv_label_set_text_fmt(lv_obj_get_child(items[8], 0),  LV_SYMBOL_LOOP      " Mouse Axis: #00FFFF %d°#",   cfg_orientation * 90);
        lv_label_set_text_fmt(lv_obj_get_child(items[9], 0),  LV_SYMBOL_IMAGE     " IMU Remap: #00FF00 %s#",     imu_remap_names[cfg_imu_remap]);
        lv_label_set_text_fmt(lv_obj_get_child(items[10], 0), LV_SYMBOL_REFRESH   " Display Rot: #00FF00 %s#",   disp_rot_names[cfg_display_rot]);
        lv_label_set_text_fmt(lv_obj_get_child(items[11], 0), LV_SYMBOL_PLAY      " Earth Spin: #00FF00 %s#",    spin_names[cfg_earth_spin]);
        lv_label_set_text_fmt(lv_obj_get_child(items[12], 0), LV_SYMBOL_EYE_OPEN  " Theme: #00FF00 %s#",         theme_names[cfg_earth_theme]);
        lv_label_set_text_fmt(lv_obj_get_child(items[13], 0), LV_SYMBOL_SHUFFLE   " Twist: #00FF00 %s#",         twist_names[cfg_twist_gesture]);
        lv_obj_scroll_to_view(items[menu_idx], LV_ANIM_ON);
        lvgl_unlock();
    }
}

static void apply_display_rotation() {
    // Map cfg_display_rot (0-3) to LVGL rotation constants
    static const lv_disp_rot_t rot_map[] = {
        LV_DISP_ROT_NONE,
        LV_DISP_ROT_90,
        LV_DISP_ROT_180,
        LV_DISP_ROT_270
    };
    lv_disp_t *disp = lv_disp_get_default();
    if (disp) lv_disp_set_rotation(disp, rot_map[cfg_display_rot]);
}

static void load_settings() {
    nvs_handle_t my_handle;
    if (nvs_open("storage", NVS_READONLY, &my_handle) == ESP_OK) {
        uint8_t val8; int32_t val32;
        if (nvs_get_u8(my_handle, "z_axis",    &val8)  == ESP_OK) cfg_z_axis       = (val8 == 1);
        if (nvs_get_u8(my_handle, "inv_x",     &val8)  == ESP_OK) cfg_invert_x     = (val8 == 1);
        if (nvs_get_u8(my_handle, "inv_y",     &val8)  == ESP_OK) cfg_invert_y     = (val8 == 1);
        if (nvs_get_u8(my_handle, "swap_xy",   &val8)  == ESP_OK) cfg_swap_xy      = (val8 == 1);
        if (nvs_get_i32(my_handle, "sens",     &val32) == ESP_OK) cfg_sensitivity  = val32 / 100.0f;
        if (nvs_get_i32(my_handle, "dead",     &val32) == ESP_OK) cfg_deadzone     = (float)val32;
        if (nvs_get_u8(my_handle, "dev_id",    &val8)  == ESP_OK) cfg_device_id    = val8;
        if (nvs_get_u8(my_handle, "orient",    &val8)  == ESP_OK) cfg_orientation  = val8;
        if (nvs_get_u8(my_handle, "disp_rot",  &val8)  == ESP_OK) cfg_display_rot  = val8;
        if (nvs_get_u8(my_handle, "imu_remap", &val8)  == ESP_OK) cfg_imu_remap    = val8;
        if (nvs_get_u8(my_handle, "earth_spin",&val8)  == ESP_OK) cfg_earth_spin   = val8;
        if (nvs_get_u8(my_handle, "earth_thm", &val8)  == ESP_OK) cfg_earth_theme  = val8;
        if (nvs_get_u8(my_handle, "twist",     &val8)  == ESP_OK) cfg_twist_gesture= val8;
        if (nvs_get_i32(my_handle, "g_off_x",  &val32) == ESP_OK) gyro_off_x       = val32 / 1000.0f;
        if (nvs_get_i32(my_handle, "g_off_y",  &val32) == ESP_OK) gyro_off_y       = val32 / 1000.0f;
        if (nvs_get_i32(my_handle, "g_off_z",  &val32) == ESP_OK) gyro_off_z       = val32 / 1000.0f;
        nvs_close(my_handle);
    }
}

static void save_settings() {
    nvs_handle_t my_handle;
    if (nvs_open("storage", NVS_READWRITE, &my_handle) == ESP_OK) {
        nvs_set_u8(my_handle, "z_axis",     cfg_z_axis     ? 1 : 0);
        nvs_set_u8(my_handle, "inv_x",      cfg_invert_x   ? 1 : 0);
        nvs_set_u8(my_handle, "inv_y",      cfg_invert_y   ? 1 : 0);
        nvs_set_u8(my_handle, "swap_xy",    cfg_swap_xy    ? 1 : 0);
        nvs_set_i32(my_handle, "sens",      (int32_t)(cfg_sensitivity * 100));
        nvs_set_i32(my_handle, "dead",      (int32_t)cfg_deadzone);
        nvs_set_u8(my_handle, "dev_id",     cfg_device_id);
        nvs_set_u8(my_handle, "orient",     cfg_orientation);
        nvs_set_u8(my_handle, "disp_rot",   cfg_display_rot);
        nvs_set_u8(my_handle, "imu_remap",  cfg_imu_remap);
        nvs_set_u8(my_handle, "earth_spin", cfg_earth_spin);
        nvs_set_u8(my_handle, "earth_thm",  cfg_earth_theme);
        nvs_set_u8(my_handle, "twist",      cfg_twist_gesture);
        nvs_set_i32(my_handle, "g_off_x",   (int32_t)(gyro_off_x * 1000));
        nvs_set_i32(my_handle, "g_off_y",   (int32_t)(gyro_off_y * 1000));
        nvs_set_i32(my_handle, "g_off_z",   (int32_t)(gyro_off_z * 1000));
        nvs_commit(my_handle);
        nvs_close(my_handle);
    }
}

static void build_ui(lv_obj_t *parent) {
    lv_obj_set_style_bg_color(parent, lv_color_hex(0x000000), 0);

    // Mouse HUD
    mouse_hud_cont = lv_obj_create(parent);
    lv_obj_set_size(mouse_hud_cont, lv_pct(100), lv_pct(100));
    lv_obj_set_style_bg_opa(mouse_hud_cont, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(mouse_hud_cont, 0, 0);

    // Separated HUD Labels container so they can be hidden during settings
    hud_labels_cont = lv_obj_create(mouse_hud_cont);
    lv_obj_set_size(hud_labels_cont, lv_pct(100), lv_pct(100));
    lv_obj_set_style_bg_opa(hud_labels_cont, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(hud_labels_cont, 0, 0);

    // 3D Earth Canvas creation
    earth_canvas = lv_canvas_create(mouse_hud_cont);
    earth_cbuf = heap_caps_malloc(EARTH_DIAM * EARTH_DIAM * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    if (!earth_cbuf) earth_cbuf = heap_caps_malloc(EARTH_DIAM * EARTH_DIAM * sizeof(lv_color_t), MALLOC_CAP_DMA); // Fallback
    lv_canvas_set_buffer(earth_canvas, earth_cbuf, EARTH_DIAM, EARTH_DIAM, LV_IMG_CF_TRUE_COLOR);
    lv_obj_align(earth_canvas, LV_ALIGN_CENTER, 0, 0);
    lv_canvas_fill_bg(earth_canvas, lv_color_hex(0x000000), LV_OPA_TRANSP);
    
    // Sparkles
    for(int i=0; i<NUM_SPARKLES; i++) {
        sparkles[i] = lv_obj_create(mouse_hud_cont);
        lv_obj_set_size(sparkles[i], 5, 5);
        lv_obj_set_style_bg_color(sparkles[i], lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_radius(sparkles[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_border_width(sparkles[i], 0, 0);
        lv_obj_set_style_shadow_color(sparkles[i], lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_shadow_width(sparkles[i], 8, 0);
        lv_obj_set_style_shadow_opa(sparkles[i], LV_OPA_80, 0);
        lv_obj_add_flag(sparkles[i], LV_OBJ_FLAG_HIDDEN);
    }

    lbl_device_info = lv_label_create(hud_labels_cont);
    lv_label_set_text(lbl_device_info, "DEV: 1");
    lv_obj_align(lbl_device_info, LV_ALIGN_TOP_LEFT, 5, 5);
    lv_obj_set_style_text_color(lbl_device_info, lv_color_hex(0xFF8800), 0);

    lbl_jog_mode = lv_label_create(hud_labels_cont);
    lv_label_set_text(lbl_jog_mode, "Mode: Scroll");
    lv_obj_align(lbl_jog_mode, LV_ALIGN_TOP_RIGHT, -5, 5);
    lv_obj_set_style_text_color(lbl_jog_mode, lv_color_hex(0x00FFFF), 0);

    lbl_battery = lv_label_create(hud_labels_cont);
    lv_label_set_recolor(lbl_battery, true);
    lv_label_set_text(lbl_battery, "100%");
    lv_obj_align(lbl_battery, LV_ALIGN_BOTTOM_LEFT, 5, -5);

    // Settings Menu
    settings_cont = lv_obj_create(parent);
    lv_obj_set_size(settings_cont, lv_pct(100), lv_pct(100));
    lv_obj_set_style_bg_opa(settings_cont, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(settings_cont, 0, 0);
    lv_obj_add_flag(settings_cont, LV_OBJ_FLAG_HIDDEN);

    lv_obj_t *cfg_title = lv_label_create(settings_cont);
    lv_label_set_text(cfg_title, "SETTINGS");
    lv_obj_align(cfg_title, LV_ALIGN_TOP_LEFT, 15, 20);
    lv_obj_set_style_text_color(cfg_title, lv_color_hex(0x00FF00), 0);

    settings_list = lv_obj_create(settings_cont);
    lv_obj_set_size(settings_list, lv_pct(95), lv_pct(60));
    lv_obj_align(settings_list, LV_ALIGN_BOTTOM_MID, 0, -10);
    lv_obj_set_style_bg_opa(settings_list, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(settings_list, 0, 0);
    lv_obj_set_flex_flow(settings_list, LV_FLEX_FLOW_COLUMN);

    for(int i=0; i<14; i++) { // 14 items: 0-13
        items[i] = lv_obj_create(settings_list);
        lv_obj_set_size(items[i], lv_pct(100), 40);
        apply_glass_style(items[i]);
        lv_obj_t *l = lv_label_create(items[i]);
        lv_label_set_recolor(l, true);
        lv_obj_center(l);
    }
    update_settings_ui();
}

static esp_err_t i2c_read_reg(uint8_t reg, uint8_t *data, size_t len) {
    return i2c_master_transmit_receive(imu_dev_handle, &reg, 1, data, len, pdMS_TO_TICKS(100));
}
static esp_err_t i2c_write_reg(uint8_t reg, uint8_t data) {
    uint8_t buf[2] = {reg, data};
    return i2c_master_transmit(imu_dev_handle, buf, 2, pdMS_TO_TICKS(100));
}

static void imu_init(void) {
    i2c_master_bus_config_t i2c_mst_config = {
        .clk_source = I2C_CLK_SRC_DEFAULT, .i2c_port = EXAMPLE_I2C_NUM,
        .scl_io_num = EXAMPLE_PIN_NUM_I2C_SCL, .sda_io_num = EXAMPLE_PIN_NUM_I2C_SDA,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus_handle;
    ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config, &bus_handle));
    i2c_device_config_t dev_cfg = { .dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = 0x6B, .scl_speed_hz = 400000 };
    if (i2c_master_bus_add_device(bus_handle, &dev_cfg, &imu_dev_handle) != ESP_OK) {
        dev_cfg.device_address = 0x6A;
        i2c_master_bus_add_device(bus_handle, &dev_cfg, &imu_dev_handle);
    }
    uint8_t id = 0; i2c_read_reg(0x00, &id, 1);
    if(id == 0x05) {
        i2c_write_reg(0x02, 0x40); i2c_write_reg(0x03, 0x24); i2c_write_reg(0x04, 0x64);
        i2c_write_reg(0x08, 0x03); i2c_write_reg(0x09, 0x01);
    }
}

static void hardware_input_task(void *param) {
    // GPIO Init with internal pullups
    gpio_config_t btn_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_INPUT,
        .pin_bit_mask = (1ULL<<BTN_L_PIN) | (1ULL<<CLUTCH_PIN) | (1ULL<<JOG_SW_PIN) | (1ULL<<JOG_UP_PIN) | (1ULL<<JOG_DN_PIN) | (1ULL<<BOOT_BUTTON_PIN),
        .pull_down_en = 0,
        .pull_up_en = 1
    };
    gpio_config(&btn_conf);

    // Init ADC for Battery
    adc_oneshot_unit_handle_t adc1_handle;
    adc_oneshot_unit_init_cfg_t init_config1 = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config1, &adc1_handle));

    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, BAT_ADC_CHANNEL, &config));
    // Note: BAT_ADC measures through 100K/100K divider on Waveshare board
    // VBAT_actual = VADC * 2

    bool sw_pressed = false;
    uint32_t sw_press_time = 0;
    bool sw_long_press_triggered = false;
    
    bool boot_pressed = false;
    uint32_t boot_press_time = 0;
    int boot_clicks = 0;

    int total_taps = 0;
    uint32_t last_tap_time = 0;

    bool last_up_state = false;
    bool last_dn_state = false;
    
    bool last_left_pressed = false;
    bool last_right_pressed = false;
    uint8_t mouse_buttons_state = 0;

    uint32_t last_motion_ms = 0;  // will be set on first loop
    float last_accel_mag = 1.0f;
    bool screen_saver_on = false;
    bool power_save_initialized = false;
    float bat_voltage = 3.8f;
    float last_bat_v = 3.8f;
    uint32_t last_bat_check = 0;

    while(1) {
        uint32_t now = esp_log_timestamp();
        imu_task_heartbeat = now;

        // Initialize motion timer on first run so screen doesn't sleep immediately
        if (!power_save_initialized) {
            last_motion_ms = now;
            last_bat_check = now;
            power_save_initialized = true;
        }
        
        // --- Battery Monitor (runs every 2s) ---
        if (now - last_bat_check > 2000) {
            last_bat_check = now;
            int adc_raw = 0;
            if (adc_oneshot_read(adc1_handle, BAT_ADC_CHANNEL, &adc_raw) == ESP_OK) {
                // ADC_ATTEN_DB_12 full scale ~3.1V on ESP32-S3
                float vadc = (adc_raw / 4095.0f) * 3.1f;
                float current_v = vadc * BAT_DIVIDER_RATIO;

                // Sanity gate: raw < 200 means GPIO is floating or no battery connected
                // Don't let bad readings corrupt the LPF
                if (adc_raw > 200 && current_v > 2.5f && current_v < 5.0f) {
                    // Low-pass smooth
                    bat_voltage = bat_voltage * 0.8f + current_v * 0.2f;

                    // Charging: voltage climbs above slow-moving baseline
                    static float charge_baseline = 0.0f;
                    if (charge_baseline == 0.0f) charge_baseline = bat_voltage;
                    charge_baseline = charge_baseline * 0.995f + bat_voltage * 0.005f;
                    is_charging = (bat_voltage > 4.05f) || (bat_voltage > charge_baseline + 0.04f);
                    last_bat_v = current_v;

                    // LiPo discharge curve (real-world): 3.2V=0%, 4.15V=100%
                    int pct;
                    if      (bat_voltage >= 4.15f) pct = 100;
                    else if (bat_voltage >= 4.0f)  pct = (int)((bat_voltage - 4.0f)  / 0.15f * 20.0f) + 80;
                    else if (bat_voltage >= 3.8f)  pct = (int)((bat_voltage - 3.8f)  / 0.20f * 30.0f) + 50;
                    else if (bat_voltage >= 3.6f)  pct = (int)((bat_voltage - 3.6f)  / 0.20f * 30.0f) + 20;
                    else if (bat_voltage >= 3.4f)  pct = (int)((bat_voltage - 3.4f)  / 0.20f * 15.0f) + 5;
                    else if (bat_voltage >= 3.2f)  pct = (int)((bat_voltage - 3.2f)  / 0.20f * 5.0f);
                    else                            pct = 0;
                    if (pct > 100) pct = 100;
                    if (pct < 0)   pct = 0;
                    bat_pct = pct;
                }
                // If ADC reads garbage, keep last known good value (don't corrupt display)
            }

            // Blink backlight (fast 250ms) when charging - use BK light GPIO
            // Only blink when screen is off (power save). When screen is on, charging shows as UI.
            if (is_charging && screen_saver_on) {
                gpio_set_level(EXAMPLE_PIN_NUM_BK_LIGHT, (now / 250) % 2);
            }
        }

        // Update device connection status info label on screen
        static uint32_t last_status_update = 0;
        if (now - last_status_update > 250) {
            last_status_update = now;
            if (lvgl_lock(10)) {
                bool conn = ble_mouse_is_connected();
                lv_label_set_text_fmt(lbl_device_info, "DEV %d: %s", cfg_device_id, conn ? "#00FF00 CON#" : "#FF8800 ADV#");
                lv_label_set_text_fmt(lbl_jog_mode, jog_mode_left_right ? LV_SYMBOL_LEFT" "LV_SYMBOL_RIGHT : LV_SYMBOL_UP" "LV_SYMBOL_DOWN);
                if (is_charging) {
                    uint8_t pulse = (esp_log_timestamp() / 10) % 255;
                    if (pulse > 127) pulse = 255 - pulse;
                    int hex_col = (pulse * 2) << 8;
                    lv_label_set_text_fmt(lbl_battery, "#%06x "LV_SYMBOL_CHARGE" %d%%#", hex_col, bat_pct);
                } else {
                    int hex_col = (bat_pct < 20) ? 0xFF0000 : 0x00FF00;
                    lv_label_set_text_fmt(lbl_battery, "#%06x %d%%#", hex_col, bat_pct);
                }
                lvgl_unlock();
            }
        }
        // Boot Button Logic
        if (gpio_get_level(BOOT_BUTTON_PIN) == 0) {
            if (!boot_pressed) { boot_pressed = true; boot_press_time = now; }
        } else {
            if (boot_pressed) {
                boot_pressed = false;
                if (now - boot_press_time < 500) {
                    boot_clicks++;
                    last_tap_time = now;
                }
            }
        }

        if (boot_clicks > 0 && !boot_pressed && (now - last_tap_time > 400)) {
            if (boot_clicks == 1) { // Toggle Menu
                in_settings_menu = !in_settings_menu;
                if(lvgl_lock(-1)) {
                    if(in_settings_menu) {
                        lv_obj_add_flag(hud_labels_cont, LV_OBJ_FLAG_HIDDEN);
                        lv_obj_clear_flag(settings_cont, LV_OBJ_FLAG_HIDDEN);
                    } else {
                        save_settings();
                        lv_obj_clear_flag(hud_labels_cont, LV_OBJ_FLAG_HIDDEN);
                        lv_obj_add_flag(settings_cont, LV_OBJ_FLAG_HIDDEN);
                    }
                    lvgl_unlock();
                }
            } else if (boot_clicks == 2) { // Save and Exit Menu
                if(in_settings_menu) {
                    save_settings();
                    in_settings_menu = false;
                    if(lvgl_lock(-1)) {
                        lv_obj_clear_flag(hud_labels_cont, LV_OBJ_FLAG_HIDDEN);
                        lv_obj_add_flag(settings_cont, LV_OBJ_FLAG_HIDDEN);
                        lvgl_unlock();
                    }
                }
            } else if (boot_clicks == 3) {
                toggle_screen(!is_screen_on);
            }
            boot_clicks = 0;
        }

        // Left Click and Clutch Logic
        bool clutch_pressed = (gpio_get_level(CLUTCH_PIN) == 0);
        bool left_pressed = (gpio_get_level(BTN_L_PIN) == 0);

        static bool last_clutch_raw = false;
        if (clutch_pressed) {
            if (!last_clutch_raw) {
                last_clutch_raw = true;
                if (!gyro_clutch_active) {
                    gyro_clutch_active = true;
                }
            }
        } else {
            if (last_clutch_raw) {
                last_clutch_raw = false;
                if (gyro_clutch_active) {
                    gyro_clutch_active = false;
                }
            }
        }

        static uint32_t both_held_start = 0;
        static bool both_held_triggered = false;
        
        if (clutch_pressed && left_pressed) {
            if (both_held_start == 0) both_held_start = now;
            else if (!both_held_triggered && (now - both_held_start > 2000)) {
                both_held_triggered = true;
                cfg_device_id++;
                if (cfg_device_id > 3) cfg_device_id = 1;
                save_settings();
                update_settings_ui();
                if (lvgl_lock(-1)) {
                    lv_label_set_text_fmt(lbl_device_info, "REBOOTING CH %d...", cfg_device_id);
                    lvgl_unlock();
                }
                vTaskDelay(pdMS_TO_TICKS(1000));
                esp_restart();
            }
        } else {
            both_held_start = 0;
            both_held_triggered = false;
        }

        if (left_pressed != last_left_pressed) {
            if (left_pressed) {
                mouse_buttons_state |= 0x01; // Left click down
            } else {
                mouse_buttons_state &= ~0x01; // Left click up
            }
            ble_mouse_send_report(0, 0, 0, mouse_buttons_state);
            last_left_pressed = left_pressed;
        }
        // Jog Dial SW Logic (Rest SW is enter / back as before)
        if (gpio_get_level(JOG_SW_PIN) == 0) {
            if (!sw_pressed) {
                sw_pressed = true;
                sw_press_time = now;
                sw_long_press_triggered = false;
            } else if (!sw_long_press_triggered && (now - sw_press_time >= 800)) {
                sw_long_press_triggered = true;
                if (in_settings_menu) {
                    save_settings();
                    in_settings_menu = false;
                    if(lvgl_lock(-1)) {
                        lv_obj_clear_flag(hud_labels_cont, LV_OBJ_FLAG_HIDDEN);
                        lv_obj_add_flag(settings_cont, LV_OBJ_FLAG_HIDDEN);
                        lvgl_unlock();
                    }
                } else {
                    ble_mouse_send_media(0x40); // AC Back (Bit 6)
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_media(0x00);
                }
            }
        } else {
            if (sw_pressed) {
                sw_pressed = false;
                if (!sw_long_press_triggered && (now - sw_press_time < 400)) {
                    if (in_settings_menu) {
                        if(menu_idx == 0) cfg_z_axis = !cfg_z_axis;
                        else if(menu_idx == 1) cfg_invert_x = !cfg_invert_x;
                        else if(menu_idx == 2) cfg_invert_y = !cfg_invert_y;
                        else if(menu_idx == 3) cfg_swap_xy = !cfg_swap_xy;
                        else if(menu_idx == 4) { cfg_sensitivity += 0.5f; if(cfg_sensitivity>4) cfg_sensitivity=0.5f; }
                        else if(menu_idx == 5) { cfg_deadzone += 5; if(cfg_deadzone>30) cfg_deadzone=5; }
                        else if(menu_idx == 6) { is_calibrating = true; }
                        else if(menu_idx == 7) {
                            cfg_device_id++;
                            if (cfg_device_id > 3) cfg_device_id = 1;
                            save_settings();
                            update_settings_ui();
                                if (lvgl_lock(-1)) {
                                    lv_label_set_text_fmt(lbl_device_info, "REBOOTING CH %d...", cfg_device_id);
                                    lvgl_unlock();
                                }
                            vTaskDelay(pdMS_TO_TICKS(1000));
                            esp_restart();
                        }
                        else if(menu_idx == 8)  { cfg_orientation  = (cfg_orientation  + 1) % 4; }
                        else if(menu_idx == 9)  { cfg_imu_remap    = (cfg_imu_remap    + 1) % 4; }
                        else if(menu_idx == 10) {
                            cfg_display_rot = (cfg_display_rot + 1) % 4;
                            apply_display_rotation();
                        }
                        else if(menu_idx == 11) { cfg_earth_spin = (cfg_earth_spin + 1) % 4; }
                        else if(menu_idx == 12) { cfg_earth_theme = (cfg_earth_theme + 1) % 8; }
                        else if(menu_idx == 13) { cfg_twist_gesture = (cfg_twist_gesture + 1) % 5; }
                        update_settings_ui();
                    } else {
                        ble_mouse_send_keyboard(0, 0x28); // Enter
                        vTaskDelay(pdMS_TO_TICKS(50));
                        ble_mouse_send_keyboard(0, 0);
                    }
                }
            }
        }

        // Jog Dial Up / Down Logic (Auto-repeats if held)
        bool up_state = (gpio_get_level(JOG_UP_PIN) == 0);
        bool dn_state = (gpio_get_level(JOG_DN_PIN) == 0);

        static uint32_t up_press_start = 0;
        static uint32_t last_up_repeat = 0;
        static bool up_held = false;

        if (up_state) {
            if (!up_held) {
                up_held = true;
                up_press_start = now;
                if (in_settings_menu) {
                    menu_idx = (menu_idx - 1);
                    if (menu_idx < 0) menu_idx = 13; // 14 items (0-13)
                    update_settings_ui();
                } else {
                    ble_mouse_send_keyboard(0, jog_mode_left_right ? 0x50 : 0x52); // Up/Left Arrow
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_keyboard(0, 0);
                }
            } else {
                if (now - up_press_start > 400) {
                    if (now - last_up_repeat > 200) {
                        last_up_repeat = now;
                        if (in_settings_menu) {
                            menu_idx = (menu_idx - 1);
                            if (menu_idx < 0) menu_idx = 13; // 14 items (0-13)
                            update_settings_ui();
                        } else {
                            ble_mouse_send_keyboard(0, jog_mode_left_right ? 0x50 : 0x52); // Up/Left Arrow
                            vTaskDelay(pdMS_TO_TICKS(50));
                            ble_mouse_send_keyboard(0, 0);
                        }
                    }
                }
            }
        } else {
            up_held = false;
        }

        static uint32_t dn_press_start = 0;
        static uint32_t last_dn_repeat = 0;
        static bool dn_held = false;

        if (dn_state) {
            if (!dn_held) {
                dn_held = true;
                dn_press_start = now;
                if (in_settings_menu) {
                    menu_idx = (menu_idx + 1) % 14; // 14 items (0-13)
                    update_settings_ui();
                } else {
                    ble_mouse_send_keyboard(0, jog_mode_left_right ? 0x4F : 0x51); // Down/Right Arrow
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_keyboard(0, 0);
                }
            } else {
                if (now - dn_press_start > 400) {
                    if (now - last_dn_repeat > 200) {
                        last_dn_repeat = now;
                        if (in_settings_menu) {
                            menu_idx = (menu_idx + 1) % 14; // 14 items (0-13)
                            update_settings_ui();
                        } else {
                            ble_mouse_send_keyboard(0, jog_mode_left_right ? 0x4F : 0x51); // Down/Right Arrow
                            vTaskDelay(pdMS_TO_TICKS(50));
                            ble_mouse_send_keyboard(0, 0);
                        }
                    }
                }
            }
        } else {
            dn_held = false;
        }

        // IMU Logic
        uint8_t data[12];
        if (i2c_read_reg(0x35, data, 12) == ESP_OK) {
            int16_t ax = (data[1]<<8)|data[0];
            int16_t ay = (data[3]<<8)|data[2];
            int16_t az = (data[5]<<8)|data[4];
            int16_t gx = (data[7]<<8)|data[6];
            int16_t gy = (data[9]<<8)|data[8];
            int16_t gz = (data[11]<<8)|data[10];
            // ─── Motion Detection & Power Management ─────────────────────────────
            float accel_g_x = ax / 4096.0f;
            float accel_g_y = ay / 4096.0f;
            float accel_g_z = az / 4096.0f;
            float accel_mag = sqrtf(accel_g_x*accel_g_x + accel_g_y*accel_g_y + accel_g_z*accel_g_z);
            
            // Check gyro for any intentional movement using calibrated values
            float cgx = gx - gyro_off_x;
            float cgy = gy - gyro_off_y;
            float cgz = gz - gyro_off_z;
            float gyro_total = fabsf(cgx) + fabsf(cgy) + fabsf(cgz);

            bool motion_detected = (fabsf(accel_mag - last_accel_mag) > MOTION_THRESHOLD) 
                                 || (gyro_total > 150.0f) // 150 LSB is ~9 degrees per second
                                 || (gpio_get_level(CLUTCH_PIN) == 0)
                                 || (gpio_get_level(BTN_L_PIN) == 0)
                                 || (gpio_get_level(BOOT_BUTTON_PIN) == 0);
            
            // Periodic debug logging to serial to diagnose sleep/power issues
            static uint32_t last_power_debug = 0;
            if (now - last_power_debug > 5000) {
                last_power_debug = now;
                ESP_LOGI("POWER", "Still: %lu ms, Accel Mag Delta: %.3f (thresh: %.2f), Gyro Total: %.1f (thresh: 150.0), Clutch: %d, LBtn: %d, Boot: %d",
                         (unsigned long)(now - last_motion_ms),
                         fabsf(accel_mag - last_accel_mag), MOTION_THRESHOLD,
                         gyro_total,
                         gpio_get_level(CLUTCH_PIN),
                         gpio_get_level(BTN_L_PIN),
                         gpio_get_level(BOOT_BUTTON_PIN));
            }

            if (motion_detected) {
                last_motion_ms = now;
                last_accel_mag = accel_mag;
                if (screen_saver_on) {
                    screen_saver_on = false;
                    toggle_screen(true); // Wake the screen
                }
            } else {
                uint32_t still_ms = now - last_motion_ms;
                if (still_ms > DEEP_SLEEP_TIMEOUT_MS) {
                    // Enter deep sleep — wake on any GPIO (buttons)
                    if (lvgl_lock(-1)) {
                        lv_obj_t *sleep_lbl = lv_label_create(lv_scr_act());
                        lv_label_set_text(sleep_lbl, "Sleeping...");
                        lv_obj_center(sleep_lbl);
                        lvgl_unlock();
                    }
                    vTaskDelay(pdMS_TO_TICKS(200));
                    toggle_screen(false);
                    // Configure all button GPIOs as wake sources
                    esp_sleep_enable_ext0_wakeup(BOOT_BUTTON_PIN, 0); // wake on BOOT low
                    esp_deep_sleep_start();
                    // Never returns here
                } else if (still_ms > POWER_SAVE_TIMEOUT_MS && !screen_saver_on) {
                    screen_saver_on = true;
                    toggle_screen(false); // Screen off to save power
                }
            }


            static int16_t lp_ax=0, lp_ay=0, lp_az=0;
            if (lp_ax==0) { lp_ax=ax; lp_ay=ay; lp_az=az; }
            lp_ax = (lp_ax*19 + ax)/20; lp_ay = (lp_ay*19 + ay)/20; lp_az = (lp_az*19 + az)/20;
            int jerk = abs(ax-lp_ax) + abs(ay-lp_ay) + abs(az-lp_az);
            static uint32_t tap_cd = 0;
            static uint32_t tap_window_start = 0;
            if (jerk > 7200 && now > tap_cd) {
                if (total_taps == 0) tap_window_start = now;
                total_taps++;
                tap_cd = now + 250;
            }
            
            // Shake detection: require 3 high-jerk spikes within 300ms to prevent
            // false triggers from drops, bumps, or placing the board on a table.
            // jerk threshold 40000 ≈ ~2.5g jolt (16384 = 1g raw at ±2g range)
            static int shake_count = 0;
            static uint32_t shake_window_start = 0;
            if (jerk > 40000) {
                if (shake_count == 0) shake_window_start = now;
                if (now - shake_window_start < 350) {
                    shake_count++;
                } else {
                    // Window expired, restart
                    shake_count = 1;
                    shake_window_start = now;
                }
                if (shake_count >= 3) {
                    shake_count = 0;
                    // Shake detected
                    static uint32_t last_shake = 0;
                    if (now - last_shake > 2000) { // 2s cooldown prevents accidental re-trigger
                        jog_mode_left_right = !jog_mode_left_right;
                        if (lvgl_lock(-1)) {
                            lv_label_set_text_fmt(lbl_jog_mode, "MODE: %s", jog_mode_left_right ? "L/R" : "U/D");
                            lvgl_unlock();
                        }
                        last_shake = now;
                    }
                    if (lvgl_lock(-1)) {
                        for(int i=0; i<NUM_SPARKLES; i++) {
                            sparkle_x[i] = 120.0f;
                            sparkle_y[i] = 160.0f;
                            sparkle_vx[i] = ((rand() % 200) - 100) / 5.0f;
                            sparkle_vy[i] = ((rand() % 200) - 100) / 5.0f - 5.0f;
                            sparkle_life[i] = 20 + (rand() % 30);
                            lv_obj_clear_flag(sparkles[i], LV_OBJ_FLAG_HIDDEN);
                        }
                        lvgl_unlock();
                    }
                }
            } else if (now - shake_window_start > 350) {
                shake_count = 0; // reset if no jerk for >350ms
            }

            if (total_taps > 0 && (now - tap_window_start > 400)) {
                if (total_taps >= 2) {
                    // Double tap -> Page Up
                    ble_mouse_send_keyboard(0, 0x4B); // Page Up HID keycode
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_keyboard(0, 0);
                } else {
                    // Single tap -> Page Down
                    ble_mouse_send_keyboard(0, 0x4E); // Page Down HID keycode
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_keyboard(0, 0);
                }
                total_taps = 0;
            }

            static bool startup_calib_done = false;
            static int startup_calib_cnt = 0;
            static long startup_sgx=0, startup_sgy=0, startup_sgz=0;

            if (!startup_calib_done) {
                startup_sgx += gx;
                startup_sgy += gy;
                startup_sgz += gz;
                startup_calib_cnt++;
                if (startup_calib_cnt >= 100) {
                    if (gyro_off_x == 0.0f && gyro_off_y == 0.0f && gyro_off_z == 0.0f) {
                        gyro_off_x = startup_sgx / 100.0f;
                        gyro_off_y = startup_sgy / 100.0f;
                        gyro_off_z = startup_sgz / 100.0f;
                        ESP_LOGI("IMU", "Auto-calibrated startup offsets: X=%.1f Y=%.1f Z=%.1f", gyro_off_x, gyro_off_y, gyro_off_z);
                    }
                    startup_calib_done = true;
                }
            }

            if (is_calibrating) {
                static int calib_cnt = 0;
                static long sgx=0, sgy=0, sgz=0;
                sgx+=gx; sgy+=gy; sgz+=gz;
                calib_cnt++;
                
                // Animate sphere by running Mahony with zero gyro to quickly find gravity
                static uint32_t last_imu_time = 0;
                float dt_imu = (last_imu_time == 0) ? 0.01f : (now - last_imu_time) * 0.001f;
                if (dt_imu > 0.1f) dt_imu = 0.1f;
                last_imu_time = now;
                MahonyAHRSupdateIMU(0.0f, 0.0f, 0.0f, ax, ay, az, dt_imu);
                rq0=q0; rq1=q1; rq2=q2; rq3=q3;

                if (calib_cnt >= 100) {
                    gyro_off_x = sgx/100.0f; gyro_off_y = sgy/100.0f; gyro_off_z = sgz/100.0f;
                    is_calibrating = false; calib_cnt=0; sgx=0; sgy=0; sgz=0;
                    save_settings(); // Persist manual calibration to survive deep sleep
                    ESP_LOGI("IMU", "Manual calibration saved: X=%.1f Y=%.1f Z=%.1f", gyro_off_x, gyro_off_y, gyro_off_z);
                }
            } else {
                // Apply IMU axis remap before feeding to Mahony
                float raw_cgx = gx - gyro_off_x;
                float raw_cgy = gy - gyro_off_y;
                float raw_cgz = gz - gyro_off_z;
                float raw_ax = ax, raw_ay = ay, raw_az = az;
                float cgx, cgy, cgz, fax, fay, faz;
                switch(cfg_imu_remap) {
                    case 1: cgx=raw_cgz; cgy=raw_cgy; cgz=raw_cgx; fax=raw_az; fay=raw_ay; faz=raw_ax; break; // ZYX
                    case 2: cgx=raw_cgy; cgy=raw_cgx; cgz=raw_cgz; fax=raw_ay; fay=raw_ax; faz=raw_az; break; // YXZ
                    case 3: cgx=raw_cgx; cgy=raw_cgz; cgz=raw_cgy; fax=raw_ax; fay=raw_az; faz=raw_ay; break; // XZY
                    default: cgx=raw_cgx; cgy=raw_cgy; cgz=raw_cgz; fax=raw_ax; fay=raw_ay; faz=raw_az; break; // XYZ
                }

                // Use actual elapsed time for accurate Mahony integration
                static uint32_t last_imu_time = 0;
                float dt_imu = (last_imu_time == 0) ? 0.01f : (now - last_imu_time) * 0.001f;
                if (dt_imu > 0.1f) dt_imu = 0.1f; // clamp on first run / task stall
                last_imu_time = now;

                MahonyAHRSupdateIMU(cgx/16.4f, cgy/16.4f, cgz/16.4f, fax, fay, faz, dt_imu);
                // Snapshot quaternion for render task
                rq0=q0; rq1=q1; rq2=q2; rq3=q3;

                // ─── Configurable Wrist Twist Gesture (Roll) ──────────────────────
                if (cfg_twist_gesture != 4) { // Not disabled
                    static float twist_accum = 0.0f;
                    static uint32_t last_action_time = 0;
                    static bool last_was_cw = false;

                    float twist_rate = cgy / 16.4f; // degrees per second
                    
                    if (fabsf(twist_rate) > 120.0f) { // require >120 deg/sec deliberate twist
                        bool is_cw = (twist_rate > 0);
                        // Anti-rebound: ignore twists in the opposite direction for 400ms (hand returning)
                        if ((now - last_action_time < 400) && (is_cw != last_was_cw)) {
                            twist_accum = 0.0f;
                        } else {
                            twist_accum += twist_rate * dt_imu;
                        }
                    } else {
                        twist_accum *= 0.6f; // high friction to kill noise
                    }

                    // 20 degrees of twist = 1 action notch
                    if (twist_accum > 20.0f || twist_accum < -20.0f) {
                        bool clockwise = (twist_accum > 0);
                        twist_accum = 0.0f; // reset fully to prevent machine-gunning
                        
                        last_action_time = now;
                        last_was_cw = clockwise;
                        
                        if (cfg_twist_gesture == 0) { // Volume
                            ble_mouse_send_media(clockwise ? 0x01 : 0x02);
                            vTaskDelay(pdMS_TO_TICKS(15));
                            ble_mouse_send_media(0x00);
                        } else if (cfg_twist_gesture == 1) { // Scroll
                            ble_mouse_send_report(0, 0, clockwise ? 1 : -1, mouse_buttons_state);
                        } else if (cfg_twist_gesture == 2) { // Zoom (Ctrl + Scroll)
                            ble_mouse_send_keyboard(0x01, 0); // Left Ctrl
                            ble_mouse_send_report(0, 0, clockwise ? 1 : -1, mouse_buttons_state);
                            vTaskDelay(pdMS_TO_TICKS(15));
                            ble_mouse_send_keyboard(0, 0);
                        } else if (cfg_twist_gesture == 3) { // Next/Prev Track
                            ble_mouse_send_media(clockwise ? 0x10 : 0x20); // Next (Bit 4) / Prev (Bit 5)
                            vTaskDelay(pdMS_TO_TICKS(15));
                            ble_mouse_send_media(0x00);
                        }
                    }
                }

                if (gyro_clutch_active) {
                    float move_x = 0;
                    if (cfg_z_axis) {
                        move_x = -cgz * 0.1f;
                    } else {
                        move_x = cgy * 0.1f; // Use Roll for horizontal if Z is disabled
                    }
                    float move_y = cgx * 0.1f;
                    if (cfg_swap_xy) { float tmp = move_x; move_x = move_y; move_y = tmp; }
                    if (cfg_invert_x) move_x = -move_x;
                    if (cfg_invert_y) move_y = -move_y;

                    // Global axis shift based on orientation setting
                    float rot_x = move_x;
                    float rot_y = move_y;
                    if (cfg_orientation == 0)      { rot_x = -move_y; rot_y = move_x; } // default 90deg anticlockwise as before
                    else if (cfg_orientation == 1) { rot_x = move_x; rot_y = move_y; }  // 0 deg
                    else if (cfg_orientation == 2) { rot_x = move_y; rot_y = -move_x; } // 90deg clockwise
                    else if (cfg_orientation == 3) { rot_x = -move_x; rot_y = -move_y; }// 180deg
                    move_x = rot_x;
                    move_y = rot_y;

                    // ─── State-of-the-art cursor motion pipeline ────────────────────────────
                    // Stage 1: Raw deadzone (applied to unsmoothed gyro data)
                    float raw_x = (fabsf(move_x) > cfg_deadzone) ? move_x : 0.0f;
                    float raw_y = (fabsf(move_y) > cfg_deadzone) ? move_y : 0.0f;

                    // Stage 2: Dual-stage EMA — velocity EMA + position EMA
                    // Inner EMA (fast, tracks motion): alpha=0.45 responsive
                    // Outer EMA (slow, smooths jitter): alpha=0.30 stable
                    static float ema1_x = 0, ema1_y = 0; // fast
                    static float ema2_x = 0, ema2_y = 0; // slow
                    ema1_x = ema1_x * 0.55f + raw_x * 0.45f;
                    ema1_y = ema1_y * 0.55f + raw_y * 0.45f;
                    ema2_x = ema2_x * 0.70f + ema1_x * 0.30f;
                    ema2_y = ema2_y * 0.70f + ema1_y * 0.30f;

                    // Stage 3: Power-curve acceleration (Fitts's Law inspired)
                    // Small movements: linear (precise control zone)
                    // Large movements: quadratic boost (fast sweeping)
                    // f(v) = sign(v) * (|v|^1.6) scaled
                    float spd = sqrtf(ema2_x*ema2_x + ema2_y*ema2_y);
                    float accel_factor;
                    if (spd < 20.0f) {
                        accel_factor = 1.0f; // linear zone: precise
                    } else if (spd < 60.0f) {
                        accel_factor = 1.0f + (spd - 20.0f) * 0.04f; // ramp: 1x -> 2.6x
                    } else {
                        accel_factor = 2.6f + (spd - 60.0f) * 0.02f; // saturate boost
                        if (accel_factor > 4.0f) accel_factor = 4.0f;
                    }
                    float ax_final = ema2_x * accel_factor;
                    float ay_final = ema2_y * accel_factor;

                    // Stage 4: Sub-pixel accumulator (prevents quantization stutter)
                    static float accum_x=0, accum_y=0;
                    accum_x += ax_final * cfg_sensitivity * 0.012f;
                    accum_y += ay_final * cfg_sensitivity * 0.012f;

                    // Stage 5: Smooth deceleration — bleed off accumulator when raw=0
                    if (raw_x == 0.0f) { accum_x *= 0.80f; ema1_x *= 0.75f; ema2_x *= 0.75f; }
                    if (raw_y == 0.0f) { accum_y *= 0.80f; ema1_y *= 0.75f; ema2_y *= 0.75f; }

                    static uint32_t last_ble = 0;
                    if (now - last_ble > 12) { // ~83Hz BLE report rate
                        int32_t dx = (int32_t)accum_x;
                        int32_t dy = (int32_t)accum_y;
                        if (dx!=0 || dy!=0) {
                            if(dx>127) dx=127; if(dx<-127) dx=-127;
                            if(dy>127) dy=127; if(dy<-127) dy=-127;
                            ble_mouse_send_report(dx, dy, 0, mouse_buttons_state);
                            accum_x -= (float)dx;
                            accum_y -= (float)dy;
                        }
                        last_ble = now;
                    }
                }

            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

static void render_earth_frame(uint32_t now) {
    // Snapshot quaternion atomically (floats on Xtensa are not atomic,
    // but worst case we get one slightly stale frame — acceptable)
    float lq0=rq0, lq1=rq1, lq2=rq2, lq3=rq3;

    // Sparkles update
    for(int i=0; i<NUM_SPARKLES; i++) {
        if(sparkle_life[i] > 0) {
            sparkle_life[i]--;
            sparkle_x[i] += sparkle_vx[i];
            sparkle_vy[i] += 0.8f;
            sparkle_y[i] += sparkle_vy[i];
            lv_obj_set_pos(sparkles[i], (lv_coord_t)sparkle_x[i]-3, (lv_coord_t)sparkle_y[i]-3);
            if (sparkle_life[i] <= 0) lv_obj_add_flag(sparkles[i], LV_OBJ_FLAG_HIDDEN);
        }
    }

    // Fixed zoom = 256 (1:1). Breathing zoom was causing oversized dirty rects each frame,
    // wasting ~30% of SPI bandwidth on rescaling. Rotate the earth instead for visual interest.
    int zoom_val = in_settings_menu ? 90 : 256;
    lv_img_set_zoom(earth_canvas, zoom_val);
    if (in_settings_menu) {
        lv_obj_align(earth_canvas, LV_ALIGN_TOP_RIGHT, -10, 10);
    } else {
        lv_obj_align(earth_canvas, LV_ALIGN_CENTER, 0, 0);
    }

    // Build rotation matrix from quaternion (correct row-major, no transpose)
    // R * v rotates body vector v into world frame
    float r00 = 1.0f - 2.0f*(lq2*lq2 + lq3*lq3);
    float r01 = 2.0f*(lq1*lq2 - lq0*lq3);
    float r02 = 2.0f*(lq1*lq3 + lq0*lq2);
    float r10 = 2.0f*(lq1*lq2 + lq0*lq3);
    float r11 = 1.0f - 2.0f*(lq1*lq1 + lq3*lq3);
    float r12 = 2.0f*(lq2*lq3 - lq0*lq1);
    float r20 = 2.0f*(lq1*lq3 - lq0*lq2);
    float r21 = 2.0f*(lq2*lq3 + lq0*lq1);
    float r22 = 1.0f - 2.0f*(lq1*lq1 + lq2*lq2);

    // Auto-spin: advance longitude offset each frame
    static const float spin_speed[] = {0.0f, 0.0003f, 0.0008f, 0.002f}; // rad per ms
    static uint32_t last_spin_time = 0;
    if (last_spin_time == 0) last_spin_time = now;
    uint32_t spin_dt = now - last_spin_time;
    last_spin_time = now;
    if (cfg_earth_spin > 0) earth_auto_lon += spin_speed[cfg_earth_spin] * spin_dt;
    // Pre-compute spin rotation (around Y-axis)
    float slon = earth_auto_lon;
    float cs = cosf(slon), ss = sinf(slon);

    // Background — pure black
    lv_color_t bg_color; bg_color.full = 0;

    // Sun direction (fixed slightly upper-right for natural look)
    const float SUN_X = 0.6f, SUN_Y = 0.4f, SUN_Z = -0.7f; // normalised

    for(int cy = 0; cy < EARTH_DIAM; cy++) {
        float ey = -(cy - EARTH_RADIUS) / (float)EARTH_RADIUS;
        float ey2 = ey * ey;
        for(int cx = 0; cx < EARTH_DIAM; cx++) {
            float ex = (cx - EARTH_RADIUS) / (float)EARTH_RADIUS;
            float dist_sq = ex*ex + ey2;

            if (dist_sq <= 1.0f) {
                float ez = -fast_sqrt(1.0f - dist_sq);

                // Apply auto-spin then board rotation
                float sx = cs*ex - ss*ez;
                float sz = ss*ex + cs*ez;
                float rx = r00*sx  + r01*ey + r02*sz;
                float ry = r10*sx  + r11*ey + r12*sz;
                float rz = r20*sx  + r21*ey + r22*sz;

                float u = 0.5f + (fast_atan2(rz, rx) * 0.1591549f);
                float v = 0.5f - (fast_asin(ry)      * 0.3183098f);

                int tx = (int)(u * earth_width) % earth_width;
                if (tx < 0) tx += earth_width;
                int ty = (int)(v * earth_height);
                if (ty >= earth_height) ty = earth_height - 1;
                if (ty < 0) ty = 0;

                uint16_t color_val = earth_texture_map[ty * earth_width + tx];
                float orig_r = ((color_val >> 11) & 0x1F) * (1.0f/31.0f);
                float orig_g = ((color_val >> 5)  & 0x3F) * (1.0f/63.0f);
                float orig_b = ( color_val        & 0x1F) * (1.0f/31.0f);

                float r_f = orig_r, g_f = orig_g, b_f = orig_b;
                if (cfg_earth_theme == 1) { // Mars
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    r_f = lum * 1.5f; g_f = lum * 0.5f; b_f = lum * 0.2f;
                } else if (cfg_earth_theme == 2) { // Matrix
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    r_f = 0.0f; g_f = lum * 1.5f; b_f = 0.0f;
                } else if (cfg_earth_theme == 3) { // Ice
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    r_f = lum * 0.7f; g_f = lum * 1.2f; b_f = lum * 1.6f;
                } else if (cfg_earth_theme == 4) { // Vaporwave (Pink / Cyan)
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    if (orig_r < 0.25f && orig_b > 0.18f) { // ocean (cyan)
                        r_f = lum * 0.2f; g_f = lum * 1.5f; b_f = lum * 1.8f;
                    } else { // land (pink)
                        r_f = lum * 1.8f; g_f = lum * 0.5f; b_f = lum * 1.5f;
                    }
                } else if (cfg_earth_theme == 5) { // Noir (Grayscale)
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    r_f = lum; g_f = lum; b_f = lum;
                } else if (cfg_earth_theme == 6) { // Lava
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    if (orig_r < 0.25f && orig_b > 0.18f) { // ocean (lava)
                        r_f = 1.5f; g_f = 0.2f; b_f = 0.0f;
                    } else { // land (obsidian)
                        r_f = lum * 0.3f; g_f = lum * 0.3f; b_f = lum * 0.3f;
                    }
                } else if (cfg_earth_theme == 7) { // Gold (Sepia)
                    float lum = orig_r*0.3f + orig_g*0.59f + orig_b*0.11f;
                    r_f = lum * 1.6f; g_f = lum * 1.2f; b_f = lum * 0.4f;
                }

                // Lambertian diffuse (sun)
                float ndotl = ex*SUN_X + ey*SUN_Y + ez*SUN_Z; // surface normal = (ex,ey,ez)
                float diff = ndotl > 0.0f ? ndotl : 0.0f;
                // Ambient: 12% to keep night side visible, not black
                float amb = 0.12f;
                float light = amb + (1.0f - amb) * diff;

                // Soft terminator: smooth the day-night boundary
                float term = ndotl + 0.08f; // shift so terminator isn't a hard line
                if (term < 0.0f) term = 0.0f;
                if (term > 0.16f) term = 0.16f;
                float blend = term * (1.0f / 0.16f); // 0..1 over 8° band
                light = amb + (light - amb) * blend + (light) * (1.0f - blend) * 0.0f;
                // Remap with a subtle S-curve for more contrast
                light = light * light * (3.0f - 2.0f * light);

                // Specular highlight (Blinn-Phong, only on ocean — detect by low red on original map)
                float spec = 0.0f;
                if (orig_r < 0.25f && orig_b > 0.18f) { // ocean pixel
                    float hx = (SUN_X + 0.0f) * 0.5f, hy = (SUN_Y + 0.0f) * 0.5f, hz = (SUN_Z - 1.0f) * 0.5f;
                    float hlen = fast_rsqrt(hx*hx + hy*hy + hz*hz);
                    hx *= hlen; hy *= hlen; hz *= hlen;
                    float ndoth = ex*hx + ey*hy + ez*hz;
                    if (ndoth > 0.0f) {
                        spec = ndoth * ndoth; spec *= spec; spec *= spec; // ^8
                        spec *= 0.5f * diff; // scale with diffuse so no spec in dark
                    }
                }

                float fr = r_f * light + spec;
                float fg = g_f * light + spec * 0.95f;
                float fb = b_f * light + spec;

                // Limb darkening + atmospheric halo: pixels near the edge get tinted
                float limb = dist_sq; // 0 at centre, 1 at edge
                float halo_str = limb * limb; // stronger at rim
                
                if (cfg_earth_theme == 0) { // Normal Earth
                    fr = fr * (1.0f - halo_str * 0.5f);
                    fg = fg * (1.0f - halo_str * 0.3f);
                    fb = fb + halo_str * 0.18f;
                } else if (cfg_earth_theme == 1) { // Mars
                    fr = fr + halo_str * 0.2f;
                    fg = fg * (1.0f - halo_str * 0.3f);
                    fb = fb * (1.0f - halo_str * 0.5f);
                } else if (cfg_earth_theme == 2) { // Matrix
                    fg = fg + halo_str * 0.2f;
                } else if (cfg_earth_theme == 3) { // Ice
                    fr = fr * (1.0f - halo_str * 0.5f);
                    fg = fg + halo_str * 0.1f;
                    fb = fb + halo_str * 0.25f;
                } else if (cfg_earth_theme == 4) { // Vaporwave
                    fr = fr + halo_str * 0.2f;
                    fg = fg * (1.0f - halo_str * 0.5f);
                    fb = fb + halo_str * 0.2f;
                } else if (cfg_earth_theme == 5) { // Noir
                    // no atmosphere glow, just darkening
                    fr = fr * (1.0f - halo_str * 0.4f);
                    fg = fg * (1.0f - halo_str * 0.4f);
                    fb = fb * (1.0f - halo_str * 0.4f);
                } else if (cfg_earth_theme == 6) { // Lava
                    fr = fr + halo_str * 0.25f; // slight red glow
                    fg = fg * (1.0f - halo_str * 0.5f);
                    fb = fb * (1.0f - halo_str * 0.5f);
                } else if (cfg_earth_theme == 7) { // Gold
                    fr = fr + halo_str * 0.1f;
                    fg = fg + halo_str * 0.05f;
                    fb = fb * (1.0f - halo_str * 0.3f);
                }


                // Clamp
                if (fr > 1.0f) fr = 1.0f; if (fr < 0.0f) fr = 0.0f;
                if (fg > 1.0f) fg = 1.0f; if (fg < 0.0f) fg = 0.0f;
                if (fb > 1.0f) fb = 1.0f; if (fb < 0.0f) fb = 0.0f;

                uint8_t r_col = (uint8_t)(fr * 31.0f);
                uint8_t g_col = (uint8_t)(fg * 63.0f);
                uint8_t b_col = (uint8_t)(fb * 31.0f);

                lv_color_t c;
                uint16_t rgb565 = (r_col << 11) | (g_col << 5) | b_col;
                c.full = (rgb565 >> 8) | (rgb565 << 8); // byte-swap for LV_COLOR_16_SWAP
                earth_cbuf[cy * EARTH_DIAM + cx] = c;

            } else {
                // Thin atmospheric halo just outside the sphere edge
                float rim = dist_sq - 1.0f; // 0..small positive
                if (rim < 0.07f) {
                    float halo = 1.0f - rim * (1.0f / 0.07f);
                    halo = halo * halo; // quadratic falloff
                    uint8_t hr = 0, hg = 0, hb = 0;
                    if (cfg_earth_theme == 0) { hr = halo * 2.0f; hg = halo * 6.0f; hb = halo * 14.0f; } // Cyan-Blue
                    else if (cfg_earth_theme == 1) { hr = halo * 14.0f; hg = halo * 6.0f; hb = halo * 2.0f; } // Orange-Red
                    else if (cfg_earth_theme == 2) { hr = 0; hg = halo * 14.0f; hb = 0; } // Green
                    else if (cfg_earth_theme == 3) { hr = halo * 4.0f; hg = halo * 10.0f; hb = halo * 16.0f; } // Bright Cyan
                    else if (cfg_earth_theme == 4) { hr = halo * 14.0f; hg = 0; hb = halo * 14.0f; } // Pink/Magenta
                    else if (cfg_earth_theme == 5) { hr = halo * 4.0f; hg = halo * 4.0f; hb = halo * 4.0f; } // Gray
                    else if (cfg_earth_theme == 6) { hr = halo * 14.0f; hg = halo * 2.0f; hb = 0; } // Red
                    else if (cfg_earth_theme == 7) { hr = halo * 12.0f; hg = halo * 8.0f; hb = halo * 2.0f; } // Gold
                    
                    if (hr > 31) hr = 31; if (hg > 63) hg = 63; if (hb > 31) hb = 31;
                    
                    uint16_t hs = (hr << 11) | (hg << 5) | hb;
                    lv_color_t hc; hc.full = (hs >> 8) | (hs << 8);
                    earth_cbuf[cy * EARTH_DIAM + cx] = hc;
                } else {
                    earth_cbuf[cy * EARTH_DIAM + cx] = bg_color;
                }
            }
        }
    }

    // Draw polar axis sticks — white, 1px
    for (int sign = -1; sign <= 1; sign += 2) {
        for (float t = 1.02f; t <= 1.22f; t += 0.008f) {
            float param = sign * t;
            // North pole points in the Y column of R (earth Y-axis)
            float px = r01 * param;
            float py = -r11 * param;
            int ax2 = (int)(px * EARTH_RADIUS + EARTH_RADIUS);
            int ay2 = (int)(py * EARTH_RADIUS + EARTH_RADIUS);
            if (ax2 >= 0 && ax2 < EARTH_DIAM && ay2 >= 0 && ay2 < EARTH_DIAM) {
                lv_color_t wc;
                uint16_t w565 = (31 << 11) | (63 << 5) | 31; // white
                wc.full = (w565 >> 8) | (w565 << 8);
                earth_cbuf[ay2 * EARTH_DIAM + ax2] = wc;
            }
        }
    }

    lv_obj_invalidate(earth_canvas);
}

static bool example_notify_lvgl_flush_ready(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_io_event_data_t *edata, void *user_ctx) {
    lv_disp_flush_ready(&disp_drv);
    return false;
}

static void example_increase_lvgl_tick(void *arg) {
    lv_tick_inc(EXAMPLE_LVGL_TICK_PERIOD_MS);
}

static void example_lvgl_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map) {
    esp_lcd_panel_draw_bitmap(panel_handle, area->x1, area->y1, area->x2 + 1, area->y2 + 1, color_map);
}

static void gui_task(void *param) {
    uint32_t last_earth_draw = 0;
    while(1) {
        uint32_t now_gui = xTaskGetTickCount() * portTICK_PERIOD_MS;
        if(lvgl_lock(10)) {
            lv_timer_handler();
            // Render earth at up to ~60fps from gui_task (not IMU task)
            // This decouples rendering from sensor polling
            if (now_gui - last_earth_draw >= 16) { // ~60fps cap
                last_earth_draw = now_gui;
                render_earth_frame(now_gui);
            }
            lvgl_unlock();
        }
        vTaskDelay(pdMS_TO_TICKS(5)); // ~200Hz gui loop, let LVGL flush freely
    }
}

void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_flash_init();
    }

    load_settings(); // Load settings early to get cfg_device_id

    // Generate unique MAC from factory MAC based on active device channel
    uint8_t base_mac[6];
    if (esp_read_mac(base_mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        base_mac[5] ^= (0x0F + cfg_device_id); // Offset based on active channel (1, 2, or 3)
        esp_base_mac_addr_set(base_mac);
    }
    
    lvgl_api_mux = xSemaphoreCreateRecursiveMutex();
    esp_event_loop_create_default();
    
    gpio_reset_pin(EXAMPLE_PIN_NUM_BK_LIGHT);
    gpio_set_direction(EXAMPLE_PIN_NUM_BK_LIGHT, GPIO_MODE_OUTPUT);
    gpio_set_level(EXAMPLE_PIN_NUM_BK_LIGHT, 1);
 
    lv_init();
    ble_mouse_init(cfg_device_id); // Initialize BLE with device channel ID
    imu_init();

    // Init SPI/LCD
    spi_bus_config_t buscfg = { .sclk_io_num=EXAMPLE_PIN_NUM_SCLK, .mosi_io_num=EXAMPLE_PIN_NUM_MOSI, .miso_io_num=EXAMPLE_PIN_NUM_MISO, .quadwp_io_num=-1, .quadhd_io_num=-1, .max_transfer_sz=240*80*2 }; // Must match draw buffer size
    spi_bus_initialize(EXAMPLE_SPI_HOST, &buscfg, SPI_DMA_CH_AUTO);
    esp_lcd_panel_io_handle_t io_handle;
    esp_lcd_panel_io_spi_config_t io_config = { .dc_gpio_num=EXAMPLE_PIN_NUM_LCD_DC, .cs_gpio_num=EXAMPLE_PIN_NUM_LCD_CS, .pclk_hz=EXAMPLE_LCD_PIXEL_CLOCK_HZ, .lcd_cmd_bits=8, .lcd_param_bits=8, .spi_mode=0, .trans_queue_depth=10, .on_color_trans_done=example_notify_lvgl_flush_ready };
    esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)EXAMPLE_SPI_HOST, &io_config, &io_handle);
    esp_lcd_panel_dev_config_t panel_config = { .reset_gpio_num=EXAMPLE_PIN_NUM_LCD_RST, .rgb_ele_order=LCD_RGB_ELEMENT_ORDER_RGB, .bits_per_pixel=16 };
    esp_lcd_new_panel_st7789(io_handle, &panel_config, &panel_handle);
    esp_lcd_panel_reset(panel_handle);
    esp_lcd_panel_init(panel_handle);
    esp_lcd_panel_mirror(panel_handle, false, false);
    esp_lcd_panel_swap_xy(panel_handle, false);
    esp_lcd_panel_disp_on_off(panel_handle, true);
    esp_lcd_panel_invert_color(panel_handle, true);

    static lv_disp_draw_buf_t draw_buf;
    lv_color_t *buf1 = heap_caps_malloc(240*80*2, MALLOC_CAP_DMA); // Reverted to SRAM for SPI DMA
    lv_color_t *buf2 = heap_caps_malloc(240*80*2, MALLOC_CAP_DMA);
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, 240*80);
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = 240; disp_drv.ver_res = 320;
    disp_drv.flush_cb = example_lvgl_flush_cb;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);

    const esp_timer_create_args_t lvgl_tick_timer_args = { .callback=&example_increase_lvgl_tick, .name="lvgl_tick" };
    esp_timer_handle_t lvgl_tick_timer;
    esp_timer_create(&lvgl_tick_timer_args, &lvgl_tick_timer);
    esp_timer_start_periodic(lvgl_tick_timer, 2 * 1000);

    build_ui(lv_scr_act());

    xTaskCreatePinnedToCore(gui_task, "gui", 1024*10, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(hardware_input_task, "hw", 1024*10, NULL, 6, NULL, 0);
}
