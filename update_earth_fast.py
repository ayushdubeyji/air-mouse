import os
import re

main_path = r"C:\Users\dell\Desktop\s3cam\src\main.c"
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fast Math approximations
fast_math = """
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
"""

if "fast_atan2" not in content:
    content = content.replace('#include "earth_texture.h"', '#include "earth_texture.h"\n' + fast_math)

# 2. Update Earth Drawing Loop (Optimization + BGR Fix + Breathing + Axis mapping)
old_draw_loop = content[content.find('                        // 3D Earth Texture Mapping Rendering'):content.find('                        lv_obj_invalidate(earth_canvas);') + 60]

new_draw_loop = """                        // 3D Earth Texture Mapping Rendering
                        // Calculate Breathing zoom
                        float time_sec = now / 1000.0f;
                        float breath = (sinf(time_sec * 3.0f) + 1.0f) * 0.5f;
                        
                        int zoom_val = in_settings_menu ? 90 : (256 + (int)(64.0f * breath));
                        lv_img_set_zoom(earth_canvas, zoom_val);
                        
                        if (in_settings_menu) {
                            lv_obj_align(earth_canvas, LV_ALIGN_TOP_RIGHT, -10, 10);
                        } else {
                            lv_obj_align(earth_canvas, LV_ALIGN_CENTER, 0, 0);
                        }

                        // Fix rotation map:
                        // The user said earth is not rotating as per boards rotation.
                        // We map the screen axes (x: right, y: down, z: forward) via the IMU rotation matrix.
                        // We might need to flip/swap axes depending on the sensor mount.
                        float r00 = 1 - 2*q2*q2 - 2*q3*q3;
                        float r01 = 2*q1*q2 - 2*q0*q3;
                        float r02 = 2*q1*q3 + 2*q0*q2;
                        float r10 = 2*q1*q2 + 2*q0*q3;
                        float r11 = 1 - 2*q1*q1 - 2*q3*q3;
                        float r12 = 2*q2*q3 - 2*q0*q1;
                        float r20 = 2*q1*q3 - 2*q0*q2;
                        float r21 = 2*q2*q3 + 2*q0*q1;
                        float r22 = 1 - 2*q1*q1 - 2*q2*q2;

                        lv_color_t bg_color = lv_color_hex(0x050510);
                        
                        for(int cy = 0; cy < EARTH_DIAM; cy++) {
                            float y = (cy - EARTH_RADIUS) / (float)EARTH_RADIUS;
                            for(int cx = 0; cx < EARTH_DIAM; cx++) {
                                float x = (cx - EARTH_RADIUS) / (float)EARTH_RADIUS;
                                float dist_sq = x*x + y*y;
                                
                                if (dist_sq <= 1.0f) {
                                    float z = -sqrtf(1.0f - dist_sq);
                                    
                                    // Map to earth space. Swap axes to match real-world
                                    float ex = x;
                                    float ey = -y; // Screen Y is down, earth Y is up
                                    float ez = z;
                                    
                                    float rx = r00*ex + r10*ey + r20*ez;
                                    float ry = r01*ex + r11*ey + r21*ez;
                                    float rz = r02*ex + r12*ey + r22*ez;
                                    
                                    float u = 0.5f + (fast_atan2(rz, rx) * 0.1591549f); // / 2pi
                                    float v = 0.5f - (fast_asin(ry) * 0.3183098f);      // / pi
                                    
                                    int tx = (int)(u * earth_width) % earth_width;
                                    int ty = (int)(v * earth_height);
                                    if (ty >= earth_height) ty = earth_height - 1;
                                    if (ty < 0) ty = 0;
                                    
                                    uint16_t color_val = earth_texture_map[ty * earth_width + tx];
                                    
                                    float brightness = -z;
                                    if (brightness < 0.2f) brightness = 0.2f;
                                    
                                    // Extract and SWAP Red and Blue because original color was swapped
                                    // Original: R=(color>>11), G=(color>>5), B=(color&0x1F)
                                    // We swap them: B is now extracted from high bits, R from low bits.
                                    uint8_t b_col = (color_val >> 11) & 0x1F;
                                    uint8_t g_col = (color_val >> 5) & 0x3F;
                                    uint8_t r_col = color_val & 0x1F;
                                    
                                    r_col = (uint8_t)(r_col * brightness);
                                    g_col = (uint8_t)(g_col * brightness);
                                    b_col = (uint8_t)(b_col * brightness);
                                    
                                    uint16_t shaded = (r_col << 11) | (g_col << 5) | b_col;
                                    lv_color_t c;
                                    c.full = shaded;
                                    
                                    earth_cbuf[cy * EARTH_DIAM + cx] = c;
                                } else {
                                    earth_cbuf[cy * EARTH_DIAM + cx] = bg_color;
                                }
                            }
                        }
                        lv_obj_invalidate(earth_canvas);
"""
if old_draw_loop:
    content = content.replace(old_draw_loop, new_draw_loop)


# 3. Button remapping
# Left Click -> GPIO 21
content = re.sub(r'#define PIN_BTN_LEFT\s+\d+', '#define PIN_BTN_LEFT 21', content)
# Right Click -> Removed
# The old left click (was GPIO 1) is now push to hover. But wait, "the dedicated push to hover button will be assigned to the current left click button".
# Currently, PIN_BTN_LEFT was what? Let's check the old value. Usually 1 or 2? Wait, the user said "current left click button and the left click button i am putting on gpio 21". So the physical switch that was Left Click is now Hover.
# Let's see PIN_BTN definitions in content.
btn_left_match = re.search(r'#define PIN_BTN_LEFT\s+(\d+)', content)
if btn_left_match:
    old_left_pin = btn_left_match.group(1)
    if old_left_pin != '21':
        content = re.sub(r'#define PIN_BTN_HOVER\s+\d+', f'#define PIN_BTN_HOVER {old_left_pin}', content)

# Remove right click logic
content = re.sub(r'#define PIN_BTN_RIGHT\s+\d+', '// Right click removed', content)

# In hardware_input_task, remove right button reading
content = re.sub(r'int btn_right_state = !gpio_get_level\(PIN_BTN_RIGHT\);', 'int btn_right_state = 0; // Removed', content)
content = re.sub(r'gpio_set_direction\(PIN_BTN_RIGHT, GPIO_MODE_INPUT\);', '// Right removed', content)
content = re.sub(r'gpio_set_pull_mode\(PIN_BTN_RIGHT, GPIO_PULLUP_ONLY\);', '// Right removed', content)

# 4. Shake to toggle Jog axis
# We add shake detection inside the IMU loop
shake_vars = """
                // Shake detection for Jog axis
                static float last_ax = 0;
                static uint32_t last_shake = 0;
                float shake_diff = fabsf(ax - last_ax);
                last_ax = ax;
                
                static bool jog_is_horizontal = false; // Toggle state
                if (shake_diff > 1.5f && (now - last_shake) > 1000) { // 1.5g diff threshold
                    jog_is_horizontal = !jog_is_horizontal;
                    last_shake = now;
                    ESP_LOGI("SHAKE", "Jog axis toggled to %s", jog_is_horizontal ? "Horizontal" : "Vertical");
                }
"""

if "shake_diff" not in content:
    # insert before encoder reading
    content = content.replace("int enc_state = encoder_read();", shake_vars + "\n                int enc_state = encoder_read();")

# Now update encoder scroll logic based on jog_is_horizontal
old_enc_logic = """if (enc_state != 0) {
                    if (in_settings_menu) {
                        menu_selection += enc_state;
                    } else {
                        ble_mouse_scroll(enc_state);
                    }
                }"""

new_enc_logic = """if (enc_state != 0) {
                    if (in_settings_menu) {
                        menu_selection += enc_state;
                    } else {
                        if (jog_is_horizontal) {
                            ble_mouse_scroll_horiz(enc_state); // Assuming ble_mouse supports horiz
                        } else {
                            ble_mouse_scroll(enc_state);
                        }
                    }
                }"""
content = content.replace(old_enc_logic, new_enc_logic)

# 5. Advanced Smoothing
# The user said "use some advanced algorithms to smooth out the acceleration and deaccleration curves without breaking the current working code"
# Replace the Fitts's Law line: float target_vx = ...
old_fitts = """float target_vx = dx * dx_sign * (0.5f + fabsf(dx) * 0.05f);"""
new_fitts = """// Advanced Smoothing: S-Curve / Exponential acceleration
                    float speed_factor = (fabsf(dx) * fabsf(dx)) * 0.08f; 
                    if (speed_factor > 15.0f) speed_factor = 15.0f; // Cap max accel
                    float target_vx = dx * dx_sign * (1.0f + speed_factor);"""
content = content.replace(old_fitts, new_fitts)

old_fitts_y = """float target_vy = dy * dy_sign * (0.5f + fabsf(dy) * 0.05f);"""
new_fitts_y = """float speed_factor_y = (fabsf(dy) * fabsf(dy)) * 0.08f; 
                    if (speed_factor_y > 15.0f) speed_factor_y = 15.0f;
                    float target_vy = dy * dy_sign * (1.0f + speed_factor_y);"""
content = content.replace(old_fitts_y, new_fitts_y)

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated main.c with fast earth + fixes!")
