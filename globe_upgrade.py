with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Update sphere array sizes from 3 to 6
content = content.replace("static lv_obj_t *sphere_lines[3];", "static lv_obj_t *sphere_lines[6];")
content = content.replace("static lv_point_t sphere_points[3][SPHERE_RING_POINTS + 1];", "static lv_point_t sphere_points[6][SPHERE_RING_POINTS + 1];")
content = content.replace("static vec3_t ring_verts[3][SPHERE_RING_POINTS];", "static vec3_t ring_verts[6][SPHERE_RING_POINTS];")

# 2. Update loop sizes in main.c (for i<3 or ring<3)
# To avoid replacing unrelated code, let's target the exact flag set lines
content = content.replace("for(int i=0; i<3; i++) lv_obj_clear_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN);", 
                          "for(int i=0; i<6; i++) lv_obj_clear_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN);")
content = content.replace("for(int i=0; i<3; i++) lv_obj_add_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN);", 
                          "for(int i=0; i<6; i++) lv_obj_add_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN);")

# 3. Update drawing scale and loop in imu_task (lines 456-472)
old_draw_loop = """                        float z_off = 3.2f;
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
                        }"""

# Scale is increased from 95.0 to 125.0 to make the sphere significantly bigger!
new_draw_loop = """                        float z_off = 3.2f;
                        float scale = 125.0f;

                        for (int ring = 0; ring < 6; ring++) {
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
                        }"""

content = content.replace(old_draw_loop, new_draw_loop)

# 4. Update ring precalculation and line creation in lvgl_camera_ui_init
old_init_loop = """    // Precalculate ring vertices
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
    }"""

new_init_loop = """    // Precalculate ring vertices for 6 rings (3 longitude, 3 latitude)
    for (int ring = 0; ring < 6; ring++) {
        for (int i = 0; i < SPHERE_RING_POINTS; i++) {
            float angle = i * (2.0f * 3.14159265f / SPHERE_RING_POINTS);
            if (ring == 0) { // Longitude 0 deg
                ring_verts[ring][i].x = cosf(angle);
                ring_verts[ring][i].y = 0;
                ring_verts[ring][i].z = sinf(angle);
            } else if (ring == 1) { // Longitude 60 deg
                ring_verts[ring][i].x = cosf(angle) * 0.5f;       // cos(60) = 0.5
                ring_verts[ring][i].y = cosf(angle) * 0.866025f;  // sin(60) = 0.866
                ring_verts[ring][i].z = sinf(angle);
            } else if (ring == 2) { // Longitude 120 deg
                ring_verts[ring][i].x = cosf(angle) * -0.5f;      // cos(120) = -0.5
                ring_verts[ring][i].y = cosf(angle) * 0.866025f;  // sin(120) = 0.866
                ring_verts[ring][i].z = sinf(angle);
            } else if (ring == 3) { // Latitude 0 deg (Equator)
                ring_verts[ring][i].x = cosf(angle);
                ring_verts[ring][i].y = sinf(angle);
                ring_verts[ring][i].z = 0;
            } else if (ring == 4) { // Latitude +45 deg (Upper Lat)
                ring_verts[ring][i].x = cosf(angle) * 0.707107f;  // cos(45) = 0.707
                ring_verts[ring][i].y = sinf(angle) * 0.707107f;  // sin(45) = 0.707
                ring_verts[ring][i].z = 0.707107f;
            } else if (ring == 5) { // Latitude -45 deg (Lower Lat)
                ring_verts[ring][i].x = cosf(angle) * 0.707107f;
                ring_verts[ring][i].y = sinf(angle) * 0.707107f;
                ring_verts[ring][i].z = -0.707107f;
            }
        }
    }

    for(int i = 0; i < 6; i++) {
        sphere_lines[i] = lv_line_create(parent);
        lv_line_set_points(sphere_lines[i], sphere_points[i], SPHERE_RING_POINTS + 1);
        lv_obj_add_style(sphere_lines[i], &style_line, 0);
    }"""

content = content.replace(old_init_loop, new_init_loop)

# 5. Push the text label to the bottom
old_label_align = "lv_obj_align(mouse_info_label, LV_ALIGN_TOP_LEFT, 5, 5);"
new_label_align = """lv_obj_align(mouse_info_label, LV_ALIGN_BOTTOM_MID, 0, -20);
    lv_obj_set_style_text_align(mouse_info_label, LV_TEXT_ALIGN_CENTER, 0);"""

content = content.replace(old_label_align, new_label_align)

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)

print("Success")
