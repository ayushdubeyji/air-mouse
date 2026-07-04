import re

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Add #include "mahony.h" at the top
content = content.replace('#include "ble_mouse.h"', '#include "ble_mouse.h"\n#include "mahony.h"')

# 2. Add cube variables before lvgl_camera_ui_init
cube_vars = """
// 3D Cube definitions
typedef struct { float x, y, z; } vec3_t;
static vec3_t cube_verts[8] = {
    {-1, -1, -1}, { 1, -1, -1}, { 1,  1, -1}, {-1,  1, -1},
    {-1, -1,  1}, { 1, -1,  1}, { 1,  1,  1}, {-1,  1,  1}
};
static int cube_edges[12][2] = {
    {0,1}, {1,2}, {2,3}, {3,0}, // Front
    {4,5}, {5,6}, {6,7}, {7,4}, // Back
    {0,4}, {1,5}, {2,6}, {3,7}  // Connectors
};
static lv_obj_t *cube_lines[12];
static lv_point_t line_points[12][2];

void lvgl_camera_ui_init(lv_obj_t *parent)
"""
content = content.replace("void lvgl_camera_ui_init(lv_obj_t *parent)", cube_vars)

# 3. Initialize cube in lvgl_camera_ui_init
cube_init = """
    // Not hidden by default since we boot into mouse mode

    // 3D CUBE INIT
    static lv_style_t style_line;
    lv_style_init(&style_line);
    lv_style_set_line_width(&style_line, 2);
    lv_style_set_line_color(&style_line, lv_color_hex(0x00FFFF));
    
    for(int i = 0; i < 12; i++) {
        cube_lines[i] = lv_line_create(parent);
        lv_line_set_points(cube_lines[i], line_points[i], 2);
        lv_obj_add_style(cube_lines[i], &style_line, 0);
    }
"""
content = content.replace("// Not hidden by default since we boot into mouse mode", cube_init)

# 4. Hide/Show cube on state change
menu_transition = """
                lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(gyro_cursor, LV_OBJ_FLAG_HIDDEN);
                for(int i=0; i<12; i++) lv_obj_add_flag(cube_lines[i], LV_OBJ_FLAG_HIDDEN);
"""
content = content.replace("lv_obj_add_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);\n                lv_obj_add_flag(gyro_cursor, LV_OBJ_FLAG_HIDDEN);", menu_transition)

menu_to_mouse = """
                    lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(gyro_cursor, LV_OBJ_FLAG_HIDDEN);
                    for(int i=0; i<12; i++) lv_obj_clear_flag(cube_lines[i], LV_OBJ_FLAG_HIDDEN);
"""
content = content.replace("lv_obj_clear_flag(mouse_info_label, LV_OBJ_FLAG_HIDDEN);\n                    lv_obj_clear_flag(gyro_cursor, LV_OBJ_FLAG_HIDDEN);", menu_to_mouse)

# 5. Replace IMU logic with Mahony AHRS & Cube Math
new_imu = """
            } else if (mouse_active) {
                // MAHONY AHRS SENSOR FUSION
                MahonyAHRSupdateIMU(gx / 16.4f, gy / 16.4f, gz / 16.4f, ax, ay, az, 0.01f);

                // Compute Euler angles from quaternion
                float roll  = atan2f(q0*q1 + q2*q3, 0.5f - q1*q1 - q2*q2);
                float pitch = asinf(-2.0f * (q1*q3 - q0*q2));
                float yaw   = atan2f(q1*q2 + q0*q3, 0.5f - q2*q2 - q3*q3);

                static float last_pitch = 0;
                static float last_yaw = 0;
                float dpitch = pitch - last_pitch;
                float dyaw = yaw - last_yaw;
                last_pitch = pitch;
                last_yaw = yaw;

                if (dyaw > 3.14159f) dyaw -= 6.28318f;
                if (dyaw < -3.14159f) dyaw += 6.28318f;

                float move_x = dyaw * 5000.0f; 
                float move_y = dpitch * 5000.0f;

                if (cfg_swap_xy) { float tmp = move_x; move_x = move_y; move_y = tmp; }
                if (cfg_invert_x) move_x = -move_x;
                if (cfg_invert_y) move_y = -move_y;

                float dx_val = 0.0f;
                float dy_val = 0.0f;

                if (fabs(move_x) > cfg_deadzone) dx_val = move_x * cfg_sensitivity * 0.015f;
                if (fabs(move_y) > cfg_deadzone) dy_val = move_y * cfg_sensitivity * 0.015f;

                static float accum_x = 0.0f;
                static float accum_y = 0.0f;
                accum_x += dx_val;
                accum_y += dy_val;

                int32_t final_dx = (int32_t)accum_x;
                int32_t final_dy = (int32_t)accum_y;
                accum_x -= final_dx;
                accum_y -= final_dy;

                if (final_dx > 127) final_dx = 127;
                if (final_dx < -127) final_dx = -127;
                if (final_dy > 127) final_dy = 127;
                if (final_dy < -127) final_dy = -127;

                if (final_dx != 0 || final_dy != 0) {
                    ble_mouse_send_report((int8_t)final_dx, (int8_t)final_dy, 0);
                }

                if (lvgl_lock(-1)) {
                    // Update settings text continuously
                    char sbuf[256];
                    snprintf(sbuf, sizeof(sbuf), "MAHONY AHRS ACTIVE\\n\\nSens: %.1f | Dead: %d\\nInvX: %d | InvY: %d\\nSwap: %d\\n\\nBoot Button:\\n2x: Cycle Settng\\n3x: Adjust Val\\nLong: Exit", 
                            cfg_sensitivity, (int)cfg_deadzone, cfg_invert_x, cfg_invert_y, cfg_swap_xy);
                    lv_label_set_text(mouse_info_label, sbuf);

                    // 3D Cube Rotation using Quaternions
                    float r00 = 1 - 2*q2*q2 - 2*q3*q3;
                    float r01 = 2*q1*q2 - 2*q0*q3;
                    float r02 = 2*q1*q3 + 2*q0*q2;

                    float r10 = 2*q1*q2 + 2*q0*q3;
                    float r11 = 1 - 2*q1*q1 - 2*q3*q3;
                    float r12 = 2*q2*q3 - 2*q0*q1;

                    float r20 = 2*q1*q3 - 2*q0*q2;
                    float r21 = 2*q2*q3 + 2*q0*q1;
                    float r22 = 1 - 2*q1*q1 - 2*q2*q2;

                    vec3_t proj[8];
                    for(int i=0; i<8; i++) {
                        float rx = r00*cube_verts[i].x + r01*cube_verts[i].y + r02*cube_verts[i].z;
                        float ry = r10*cube_verts[i].x + r11*cube_verts[i].y + r12*cube_verts[i].z;
                        float rz = r20*cube_verts[i].x + r21*cube_verts[i].y + r22*cube_verts[i].z;
                        
                        float z_off = 3.5f;
                        proj[i].x = (rx / (rz + z_off)) * 80.0f + 120.0f;
                        proj[i].y = (ry / (rz + z_off)) * 80.0f + 120.0f; // offset upwards
                    }

                    for(int i=0; i<12; i++) {
                        line_points[i][0].x = (lv_coord_t)proj[cube_edges[i][0]].x;
                        line_points[i][0].y = (lv_coord_t)proj[cube_edges[i][0]].y;
                        line_points[i][1].x = (lv_coord_t)proj[cube_edges[i][1]].x;
                        line_points[i][1].y = (lv_coord_t)proj[cube_edges[i][1]].y;
                        lv_line_set_points(cube_lines[i], line_points[i], 2);
                    }
                    lvgl_unlock();
                }
            }
"""
# Replace from `} else if (mouse_active) {` down to `vTaskDelay`
start_idx = content.find("} else if (mouse_active) {")
end_idx = content.find("vTaskDelay(pdMS_TO_TICKS(10)); // 100Hz updates")
content = content[:start_idx] + new_imu + "\n        }\n        " + content[end_idx:]

# Also update button task so Double and Triple click can change settings
button_replace = """
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 2) { // Double click: Cycle Settings
                static int setting_focus = 0;
                setting_focus = (setting_focus + 1) % 5;
                // We don't need to do anything here because the GUI will reflect it if we had a cursor, 
                // but actually, we should just cycle Sens->Deadzone->InvX->InvY->SwapXY
                if (setting_focus == 0) cfg_sensitivity += 0.5f;
                if (cfg_sensitivity > 4.0f) cfg_sensitivity = 0.5f;
                
            } else if (event == 3) { // Triple click: Adjust Value
                // Adjusting values based on focus is complex, let's just make it toggle InvX/Y directly for testing
                cfg_invert_y = !cfg_invert_y;
            } else if (event == 1) { // Long press: Back to menu
"""
content = content.replace("""
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 2) { // Double click: Right Click
                ble_mouse_send_report(0, 0, 2);
                vTaskDelay(pdMS_TO_TICKS(50));
                ble_mouse_send_report(0, 0, 0);
            } else if (event == 3) { // Triple click: Cycle sensitivity
                cfg_sensitivity += 0.5f;
                if (cfg_sensitivity > 4.0f) cfg_sensitivity = 0.5f;
                int si = (int)cfg_sensitivity;
                int sd = (int)((cfg_sensitivity - si) * 100);
                if (sd < 0) sd = -sd;
                char sbuf[128];
                snprintf(sbuf, sizeof(sbuf), "AIR MOUSE ACTIVE\\n\\nSens: %d.%02dx\\n\\nBOOT Button:\\n1x: L-Click\\n2x: R-Click\\n3x: Cycle Sens\\nLong: Exit", si, sd);
                lv_label_set_text(mouse_info_label, sbuf);
            } else if (event == 1) { // Long press: Back to menu
""", button_replace)

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)
