import re

with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add math.h
code = code.replace('#include "nvs_flash.h"', '#include "nvs_flash.h"\n#include <math.h>')

# 2. Add IMU Definitions and Variables
imu_code = """
#define QMI8658_ADDR 0x6B
static float gyro_off_x = 0, gyro_off_y = 0, gyro_off_z = 0;
static bool is_calibrating = false;
static bool mouse_active = false;

static esp_err_t i2c_write_reg(uint8_t reg, uint8_t data) {
    uint8_t write_buf[2] = {reg, data};
    return i2c_master_write_to_device(EXAMPLE_I2C_NUM, QMI8658_ADDR, write_buf, 2, pdMS_TO_TICKS(100));
}
static esp_err_t i2c_read_reg(uint8_t reg, uint8_t *data, size_t len) {
    return i2c_master_write_read_device(EXAMPLE_I2C_NUM, QMI8658_ADDR, &reg, 1, data, len, pdMS_TO_TICKS(100));
}

static void imu_init(void) {
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = EXAMPLE_PIN_NUM_I2C_SDA,
        .scl_io_num = EXAMPLE_PIN_NUM_I2C_SCL,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = 400000,
    };
    i2c_param_config(EXAMPLE_I2C_NUM, &conf);
    i2c_driver_install(EXAMPLE_I2C_NUM, conf.mode, 0, 0, 0);

    uint8_t id = 0;
    i2c_read_reg(0x00, &id, 1);
    if (id == 0x05) {
        ESP_LOGI(TAG, "QMI8658 found!");
        i2c_write_reg(0x02, 0x60); // CTRL1
        i2c_write_reg(0x03, 0x24); // CTRL2
        i2c_write_reg(0x04, 0x64); // CTRL3
        i2c_write_reg(0x08, 0x03); // CTRL7
    } else {
        ESP_LOGE(TAG, "QMI8658 not found! ID: 0x%02X", id);
    }
}

static void imu_task(void *param) {
    uint8_t data[12];
    int calib_count = 0;
    long sum_gx = 0, sum_gy = 0, sum_gz = 0;

    while(1) {
        if (i2c_read_reg(0x35, data, 12) == ESP_OK) {
            int16_t gx = (data[7] << 8) | data[6];
            int16_t gy = (data[9] << 8) | data[8];
            int16_t gz = (data[11] << 8) | data[10];

            if (is_calibrating) {
                sum_gx += gx; sum_gy += gy; sum_gz += gz;
                calib_count++;
                if (calib_count >= 100) {
                    gyro_off_x = sum_gx / 100.0f;
                    gyro_off_y = sum_gy / 100.0f;
                    gyro_off_z = sum_gz / 100.0f;
                    is_calibrating = false;
                    calib_count = 0;
                    sum_gx = 0; sum_gy = 0; sum_gz = 0;
                    ESP_LOGI(TAG, "IMU Calibrated!");
                }
            } else if (mouse_active) {
                float x = gx - gyro_off_x;
                float y = gy - gyro_off_y;
                float z = gz - gyro_off_z;
                if (fabs(x) > 50 || fabs(y) > 50 || fabs(z) > 50) {
                    // Send to BLE / Print
                    ESP_LOGI(TAG, "Air Mouse: dX=%.1f, dY=%.1f", x, y);
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
"""
code = code.replace('bool lvgl_lock(int timeout_ms)', imu_code + '\nbool lvgl_lock(int timeout_ms)')

# 3. Add App States and Menu Items
code = code.replace('STATE_SERVER\n} app_state_t;', 'STATE_SERVER,\n    STATE_MOUSE,\n    STATE_CALIBRATE\n} app_state_t;')
code = code.replace('lv_obj_t *btn_server;', 'lv_obj_t *btn_server;\nlv_obj_t *btn_mouse;\nlv_obj_t *btn_calib;\nlv_obj_t *calib_label;')

# 4. Update init tasks
code = code.replace('camera_init();', 'camera_init();\n    imu_init();')
code = code.replace('xTaskCreatePinnedToCore(button_task, "button_task", 1024 * 3, NULL, 1, NULL, 0);', 'xTaskCreatePinnedToCore(button_task, "button_task", 1024 * 3, NULL, 1, NULL, 0);\n    xTaskCreatePinnedToCore(imu_task, "imu_task", 1024 * 4, NULL, 1, NULL, 0);')

# 5. Update UI Init
ui_old = """    // Local Feed Button
    btn_local = lv_obj_create(menu_container);
    lv_obj_set_size(btn_local, 180, 50);
    lv_obj_align(btn_local, LV_ALIGN_CENTER, 0, -35);

    lv_obj_t *lbl_local = lv_label_create(btn_local);
    lv_label_set_text(lbl_local, "1. Local Feed");
    lv_obj_align(lbl_local, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(lbl_local, lv_color_hex(0xFFFFFF), 0);

    // Server Button
    btn_server = lv_obj_create(menu_container);
    lv_obj_set_size(btn_server, 180, 50);
    lv_obj_align(btn_server, LV_ALIGN_CENTER, 0, 35);

    lv_obj_t *lbl_server = lv_label_create(btn_server);
    lv_label_set_text(lbl_server, "2. Camera Server");
    lv_obj_align(lbl_server, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(lbl_server, lv_color_hex(0xFFFFFF), 0);"""

ui_new = """    // List layout for menu
    lv_obj_t *list = lv_obj_create(menu_container);
    lv_obj_set_size(list, lv_pct(100), lv_pct(80));
    lv_obj_align(list, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(list, lv_color_hex(0x222222), 0);
    lv_obj_set_style_border_width(list, 0, 0);
    lv_obj_set_flex_flow(list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(list, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_all(list, 5, 0);

    btn_local = lv_btn_create(list);
    lv_obj_set_size(btn_local, 180, 40);
    lv_obj_t *lbl_local = lv_label_create(btn_local);
    lv_label_set_text(lbl_local, "1. Local Feed");
    lv_obj_center(lbl_local);

    btn_server = lv_btn_create(list);
    lv_obj_set_size(btn_server, 180, 40);
    lv_obj_t *lbl_server = lv_label_create(btn_server);
    lv_label_set_text(lbl_server, "2. Camera Server");
    lv_obj_center(lbl_server);

    btn_mouse = lv_btn_create(list);
    lv_obj_set_size(btn_mouse, 180, 40);
    lv_obj_t *lbl_mouse = lv_label_create(btn_mouse);
    lv_label_set_text(lbl_mouse, "3. Air Mouse Toggle");
    lv_obj_center(lbl_mouse);

    btn_calib = lv_btn_create(list);
    lv_obj_set_size(btn_calib, 180, 40);
    lv_obj_t *lbl_calib = lv_label_create(btn_calib);
    lv_label_set_text(lbl_calib, "4. Calibrate IMU");
    lv_obj_center(lbl_calib);"""
code = code.replace(ui_old, ui_new)

# Add calib label
code = code.replace('bat_label = lv_label_create(parent);', 'calib_label = lv_label_create(parent);\nlv_label_set_text(calib_label, "Calibrating IMU...\\nPlease keep still.");\nlv_obj_align(calib_label, LV_ALIGN_CENTER, 0, 0);\nlv_obj_set_style_text_color(calib_label, lv_color_hex(0xFFFF00), 0);\nlv_obj_add_flag(calib_label, LV_OBJ_FLAG_HIDDEN);\nbat_label = lv_label_create(parent);')

# 6. Update focus
focus_old = """static void update_menu_focus(void)
{
    if (menu_hover_index == 0) {
        lv_obj_set_style_bg_color(btn_local, lv_color_hex(0x00FF00), 0);
        lv_obj_set_style_bg_color(btn_server, lv_color_hex(0x555555), 0);
    } else {
        lv_obj_set_style_bg_color(btn_local, lv_color_hex(0x555555), 0);
        lv_obj_set_style_bg_color(btn_server, lv_color_hex(0x00FF00), 0);
    }
}"""
focus_new = """static void update_menu_focus(void)
{
    lv_obj_set_style_bg_color(btn_local, lv_color_hex(0x555555), 0);
    lv_obj_set_style_bg_color(btn_server, lv_color_hex(0x555555), 0);
    lv_obj_set_style_bg_color(btn_mouse, lv_color_hex(0x555555), 0);
    lv_obj_set_style_bg_color(btn_calib, lv_color_hex(0x555555), 0);

    lv_obj_t *target = NULL;
    if (menu_hover_index == 0) target = btn_local;
    else if (menu_hover_index == 1) target = btn_server;
    else if (menu_hover_index == 2) target = btn_mouse;
    else if (menu_hover_index == 3) target = btn_calib;

    if (target) {
        lv_obj_set_style_bg_color(target, lv_color_hex(0x00FF00), 0);
        if (mouse_active && target == btn_mouse) {
             lv_obj_set_style_bg_color(target, lv_color_hex(0xFF8800), 0); // Orange if ON
        }
    }
    
    // Highlight mouse button if active regardless of focus
    if (mouse_active && menu_hover_index != 2) {
         lv_obj_set_style_bg_color(btn_mouse, lv_color_hex(0x884400), 0);
    }
}"""
code = code.replace(focus_old, focus_new)

# 7. Update handle event
event_old = """                menu_hover_index = (menu_hover_index + 1) % 2;"""
event_new = """                menu_hover_index = (menu_hover_index + 1) % 4;"""
code = code.replace(event_old, event_new)

event_enter_old = """                if (menu_hover_index == 0) {
                    current_state = STATE_LOCAL_FEED;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(img_camera, LV_OBJ_FLAG_HIDDEN);
                } else {
                    current_state = STATE_SERVER;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(server_info_label, LV_OBJ_FLAG_HIDDEN);
                    if (!camera_web_server) {
                        wifi_init_softap();
                        camera_web_server = start_webserver();
                    }
                }"""
event_enter_new = """                if (menu_hover_index == 0) {
                    current_state = STATE_LOCAL_FEED;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(img_camera, LV_OBJ_FLAG_HIDDEN);
                } else if (menu_hover_index == 1) {
                    current_state = STATE_SERVER;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(server_info_label, LV_OBJ_FLAG_HIDDEN);
                    if (!camera_web_server) {
                        wifi_init_softap();
                        camera_web_server = start_webserver();
                    }
                } else if (menu_hover_index == 2) {
                    mouse_active = !mouse_active;
                    update_menu_focus();
                } else if (menu_hover_index == 3) {
                    current_state = STATE_CALIBRATE;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                    is_calibrating = true;
                }"""
code = code.replace(event_enter_old, event_enter_new)

event_back_old = """            if (event == 2) { // BACK
                current_state = STATE_MENU;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(img_camera, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(server_info_label, LV_OBJ_FLAG_HIDDEN);
            }"""
event_back_new = """            if (event == 2) { // BACK
                current_state = STATE_MENU;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(img_camera, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(server_info_label, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                is_calibrating = false;
            }"""
code = code.replace(event_back_old, event_back_new)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated main.c")
