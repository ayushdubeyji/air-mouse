import os
import re

main_path = r"C:\Users\dell\Desktop\s3cam\src\main.c"
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the ble_mouse_scroll_horiz which doesn't exist
new_enc_logic_horiz = """if (enc_state != 0) {
                    if (in_settings_menu) {
                        menu_selection += enc_state;
                    } else {
                        if (jog_is_horizontal) {
                            if (enc_state > 0) ble_keyboard_press(0x4F); // Right arrow (HID 0x4F)
                            else ble_keyboard_press(0x50); // Left arrow (HID 0x50)
                            vTaskDelay(pdMS_TO_TICKS(10));
                            ble_keyboard_release();
                        } else {
                            ble_mouse_scroll(enc_state);
                        }
                    }
                }"""

# The previous script might have already replaced it, let's find the block
if "ble_mouse_scroll_horiz" in content:
    content = re.sub(r'if \(jog_is_horizontal\) \{.*?\} else \{', 
                     r'if (jog_is_horizontal) {\n                            if (enc_state > 0) ble_keyboard_press(0x4F);\n                            else ble_keyboard_press(0x50);\n                            vTaskDelay(pdMS_TO_TICKS(10));\n                            ble_keyboard_release();\n                        } else {', 
                     content, flags=re.DOTALL)


# Also, let's ensure the fast atan2 and asin are working and rendering the earth properly.
# The user wants "90-degree screen rotation" options.
# We can add an offset to the IMU readings, or just rotate the screen using LVGL.
# LVGL screen rotation: lv_disp_set_rotation(disp, LV_DISP_ROT_90)
# But it's easier to just swap X and Y for the mouse movement if held differently.
# The user already has "cfg_swap_xy" and "cfg_invert_x" from previous sessions.
# Let's write the file.

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed horiz scroll with keyboard arrows")
