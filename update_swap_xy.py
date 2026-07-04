with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Swap XY to true when entering local feed
old_enter_local = """                if (menu_hover_index == 0) {
                    current_state = STATE_LOCAL_FEED;
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(img_camera, LV_OBJ_FLAG_HIDDEN);"""

new_enter_local = """                if (menu_hover_index == 0) {
                    current_state = STATE_LOCAL_FEED;
                    esp_lcd_panel_swap_xy(panel_handle, true); // Set to landscape for 320x240 camera
                    lv_obj_add_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                    lv_obj_clear_flag(img_camera, LV_OBJ_FLAG_HIDDEN);"""

code = code.replace(old_enter_local, new_enter_local)

# 2. Swap XY to false when leaving local feed
old_leave_local = """            if (event == 2) { // BACK
                current_state = STATE_MENU;
                mouse_active = false;
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(img_camera, LV_OBJ_FLAG_HIDDEN);"""

new_leave_local = """            if (event == 2) { // BACK
                current_state = STATE_MENU;
                mouse_active = false;
                esp_lcd_panel_swap_xy(panel_handle, false); // Set back to portrait 240x320 for menu
                lv_obj_clear_flag(menu_container, LV_OBJ_FLAG_HIDDEN);
                lv_obj_add_flag(img_camera, LV_OBJ_FLAG_HIDDEN);"""

code = code.replace(old_leave_local, new_leave_local)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Added dynamic swap_xy for camera feed")
