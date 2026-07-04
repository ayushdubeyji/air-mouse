import re

with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update State Enum to include STATE_SETTINGS
code = re.sub(
    r'typedef enum\s*\{.*?\}\s*app_state_t;',
    '''typedef enum {
    STATE_MENU,
    STATE_LOCAL_FEED,
    STATE_SERVER,
    STATE_MOUSE,
    STATE_CALIBRATE,
    STATE_SETTINGS
} app_state_t;''',
    code,
    flags=re.DOTALL
)

# 2. Add Settings Global Variables and NVS functions
settings_globals = """
#include "nvs.h"

static bool cfg_invert_x = false;
static bool cfg_invert_y = false;
static bool cfg_swap_xy = false;
static float cfg_sensitivity = 1.5f;
static float cfg_deadzone = 25.0f;

static void save_settings(void) {
    nvs_handle_t my_handle;
    if (nvs_open("storage", NVS_READWRITE, &my_handle) == ESP_OK) {
        nvs_set_u8(my_handle, "inv_x", cfg_invert_x ? 1 : 0);
        nvs_set_u8(my_handle, "inv_y", cfg_invert_y ? 1 : 0);
        nvs_set_u8(my_handle, "swap_xy", cfg_swap_xy ? 1 : 0);
        nvs_set_i32(my_handle, "sens", (int32_t)(cfg_sensitivity * 100));
        nvs_set_i32(my_handle, "dead", (int32_t)cfg_deadzone);
        nvs_commit(my_handle);
        nvs_close(my_handle);
    }
}

static void load_settings(void) {
    nvs_handle_t my_handle;
    if (nvs_open("storage", NVS_READONLY, &my_handle) == ESP_OK) {
        uint8_t val8;
        int32_t val32;
        if (nvs_get_u8(my_handle, "inv_x", &val8) == ESP_OK) cfg_invert_x = (val8 == 1);
        if (nvs_get_u8(my_handle, "inv_y", &val8) == ESP_OK) cfg_invert_y = (val8 == 1);
        if (nvs_get_u8(my_handle, "swap_xy", &val8) == ESP_OK) cfg_swap_xy = (val8 == 1);
        if (nvs_get_i32(my_handle, "sens", &val32) == ESP_OK) cfg_sensitivity = val32 / 100.0f;
        if (nvs_get_i32(my_handle, "dead", &val32) == ESP_OK) cfg_deadzone = (float)val32;
        nvs_close(my_handle);
    }
}
"""

# Place it right after QMI8658 static variables
code = code.replace(
    'static bool mouse_active = false;',
    'static bool mouse_active = false;\n' + settings_globals
)

# 3. Add Settings UI Declarations
code = code.replace(
    'lv_obj_t *mouse_info_label;',
    """lv_obj_t *mouse_info_label;
lv_obj_t *btn_settings;
lv_obj_t *settings_container;
lv_obj_t *lbl_cfg_inv_x;
lv_obj_t *lbl_cfg_inv_y;
lv_obj_t *lbl_cfg_swap_xy;
lv_obj_t *lbl_cfg_sens;
lv_obj_t *lbl_cfg_dead;
lv_obj_t *lbl_cfg_calib;
lv_obj_t *lbl_cfg_back;
"""
)

# 4. Modify imu_task for fast calibration and advanced sigmoid curve mapping
imu_task_old = """static void imu_task(void *param) {
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
                // Pitch/Roll mapping to Mouse X/Y
                float dx_gyro = -(gz - gyro_off_z) / 80.0f;
                float dy_gyro = (gx - gyro_off_x) / 80.0f;
                
                int8_t dx = 0;
                int8_t dy = 0;
                
                if (fabs(dx_gyro) > 1.0f) dx = (int8_t)dx_gyro;
                if (fabs(dy_gyro) > 1.0f) dy = (int8_t)dy_gyro;
                
                if (dx != 0 || dy != 0) {
                    ble_mouse_send_report(dx, dy, 0);
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}"""

imu_task_new = """static void imu_task(void *param) {
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
                if (calib_count >= 40) { // Reduced to 40 samples (takes only 400ms)
                    gyro_off_x = sum_gx / 40.0f;
                    gyro_off_y = sum_gy / 40.0f;
                    gyro_off_z = sum_gz / 40.0f;
                    is_calibrating = false;
                    calib_count = 0;
                    sum_gx = 0; sum_gy = 0; sum_gz = 0;
                    ESP_LOGI(TAG, "IMU Calibrated!");
                    // Auto go back to menu/settings
                    if (current_state == STATE_CALIBRATE) {
                        current_state = STATE_SETTINGS;
                        if (lvgl_lock(-1)) {
                            lv_obj_clear_flag(settings_container, LV_OBJ_FLAG_HIDDEN);
                            lv_obj_add_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                            lvgl_unlock();
                        }
                    }
                }
            } else if (mouse_active) {
                float raw_x = -(gz - gyro_off_z);
                float raw_y = (gx - gyro_off_x);

                if (cfg_swap_xy) {
                    float tmp = raw_x;
                    raw_x = raw_y;
                    raw_y = tmp;
                }

                if (cfg_invert_x) raw_x = -raw_x;
                if (cfg_invert_y) raw_y = -raw_y;

                float dx_val = 0;
                float dy_val = 0;

                // Advanced Sigmoid-like power curve mapping to filter jitter
                float abs_x = fabs(raw_x);
                if (abs_x > cfg_deadzone) {
                    dx_val = copysignf(powf(abs_x - cfg_deadzone, 1.35f) * cfg_sensitivity * 0.005f, raw_x);
                }

                float abs_y = fabs(raw_y);
                if (abs_y > cfg_deadzone) {
                    dy_val = copysignf(powf(abs_y - cfg_deadzone, 1.35f) * cfg_sensitivity * 0.005f, raw_y);
                }

                int32_t final_dx = (int32_t)dx_val;
                int32_t final_dy = (int32_t)dy_val;
                if (final_dx > 127) final_dx = 127;
                if (final_dx < -127) final_dx = -127;
                if (final_dy > 127) final_dy = 127;
                if (final_dy < -127) final_dy = -127;

                int8_t dx = (int8_t)final_dx;
                int8_t dy = (int8_t)final_dy;
                
                if (dx != 0 || dy != 0) {
                    ble_mouse_send_report(dx, dy, 0);
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10)); // 100Hz updates for high responsiveness
    }
}"""
code = code.replace(imu_task_old, imu_task_new)

# 5. Initialize settings load in app_main
code = code.replace(
    'ble_mouse_init();',
    'ble_mouse_init();\n    load_settings();'
)

# 6. Update UI Init to create the Settings Screen
ui_init_old = """    btn_calib = lv_btn_create(list);
    lv_obj_set_size(btn_calib, 180, 40);
    lv_obj_t *lbl_calib = lv_label_create(btn_calib);
    lv_label_set_text(lbl_calib, "4. Calibrate IMU");
    lv_obj_center(lbl_calib);"""

ui_init_new = """    btn_calib = lv_btn_create(list);
    lv_obj_set_size(btn_calib, 180, 40);
    lv_obj_t *lbl_calib = lv_label_create(btn_calib);
    lv_label_set_text(lbl_calib, "4. Calibrate IMU");
    lv_obj_center(lbl_calib);

    btn_settings = lv_btn_create(list);
    lv_obj_set_size(btn_settings, 180, 40);
    lv_obj_t *lbl_settings = lv_label_create(btn_settings);
    lv_label_set_text(lbl_settings, "5. Settings");
    lv_obj_center(lbl_settings);

    // Settings container
    settings_container = lv_obj_create(parent);
    lv_obj_set_size(settings_container, lv_pct(100), lv_pct(100));
    lv_obj_align(settings_container, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_bg_color(settings_container, lv_color_hex(0x1a1a1a), 0);
    lv_obj_set_style_pad_all(settings_container, 10, 0);
    lv_obj_add_flag(settings_container, LV_OBJ_FLAG_HIDDEN);

    lv_obj_t *cfg_title = lv_label_create(settings_container);
    lv_label_set_text(cfg_title, "CONFIG & AXIS SETTINGS");
    lv_obj_align(cfg_title, LV_ALIGN_TOP_MID, 0, 5);
    lv_obj_set_style_text_color(cfg_title, lv_color_hex(0xFFFF00), 0);

    lv_obj_t *cfg_list = lv_obj_create(settings_container);
    lv_obj_set_size(cfg_list, lv_pct(100), lv_pct(85));
    lv_obj_align(cfg_list, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(cfg_list, lv_color_hex(0x1a1a1a), 0);
    lv_obj_set_style_border_width(cfg_list, 0, 0);
    lv_obj_set_flex_flow(cfg_list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(cfg_list, 5, 0);

    lbl_cfg_inv_x = lv_label_create(cfg_list);
    lbl_cfg_inv_y = lv_label_create(cfg_list);
    lbl_cfg_swap_xy = lv_label_create(cfg_list);
    lbl_cfg_sens = lv_label_create(cfg_list);
    lbl_cfg_dead = lv_label_create(cfg_list);
    lbl_cfg_calib = lv_label_create(cfg_list);
    lbl_cfg_back = lv_label_create(cfg_list);"""
code = code.replace(ui_init_old, ui_init_new)

# 7. Add Update Configurations Text Helper Function
update_cfg_text_func = """
static void update_settings_labels(void) {
    lv_label_set_text_fmt(lbl_cfg_inv_x, "Invert X: %s", cfg_invert_x ? "ON" : "OFF");
    lv_label_set_text_fmt(lbl_cfg_inv_y, "Invert Y: %s", cfg_invert_y ? "ON" : "OFF");
    lv_label_set_text_fmt(lbl_cfg_swap_xy, "Swap X/Y: %s", cfg_swap_xy ? "ON" : "OFF");
    lv_label_set_text_fmt(lbl_cfg_sens, "Sensitivity: %.2f", cfg_sensitivity);
    lv_label_set_text_fmt(lbl_cfg_dead, "Deadzone: %.0f", cfg_deadzone);
    lv_label_set_text(lbl_cfg_calib, "[ Calibrate Gyro ]");
    lv_label_set_text(lbl_cfg_back, "[ Save & Back ]");
}
"""
code = code.replace("static void update_menu_focus(void)", update_cfg_text_func + "\nstatic void update_menu_focus(void)")

# 8. Update Menu and Settings Focus System
focus_system_old = """static void update_menu_focus(void)
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

focus_system_new = """static void update_menu_focus(void)
{
    if (current_state == STATE_MENU) {
        lv_obj_set_style_bg_color(btn_local, lv_color_hex(0x555555), 0);
        lv_obj_set_style_bg_color(btn_server, lv_color_hex(0x555555), 0);
        lv_obj_set_style_bg_color(btn_mouse, lv_color_hex(0x555555), 0);
        lv_obj_set_style_bg_color(btn_calib, lv_color_hex(0x555555), 0);
        lv_obj_set_style_bg_color(btn_settings, lv_color_hex(0x555555), 0);

        lv_obj_t *target = NULL;
        if (menu_hover_index == 0) target = btn_local;
        else if (menu_hover_index == 1) target = btn_server;
        else if (menu_hover_index == 2) target = btn_mouse;
        else if (menu_hover_index == 3) target = btn_calib;
        else if (menu_hover_index == 4) target = btn_settings;

        if (target) {
            lv_obj_set_style_bg_color(target, lv_color_hex(0x00FF00), 0);
        }
    } else if (current_state == STATE_SETTINGS) {
        // Clear all text styles in settings
        lv_obj_set_style_text_color(lbl_cfg_inv_x, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_color(lbl_cfg_inv_y, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_color(lbl_cfg_swap_xy, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_color(lbl_cfg_sens, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_color(lbl_cfg_dead, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_color(lbl_cfg_calib, lv_color_hex(0x8888FF), 0);
        lv_obj_set_style_text_color(lbl_cfg_back, lv_color_hex(0x88FF88), 0);

        lv_obj_t *target = NULL;
        if (menu_hover_index == 0) target = lbl_cfg_inv_x;
        else if (menu_hover_index == 1) target = lbl_cfg_inv_y;
        else if (menu_hover_index == 2) target = lbl_cfg_swap_xy;
        else if (menu_hover_index == 3) target = lbl_cfg_sens;
        else if (menu_hover_index == 4) target = lbl_cfg_dead;
        else if (menu_hover_index == 5) target = lbl_cfg_calib;
        else if (menu_hover_index == 6) target = lbl_cfg_back;

        if (target) {
            lv_obj_set_style_text_color(target, lv_color_hex(0x00FF00), 0);
        }
    }
}"""
code = code.replace(focus_system_old, focus_system_new)

# 9. Update click boundaries (mod 4 -> mod 5 in main menu, and settings boundary is mod 7)
code = code.replace(
    'menu_hover_index = (menu_hover_index + 1) % 4;',
    """if (current_state == STATE_MENU) {
                    menu_hover_index = (menu_hover_index + 1) % 5;
                } else if (current_state == STATE_SETTINGS) {
                    menu_hover_index = (menu_hover_index + 1) % 7;
                }"""
)

# 10. Update Handle Button Enter Event in Main Menu & Settings Mode
enter_event_old = """                if (menu_hover_index == 0) {
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
                    current_state = STATE_MOUSE;
                    mouse_active = true;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                } else if (menu_hover_index == 3) {
                    current_state = STATE_CALIBRATE;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                    is_calibrating = true;
                }"""

enter_event_new = """                if (menu_hover_index == 0) {
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
                    current_state = STATE_MOUSE;
                    mouse_active = true;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                } else if (menu_hover_index == 3) {
                    current_state = STATE_CALIBRATE;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                    is_calibrating = true;
                } else if (menu_hover_index == 4) {
                    current_state = STATE_SETTINGS;
                    menu_hover_index = 0;
                    update_settings_labels();
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(settings_container, LV_OBJ_FLAG_HIDDEN);
                    update_menu_focus();
                }"""
code = code.replace(enter_event_old, enter_event_new)

# Add Settings State Enter Action to handle_button_event
settings_action_handler = """        if (current_state == STATE_SETTINGS) {
            if (event == 0) { // HOVER next config item
                menu_hover_index = (menu_hover_index + 1) % 7;
                update_menu_focus();
            } else if (event == 1) { // ENTER/TOGGLE config item
                if (menu_hover_index == 0) cfg_invert_x = !cfg_invert_x;
                else if (menu_hover_index == 1) cfg_invert_y = !cfg_invert_y;
                else if (menu_hover_index == 2) cfg_swap_xy = !cfg_swap_xy;
                else if (menu_hover_index == 3) {
                    cfg_sensitivity += 0.5f;
                    if (cfg_sensitivity > 4.0f) cfg_sensitivity = 0.5f;
                }
                else if (menu_hover_index == 4) {
                    cfg_deadzone += 10.0f;
                    if (cfg_deadzone > 60.0f) cfg_deadzone = 10.0f;
                }
                else if (menu_hover_index == 5) {
                    current_state = STATE_CALIBRATE;
                    lv_obj_add_flag(settings_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                    is_calibrating = true;
                }
                else if (menu_hover_index == 6) {
                    save_settings();
                    current_state = STATE_MENU;
                    menu_hover_index = 4; // Back to Settings option
                    lv_obj_add_flag(settings_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    update_menu_focus();
                }
                update_settings_labels();
            } else if (event == 2) { // BACK
                save_settings();
                current_state = STATE_MENU;
                menu_hover_index = 4;
                lv_obj_add_flag(settings_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                update_menu_focus();
            }
            lvgl_unlock();
            return;
        }"""
code = code.replace(
    'if (current_state == STATE_MOUSE) {',
    settings_action_handler + '\n        if (current_state == STATE_MOUSE) {'
)

# Fix back action to include settings container
code = code.replace(
    'lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);',
    'lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);\n                lv_obj_add_flag(settings_container, LV_OBJ_FLAG_HIDDEN);'
)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully updated main.c with Calibration Config Settings Screen")
