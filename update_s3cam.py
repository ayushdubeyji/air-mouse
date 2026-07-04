import re

with open('C:/Users/dell/Desktop/s3cam/src/main.c', 'r') as f:
    content = f.read()

# 1. Update Pins
content = re.sub(
    r'#define BTN_L_PIN 4.*?\n#define BTN_R_PIN 6.*?\n#define JOG_SW_PIN 10',
    '#define CLUTCH_PIN 4      // Push to hover (was Left Click)\n#define BTN_L_PIN 21      // New Left Click\n#define JOG_SW_PIN 10',
    content, flags=re.MULTILINE
)

# 2. Update GPIO Mask
content = re.sub(
    r'\.pin_bit_mask = \(1ULL<<BTN_L_PIN\) \| \(1ULL<<BTN_R_PIN\) \| \(1ULL<<JOG_SW_PIN\) \| \(1ULL<<JOG_UP_PIN\) \| \(1ULL<<JOG_DN_PIN\) \| \(1ULL<<BOOT_BUTTON_PIN\),',
    '.pin_bit_mask = (1ULL<<BTN_L_PIN) | (1ULL<<CLUTCH_PIN) | (1ULL<<JOG_SW_PIN) | (1ULL<<JOG_UP_PIN) | (1ULL<<JOG_DN_PIN) | (1ULL<<BOOT_BUTTON_PIN),',
    content
)

# 3. Add jog_mode_left_right label creation
content = re.sub(
    r'    lbl_clutch = lv_label_create\(hud_labels_cont\);\n    lv_label_set_text\(lbl_clutch, "HOLD L-CLICK TO MOVE"\);\n    lv_obj_align\(lbl_clutch, LV_ALIGN_BOTTOM_MID, 0, -20\);\n    lv_obj_set_style_text_color\(lbl_clutch, lv_color_hex\(0x888888\), 0\);',
    '    lbl_clutch = lv_label_create(hud_labels_cont);\n    lv_label_set_text(lbl_clutch, "HOLD CLUTCH TO MOVE");\n    lv_obj_align(lbl_clutch, LV_ALIGN_BOTTOM_MID, 0, -20);\n    lv_obj_set_style_text_color(lbl_clutch, lv_color_hex(0x888888), 0);\n\n    lbl_jog_mode = lv_label_create(hud_labels_cont);\n    lv_label_set_text(lbl_jog_mode, "MODE: U/D");\n    lv_obj_align(lbl_jog_mode, LV_ALIGN_BOTTOM_LEFT, 10, -10);\n    lv_obj_set_style_text_color(lbl_jog_mode, lv_color_hex(0xFF00FF), 0);',
    content
)

# 4. Ring Generation (Sphere)
ring_code = """
            if (ring == 0) { // Yaw ring (Horizontal: XY plane)
                ring_verts[ring][i].x = cosf(angle);
                ring_verts[ring][i].y = sinf(angle);
                ring_verts[ring][i].z = 0;
            } else if (ring == 1) { // Pitch ring (Vertical: YZ plane)
                ring_verts[ring][i].x = 0;
                ring_verts[ring][i].y = cosf(angle);
                ring_verts[ring][i].z = sinf(angle);
            } else if (ring == 2) { // Roll ring (Vertical: XZ plane)
                ring_verts[ring][i].x = cosf(angle);
                ring_verts[ring][i].y = 0;
                ring_verts[ring][i].z = sinf(angle);
            } else if (ring == 3) { // Latitude 1
                ring_verts[ring][i].x = cosf(angle) * 0.707f;
                ring_verts[ring][i].y = sinf(angle) * 0.707f;
                ring_verts[ring][i].z = 0.707f;
            } else if (ring == 4) { // Latitude 2
                ring_verts[ring][i].x = cosf(angle) * 0.707f;
                ring_verts[ring][i].y = sinf(angle) * 0.707f;
                ring_verts[ring][i].z = -0.707f;
            } else { // Longitude 2
                ring_verts[ring][i].x = cosf(angle) * 0.707f;
                ring_verts[ring][i].y = sinf(angle) * 0.707f;
                ring_verts[ring][i].z = 0;
            }
"""
content = re.sub(
    r'            if \(ring == 0\) \{ // Yaw ring.*?ring_verts\[ring\]\[i\]\.z = 0;\n            \}',
    ring_code,
    content,
    flags=re.DOTALL
)

# Unhide the rings
content = re.sub(
    r'        if \(i >= 3\) \{\n            lv_obj_add_flag\(sphere_lines\[i\], LV_OBJ_FLAG_HIDDEN\); // Hide latitude rings to avoid weird circles\n        \}',
    '        // lv_obj_add_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN); // Rings are fixed now',
    content
)

# 5. Shake logic (Toggle jog mode)
shake_logic = """            if (jerk > 25000) {
                // Shake detected
                static uint32_t last_shake = 0;
                if (now - last_shake > 1000) {
                    jog_mode_left_right = !jog_mode_left_right;
                    if (lvgl_lock(-1)) {
                        lv_label_set_text_fmt(lbl_jog_mode, "MODE: %s", jog_mode_left_right ? "L/R" : "U/D");
                        lvgl_unlock();
                    }
                    last_shake = now;
                }
                if (lvgl_lock(-1)) {
                    for(int i=0; i<NUM_SPARKLES; i++) {"""
content = re.sub(
    r'            if \(jerk > 25000\) \{\n                if \(lvgl_lock\(-1\)\) \{\n                    for\(int i=0; i<NUM_SPARKLES; i\+\+\) \{',
    shake_logic,
    content
)

# 6. Smooth Cursor Movement
smooth_logic = """                    // Advanced smoothing algorithm using EMA + Non-linear acceleration
                    static float smooth_x = 0;
                    static float smooth_y = 0;
                    smooth_x = smooth_x * 0.7f + move_x * 0.3f;
                    smooth_y = smooth_y * 0.7f + move_y * 0.3f;
                    
                    float accel_x = (smooth_x * fabs(smooth_x)) * 0.05f + smooth_x * 0.5f;
                    float accel_y = (smooth_y * fabs(smooth_y)) * 0.05f + smooth_y * 0.5f;

                    static float accum_x=0, accum_y=0;
                    if (fabs(move_x) > cfg_deadzone) accum_x += accel_x * cfg_sensitivity * 0.015f;
                    if (fabs(move_y) > cfg_deadzone) accum_y += accel_y * cfg_sensitivity * 0.015f;"""
content = re.sub(
    r'                    static float accum_x=0, accum_y=0;\n                    if \(fabs\(move_x\) > cfg_deadzone\) accum_x \+= move_x \* cfg_sensitivity \* 0.015f;\n                    if \(fabs\(move_y\) > cfg_deadzone\) accum_y \+= move_y \* cfg_sensitivity \* 0.015f;',
    smooth_logic,
    content
)

# 7. Button and Clutch Logic
button_logic = """        // Left Click and Clutch Logic
        bool clutch_pressed = (gpio_get_level(CLUTCH_PIN) == 0);
        bool left_pressed = (gpio_get_level(BTN_L_PIN) == 0);

        static bool last_clutch_raw = false;
        if (clutch_pressed) {
            if (!last_clutch_raw) {
                last_clutch_raw = true;
                if (!in_settings_menu) {
                    gyro_clutch_active = true;
                    if (lvgl_lock(-1)) {
                        lv_label_set_text(lbl_clutch, "ACTIVE");
                        lv_obj_set_style_text_color(lbl_clutch, lv_color_hex(0x00FF00), 0);
                        lvgl_unlock();
                    }
                }
            }
        } else {
            if (last_clutch_raw) {
                last_clutch_raw = false;
                if (!in_settings_menu) {
                    gyro_clutch_active = false;
                    if (lvgl_lock(-1)) {
                        lv_label_set_text(lbl_clutch, "HOLD CLUTCH TO MOVE");
                        lv_obj_set_style_text_color(lbl_clutch, lv_color_hex(0x888888), 0);
                        lvgl_unlock();
                    }
                }
            }
        }

        if (left_pressed != last_left_pressed) {
            if (left_pressed) {
                mouse_buttons_state |= 0x01; // Left click down
            } else {
                mouse_buttons_state &= ~0x01; // Left click up
            }
            ble_mouse_send_report(0, 0, mouse_buttons_state);
            last_left_pressed = left_pressed;
        }"""
content = re.sub(
    r'        // Left / Right Mouse Buttons & Clutch Logic.*?(?=        // Jog Dial SW Logic)',
    button_logic + "\n",
    content,
    flags=re.DOTALL
)

# 8. Jog UP/DN Logic
content = re.sub(r'ble_mouse_send_keyboard\(0, 0x52\); // Up Arrow', 'ble_mouse_send_keyboard(0, jog_mode_left_right ? 0x50 : 0x52); // Up/Left Arrow', content)
content = re.sub(r'ble_mouse_send_keyboard\(0, 0x51\); // Down Arrow', 'ble_mouse_send_keyboard(0, jog_mode_left_right ? 0x4F : 0x51); // Down/Right Arrow', content)

# 9. PSRAM LVGL allocation
psram_alloc = """    lv_color_t *buf1 = heap_caps_malloc(240*160*2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT); // Use PSRAM
    lv_color_t *buf2 = heap_caps_malloc(240*160*2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT); // Use PSRAM
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, 240*160);"""
content = re.sub(
    r'    lv_color_t \*buf1 = heap_caps_malloc\(240\*80\*2, MALLOC_CAP_DMA\); // Increased from 40 to 80 lines for higher FPS\n    lv_color_t \*buf2 = heap_caps_malloc\(240\*80\*2, MALLOC_CAP_DMA\);\n    lv_disp_draw_buf_init\(&draw_buf, buf1, buf2, 240\*80\);',
    psram_alloc,
    content
)


with open('C:/Users/dell/Desktop/s3cam/src/main.c', 'w') as f:
    f.write(content)

print("Done")
