import re

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Replace definitions (lines 277-289)
content = re.sub(
    r'// 3D Cube definitions.*static lv_point_t line_points\[12\]\[2\];',
    r'''// 3D Sphere definitions
typedef struct { float x, y, z; } vec3_t;
#define SPHERE_RING_POINTS 16
static lv_obj_t *sphere_lines[3];
static lv_point_t sphere_points[3][SPHERE_RING_POINTS + 1];
static vec3_t ring_verts[3][SPHERE_RING_POINTS];''',
    content,
    flags=re.DOTALL
)

# 2. Replace active mouse block including calibration subtract & sphere draw (lines 389-482)
active_mouse_pattern = r'\} else if \(mouse_active\) \{(?:(?!\} else if \(mouse_active\) \{).)*?\}\s*\}\s*vTaskDelay\(pdMS_TO_TICKS\(10\)\);'
# Wait, let's match the block carefully:
active_mouse_pattern = r'\} else if \(mouse_active\) \{.*?ble_mouse_send_report\(\(int8_t\)final_dx, \(int8_t\)final_dy, 0\);\s*\}\s*static uint32_t last_cube_draw = 0;.*?lvgl_unlock\(\);\s*\}\s*\}\s*\}'

new_active_mouse = r'''} else if (mouse_active) {
                // Subtract calibration offsets to fix drift ("moving on its own")!
                float cgx = gx - gyro_off_x;
                float cgy = gy - gyro_off_y;
                float cgz = gz - gyro_off_z;

                // MAHONY AHRS SENSOR FUSION using calibrated offsets
                MahonyAHRSupdateIMU(cgx / 16.4f, cgy / 16.4f, cgz / 16.4f, ax, ay, az, 0.01f);

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

                static uint32_t last_sphere_draw = 0;
                uint32_t current_time = xTaskGetTickCount() * portTICK_PERIOD_MS;
                // Throttle drawing to ~30 FPS to stop rendering bottlenecks
                if (current_time - last_sphere_draw > 33) {
                    last_sphere_draw = current_time;
                    if (lvgl_lock(-1)) {
                        // 3D Sphere Rotation using Quaternions
                        float r00 = 1 - 2*q2*q2 - 2*q3*q3;
                        float r01 = 2*q1*q2 - 2*q0*q3;
                        float r02 = 2*q1*q3 + 2*q0*q2;
                        float r10 = 2*q1*q2 + 2*q0*q3;
                        float r11 = 1 - 2*q1*q1 - 2*q3*q3;
                        float r12 = 2*q2*q3 - 2*q0*q1;
                        float r20 = 2*q1*q3 - 2*q0*q2;
                        float r21 = 2*q2*q3 + 2*q0*q1;
                        float r22 = 1 - 2*q1*q1 - 2*q2*q2;

                        float z_off = 3.2f;
                        float scale = 95.0f;

                        for (int ring = 0; ring < 3; ring++) {
                            for (int i = 0; i <= SPHERE_RING_POINTS; i++) {
                                float px = ring_verts[ring][i % SPHERE_RING_POINTS].x;
                                float py = ring_verts[ring][i % SPHERE_RING_POINTS].y;
                                float pz = ring_verts[ring][i % SPHERE_RING_POINTS].z;

                                float rx = r00*px + r01*py + r02*pz;
                                float ry = r10*px + r11*py + r12*pz;
                                float rz = r20*px + r21*py + r22*pz;

                                sphere_points[ring][i].x = (lv_coord_t)((rx / (rz + z_off)) * scale + 120.0f);
                                sphere_points[ring][i].y = (lv_coord_t)((ry / (rz + z_off)) * scale + 160.0f);
                            }
                            lv_line_set_points(sphere_lines[ring], sphere_points[ring], SPHERE_RING_POINTS + 1);
                        }
                        lvgl_unlock();
                    }
                }
            }'''

# Replace the active mouse block
content = re.sub(active_mouse_pattern, new_active_mouse, content, flags=re.DOTALL)

# 3. Replace initialization of cube lines in lvgl_camera_ui_init (lines 861-871)
cube_init_pattern = r'// 3D CUBE INIT.*?for\(int i = 0; i < 12; i\)\s*\{.*?cube_lines\[i\] = lv_line_create\(parent\);.*?lv_line_set_points\(cube_lines\[i\], line_points\[i\], 2\);.*?lv_obj_add_style\(cube_lines\[i\], &style_line, 0\);\s*\}'
new_sphere_init = r'''// 3D SPHERE INIT
    static lv_style_t style_line;
    lv_style_init(&style_line);
    lv_style_set_line_width(&style_line, 2);
    lv_style_set_line_color(&style_line, lv_color_hex(0x00FFFF));

    // Precalculate ring vertices
    for (int ring = 0; ring < 3; ring++) {
        for (int i = 0; i < SPHERE_RING_POINTS; i++) {
            float angle = i * (2.0f * 3.14159265f / SPHERE_RING_POINTS);
            if (ring == 0) {
                ring_verts[ring][i].x = cosf(angle);
                ring_verts[ring][i].y = sinf(angle);
                ring_verts[ring][i].z = 0;
            } else if (ring == 1) {
                ring_verts[ring][i].x = 0;
                ring_verts[ring][i].y = cosf(angle);
                ring_verts[ring][i].z = sinf(angle);
            } else {
                ring_verts[ring][i].x = cosf(angle);
                ring_verts[ring][i].y = 0;
                ring_verts[ring][i].z = sinf(angle);
            }
        }
    }

    for(int i = 0; i < 3; i++) {
        sphere_lines[i] = lv_line_create(parent);
        lv_line_set_points(sphere_lines[i], sphere_points[i], SPHERE_RING_POINTS + 1);
        lv_obj_add_style(sphere_lines[i], &style_line, 0);
    }'''

content = re.sub(cube_init_pattern, new_sphere_init, content, flags=re.DOTALL)

# 4. Replace hidden / clear flag loops
content = content.replace("for(int i=0; i<12; i++) lv_obj_add_flag(cube_lines[i], LV_OBJ_FLAG_HIDDEN);", "for(int i=0; i<3; i++) lv_obj_add_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN);")
content = content.replace("for(int i=0; i<12; i++) lv_obj_clear_flag(cube_lines[i], LV_OBJ_FLAG_HIDDEN);", "for(int i=0; i<3; i++) lv_obj_clear_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN);")

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)

print("Replacement complete.")
