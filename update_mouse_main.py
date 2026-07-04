with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add #include "ble_mouse.h"
code = code.replace('#include "nvs_flash.h"', '#include "nvs_flash.h"\n#include "ble_mouse.h"')

# 2. Add mouse_info_label definition
code = code.replace('lv_obj_t *btn_calib;', 'lv_obj_t *btn_calib;\nlv_obj_t *mouse_info_label;')

# 3. Create mouse_info_label in UI init
ui_label_new = """mouse_info_label = lv_label_create(parent);
    lv_label_set_text(mouse_info_label, "AIR MOUSE ACTIVE\\n\\nTilt board to move\\n\\nBOOT Button:\\n- Single Click: Left Click\\n- Double Click: Right Click\\n- Long Press: Exit");
    lv_obj_align(mouse_info_label, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(mouse_info_label, lv_color_hex(0x00FFFF), 0);
    lv_obj_set_style_text_align(mouse_info_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);

    bat_label = lv_label_create(parent);"""
code = code.replace('bat_label = lv_label_create(parent);', ui_label_new)

# 4. Initialize BLE Mouse in app_main
code = code.replace('lv_init();', 'lv_init();\n    ble_mouse_init();')

# 5. Update imu_task to send BLE reports
imu_task_old = """            } else if (mouse_active) {
                float x = gx - gyro_off_x;
                float y = gy - gyro_off_y;
                float z = gz - gyro_off_z;
                if (fabs(x) > 50 || fabs(y) > 50 || fabs(z) > 50) {
                    // Send to BLE / Print
                    ESP_LOGI(TAG, "Air Mouse: dX=%.1f, dY=%.1f", x, y);
                }
            }"""

imu_task_new = """            } else if (mouse_active) {
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
            }"""
code = code.replace(imu_task_old, imu_task_new)

# 6. Update handle_button_event to handle STATE_MOUSE
event_old = """                } else if (menu_hover_index == 2) {
                    mouse_active = !mouse_active;
                    update_menu_focus();
                }"""

event_new = """                } else if (menu_hover_index == 2) {
                    current_state = STATE_MOUSE;
                    mouse_active = true;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                }"""
code = code.replace(event_old, event_new)

# Update back action
back_old = """            if (event == 2) { // BACK
                current_state = STATE_MENU;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(img_camera, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(server_info_label, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                is_calibrating = false;
            }"""

back_new = """            if (event == 2) { // BACK
                current_state = STATE_MENU;
                mouse_active = false;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(img_camera, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(server_info_label, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(calib_label, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                is_calibrating = false;
            }"""
code = code.replace(back_old, back_new)

# Handle clicks in STATE_MOUSE
state_mouse_handler = """        if (current_state == STATE_MOUSE) {
            if (event == 0) { // Single click: Left Click
                ble_mouse_send_report(0, 0, 1);
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 2) { // Double click: Right Click
                ble_mouse_send_report(0, 0, 2);
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 1) { // Long press: Back to menu
                current_state = STATE_MENU;
                mouse_active = false;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
            }
            lvgl_unlock();
            return;
        }"""

# Insert state_mouse_handler at the beginning of handle_button_event
code = code.replace("if (lvgl_lock(-1)) {", "if (lvgl_lock(-1)) {\n" + state_mouse_handler)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully updated main.c with BLE Mouse support")
