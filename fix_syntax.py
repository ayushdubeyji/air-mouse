import re

with open('C:/Users/dell/Desktop/s3cam/src/main.c', 'r') as f:
    content = f.read()

# 1. Fix the ring generation syntax error
ring_generation_fixed = """            if (ring == 0) { // Yaw ring (Horizontal: XY plane)
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
            }"""
            
content = re.sub(
    r'            if \(ring == 0\) \{ // Yaw ring.*?ring_verts\[ring\]\[i\]\.z = 0;\n            \}\n        \}\n    \}',
    ring_generation_fixed + '\n        }\n    }',
    content,
    flags=re.DOTALL
)

# 2. Change cfg_screen_rot to cfg_orientation
content = re.sub(
    r'static bool cfg_screen_rot = false; // Screen orientation \(false=0, true=90 deg\)',
    'static int cfg_orientation = 0; // Mouse physical orientation (0=0, 1=90, 2=180, 3=270 deg)',
    content
)

# 3. load_settings & save_settings
content = re.sub(
    r'if \(nvs_get_u8\(my_handle, "scr_rot", &val8\) == ESP_OK\) cfg_screen_rot = \(val8 == 1\);',
    'if (nvs_get_u8(my_handle, "orient", &val8) == ESP_OK) cfg_orientation = val8;',
    content
)
content = re.sub(
    r'nvs_set_u8\(my_handle, "scr_rot", cfg_screen_rot \? 1 : 0\);',
    'nvs_set_u8(my_handle, "orient", cfg_orientation);',
    content
)

# 4. Settings menu update
content = re.sub(
    r'lv_label_set_text_fmt\(lv_obj_get_child\(items\[8\], 0\), LV_SYMBOL_IMAGE " Rotation 90°: %s", cfg_screen_rot \? "#00FF00 ON#" : "#FF0000 OFF#"\);',
    'lv_label_set_text_fmt(lv_obj_get_child(items[8], 0), LV_SYMBOL_IMAGE " Orientation: #00FF00 %d°#", cfg_orientation * 90);',
    content
)

# 5. Toggle logic in SW press
content = re.sub(
    r'else if\(menu_idx == 8\) \{\s*cfg_screen_rot = !cfg_screen_rot;',
    'else if(menu_idx == 8) {\n                            cfg_orientation = (cfg_orientation + 1) % 4;',
    content
)
# Wait, actually in my previous reading I didn't see what menu_idx == 8 did. It might not exist in the switch case.
# Let's just add it before the "update_settings_ui();" inside in_settings_menu
content = re.sub(
    r'                        else if\(menu_idx == 7\) \{(.*?)\n                        \}\n                        update_settings_ui\(\);',
    r'                        else if(menu_idx == 7) {\1\n                        }\n                        else if(menu_idx == 8) { cfg_orientation = (cfg_orientation + 1) % 4; }\n                        update_settings_ui();',
    content,
    flags=re.DOTALL
)

# 6. Apply rotation to mouse movement and sphere rendering
# Find mouse rotation logic
old_mouse_rot = """                    // Global axis shift: anticlockwise 90 degrees rotation
                    float rot_x = -move_y;
                    float rot_y = move_x;
                    move_x = rot_x;
                    move_y = rot_y;"""

new_mouse_rot = """                    // Global axis shift based on orientation setting
                    float rot_x = move_x;
                    float rot_y = move_y;
                    if (cfg_orientation == 0)      { rot_x = -move_y; rot_y = move_x; } // default 90deg anticlockwise as before
                    else if (cfg_orientation == 1) { rot_x = move_x; rot_y = move_y; }  // 0 deg
                    else if (cfg_orientation == 2) { rot_x = move_y; rot_y = -move_x; } // 90deg clockwise
                    else if (cfg_orientation == 3) { rot_x = -move_x; rot_y = -move_y; }// 180deg
                    move_x = rot_x;
                    move_y = rot_y;"""

content = content.replace(old_mouse_rot, new_mouse_rot)

# Sphere rotation logic
old_sphere_rot = """                                // Rotate sphere rendering 90 degrees anticlockwise to align with global axis shift
                                float rot_rx = -ry;
                                float rot_ry = rx;
                                rx = rot_rx;
                                ry = rot_ry;"""

new_sphere_rot = """                                // Rotate sphere rendering to match physical orientation
                                float rot_rx = rx;
                                float rot_ry = ry;
                                if (cfg_orientation == 0)      { rot_rx = -ry; rot_ry = rx; }
                                else if (cfg_orientation == 1) { rot_rx = rx; rot_ry = ry; }
                                else if (cfg_orientation == 2) { rot_rx = ry; rot_ry = -rx; }
                                else if (cfg_orientation == 3) { rot_rx = -rx; rot_ry = -ry; }
                                rx = rot_rx;
                                ry = rot_ry;"""

content = content.replace(old_sphere_rot, new_sphere_rot)

with open('C:/Users/dell/Desktop/s3cam/src/main.c', 'w') as f:
    f.write(content)

print("Done")
