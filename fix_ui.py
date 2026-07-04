import re

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Remove the constant text updating in imu_task
imu_loop = """
                if (lvgl_lock(-1)) {
                    // Update settings text continuously
                    char sbuf[256];
                    snprintf(sbuf, sizeof(sbuf), "MAHONY AHRS ACTIVE\\n\\nSens: %.1f | Dead: %d\\nInvX: %d | InvY: %d\\nSwap: %d\\n\\nBoot Button:\\n2x: Cycle Settng\\n3x: Adjust Val\\nLong: Exit", 
                            cfg_sensitivity, (int)cfg_deadzone, cfg_invert_x, cfg_invert_y, cfg_swap_xy);
                    lv_label_set_text(mouse_info_label, sbuf);

                    // 3D Cube Rotation using Quaternions
"""
imu_loop_fix = """
                if (lvgl_lock(-1)) {
                    // 3D Cube Rotation using Quaternions
"""
content = content.replace(imu_loop, imu_loop_fix)

# 2. Re-position and format mouse_info_label in lvgl_camera_ui_init
mouse_ui_init_old = """
    mouse_info_label = lv_label_create(parent);
    lv_label_set_text(mouse_info_label, "AIR MOUSE ACTIVE\\n\\nBOOT Button:\\n1x: L-Click\\n2x: R-Click\\nLong: Exit");
    lv_obj_align(mouse_info_label, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(mouse_info_label, lv_color_hex(0x00FFFF), 0);
    lv_obj_set_style_text_align(mouse_info_label, LV_TEXT_ALIGN_CENTER, 0);
"""
mouse_ui_init_new = """
    mouse_info_label = lv_label_create(parent);
    lv_label_set_text(mouse_info_label, "3D GYRO MOUSE");
    // Move it to top left so it doesn't clutter the cube
    lv_obj_align(mouse_info_label, LV_ALIGN_TOP_LEFT, 5, 5);
    lv_obj_set_style_text_color(mouse_info_label, lv_color_hex(0x00FFBB), 0);
    lv_obj_set_style_text_font(mouse_info_label, &lv_font_montserrat_14, 0);
"""
content = content.replace(mouse_ui_init_old, mouse_ui_init_new)

# 3. Add a helper function to update the mouse text
# Wait, let's just do it directly in the button handler and where state switches
# Let's write the helper function definition at the top
helper_func = """
static void update_mouse_page_text(void) {
    if (!mouse_info_label) return;
    char sbuf[256];
    snprintf(sbuf, sizeof(sbuf), 
        "6DoF IMU ACTIVE\\n"
        "Sens: %.1f | Dead: %d\\n"
        "InvX: %d | InvY: %d\\n"
        "SwapXY: %d\\n\\n"
        "2x: Cycle Setting\\n"
        "3x: Toggle/Adjust", 
        cfg_sensitivity, (int)cfg_deadzone, cfg_invert_x, cfg_invert_y, cfg_swap_xy);
    if (lvgl_lock(-1)) {
        lv_label_set_text(mouse_info_label, sbuf);
        lvgl_unlock();
    }
}
"""
content = content.replace("static void update_settings_labels(void);", "static void update_settings_labels(void);\n" + helper_func)

# 4. Find where Double Click and Triple Click change settings
button_logic_old = """
            } else if (event == 2) { // Double click: Cycle Settings
                static int setting_focus = 0;
                setting_focus = (setting_focus + 1) % 5;
                if (setting_focus == 0) { cfg_sensitivity += 0.5f; if (cfg_sensitivity > 4.0f) cfg_sensitivity = 0.5f; }
                else if (setting_focus == 1) { cfg_deadzone += 5.0f; if (cfg_deadzone > 30.0f) cfg_deadzone = 5.0f; }
                else if (setting_focus == 2) { cfg_invert_x = !cfg_invert_x; }
                else if (setting_focus == 3) { cfg_invert_y = !cfg_invert_y; }
                else if (setting_focus == 4) { cfg_swap_xy = !cfg_swap_xy; }
            } else if (event == 1) { // Long press: Back to menu
"""

button_logic_new = """
            } else if (event == 2) { // Double click: Cycle Settings focus
                static int setting_focus = 0;
                setting_focus = (setting_focus + 1) % 5;
                if (setting_focus == 0) { cfg_sensitivity += 0.5f; if (cfg_sensitivity > 4.0f) cfg_sensitivity = 0.5f; }
                else if (setting_focus == 1) { cfg_deadzone += 5.0f; if (cfg_deadzone > 30.0f) cfg_deadzone = 5.0f; }
                else if (setting_focus == 2) { cfg_invert_x = !cfg_invert_x; }
                else if (setting_focus == 3) { cfg_invert_y = !cfg_invert_y; }
                else if (setting_focus == 4) { cfg_swap_xy = !cfg_swap_xy; }
                update_mouse_page_text();
            } else if (event == 1) { // Long press: Back to menu
"""
content = content.replace(button_logic_old, button_logic_new)

# Make sure it updates when entering mouse state
enter_mouse_old = """
                    int sens_dec = (int)((cfg_sensitivity - sens_int) * 100);
                    if (sens_dec < 0) sens_dec = -sens_dec;
                    snprintf(buf, sizeof(buf), "AIR MOUSE ACTIVE\\n\\nSens: %d.%02dx\\n\\nBOOT Button:\\n- Single: Left Click\\n- Double: Right Click\\n- Triple: Cycle Sens\\n- Long Press: Exit", sens_int, sens_dec);
                    lv_label_set_text(mouse_info_label, buf);
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
"""
enter_mouse_new = """
                    update_mouse_page_text();
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
"""
content = content.replace(enter_mouse_old, enter_mouse_new)

# 5. Fix cube projection and scale to make it bigger and centered
cube_projection = """
                        float z_off = 3.5f;
                        proj[i].x = (rx / (rz + z_off)) * 80.0f + 120.0f;
                        proj[i].y = (ry / (rz + z_off)) * 80.0f + 120.0f; // offset upwards
"""
cube_projection_new = """
                        // Center is 120, 120. Scale is 90.
                        float z_off = 3.2f;
                        float scale = 95.0f;
                        proj[i].x = (rx / (rz + z_off)) * scale + 120.0f;
                        proj[i].y = (ry / (rz + z_off)) * scale + 120.0f;
"""
content = content.replace(cube_projection, cube_projection_new)

# Let's ensure the initial text is updated
# In app_main after lvgl_camera_ui_init:
app_main_old = """
    if (lvgl_lock(-1))
    {
        lvgl_camera_ui_init(lv_scr_act());
        update_menu_focus();
        lvgl_unlock();
    }
"""
app_main_new = """
    if (lvgl_lock(-1))
    {
        lvgl_camera_ui_init(lv_scr_act());
        update_menu_focus();
        lvgl_unlock();
    }
    update_mouse_page_text(); // Initialize text right after UI creation
"""
content = content.replace(app_main_old, app_main_new)

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)
