import re

with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace Camera Pins with correct Waveshare definitions
camera_pins_old = """#define Y9_GPIO_NUM 2
#define Y8_GPIO_NUM 7
#define Y7_GPIO_NUM 10
#define Y6_GPIO_NUM 14
#define Y5_GPIO_NUM 11
#define Y4_GPIO_NUM 15
#define Y3_GPIO_NUM 13
#define Y2_GPIO_NUM 12
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM 4
#define PCLK_GPIO_NUM 9"""

camera_pins_new = """#define Y9_GPIO_NUM 12
#define Y8_GPIO_NUM 14
#define Y7_GPIO_NUM 15
#define Y6_GPIO_NUM 16
#define Y5_GPIO_NUM 18
#define Y4_GPIO_NUM 20
#define Y3_GPIO_NUM 22
#define Y2_GPIO_NUM 19
#define VSYNC_GPIO_NUM 7
#define HREF_GPIO_NUM 9
#define PCLK_GPIO_NUM 17"""

code = code.replace(camera_pins_old, camera_pins_new)

# Re-define top camera configs
camera_top_old = """#define PWDN_GPIO_NUM 17  // power down is not used
#define RESET_GPIO_NUM -1 // software reset will be performed
#define XCLK_GPIO_NUM 8
#define SIOD_GPIO_NUM 21
#define SIOC_GPIO_NUM 16"""

camera_top_new = """#define PWDN_GPIO_NUM 8
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 13
#define SIOD_GPIO_NUM 11
#define SIOC_GPIO_NUM 10"""

code = code.replace(camera_top_old, camera_top_new)

# 2. Fix QMI8658 I2C auto-increment configuration (CTRL1 should be 0x01, not 0x60)
code = code.replace(
    'i2c_write_reg(0x02, 0x60); // CTRL1',
    'i2c_write_reg(0x02, 0x01); // CTRL1: Little Endian + Auto-Increment'
)

# 3. Update button task to support Triple Click
button_task_old = """        if (click_count > 0 && !pressed) {
            uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;
            if (now - last_press_time > 400) {
                if (click_count == 1) {
                    handle_button_event(0); // HOVER
                } else if (click_count >= 2) {
                    handle_button_event(2); // BACK
                }
                click_count = 0;
            }
        }"""

button_task_new = """        if (click_count > 0 && !pressed) {
            uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;
            if (now - last_press_time > 400) {
                if (click_count == 1) {
                    handle_button_event(0); // Single Click: HOVER
                } else if (click_count == 2) {
                    handle_button_event(2); // Double Click: BACK
                } else if (click_count >= 3) {
                    handle_button_event(3); // Triple Click: Cycle Sens
                }
                click_count = 0;
            }
        }"""
code = code.replace(button_task_old, button_task_new)

# 4. Update STATE_MOUSE event handlers in handle_button_event
state_mouse_old = """        if (current_state == STATE_MOUSE) {
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

state_mouse_new = """        if (current_state == STATE_MOUSE) {
            if (event == 0) { // Single click: Left Click
                ble_mouse_send_report(0, 0, 1);
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 2) { // Double click: Right Click
                ble_mouse_send_report(0, 0, 2);
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 3) { // Triple click: Cycle Sensitivity
                cfg_sensitivity += 0.5f;
                if (cfg_sensitivity > 4.0f) cfg_sensitivity = 1.0f;
                char buf[256];
                snprintf(buf, sizeof(buf), "AIR MOUSE ACTIVE\\n\\nSens: %.2fx\\n\\nBOOT Button:\\n- Single: Left Click\\n- Double: Right Click\\n- Triple: Cycle Sens\\n- Long Press: Exit", cfg_sensitivity);
                lv_label_set_text(mouse_info_label, buf);
            } else if (event == 1) { // Long press: Back to menu
                current_state = STATE_MENU;
                mouse_active = false;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
            }
            lvgl_unlock();
            return;
        }"""
code = code.replace(state_mouse_old, state_mouse_new)

# Update mouse menu click description
enter_mouse_old = """                } else if (menu_hover_index == 2) {
                    current_state = STATE_MOUSE;
                    mouse_active = true;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                }"""

enter_mouse_new = """                } else if (menu_hover_index == 2) {
                    current_state = STATE_MOUSE;
                    mouse_active = true;
                    char buf[256];
                    snprintf(buf, sizeof(buf), "AIR MOUSE ACTIVE\\n\\nSens: %.2fx\\n\\nBOOT Button:\\n- Single: Left Click\\n- Double: Right Click\\n- Triple: Cycle Sens\\n- Long Press: Exit", cfg_sensitivity);
                    lv_label_set_text(mouse_info_label, buf);
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                }"""
code = code.replace(enter_mouse_old, enter_mouse_new)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully fixed camera pins, IMU auto-increment, and mouse sensitivity shortcut")
