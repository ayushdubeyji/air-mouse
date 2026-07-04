import os
import re

main_path = r"C:\Users\dell\Desktop\s3cam\src\main.c"
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Include the earth texture
content = content.replace('#include "nvs.h"', '#include "nvs.h"\n#include "earth_texture.h"')

# 2. Remove sphere_lines and points, add canvas buffer
old_sphere_vars = """// 3D Sphere definitions
typedef struct { float x, y, z; } vec3_t;
#define SPHERE_RING_POINTS 16
static lv_obj_t *sphere_lines[6];
static lv_point_t sphere_points[6][SPHERE_RING_POINTS + 1];
static vec3_t ring_verts[6][SPHERE_RING_POINTS];"""

new_sphere_vars = """// 3D Earth Canvas definitions
#define EARTH_RADIUS 64
#define EARTH_DIAM (EARTH_RADIUS * 2)
static lv_obj_t *earth_canvas;
static lv_color_t *earth_cbuf;"""

content = content.replace(old_sphere_vars, new_sphere_vars)

# 3. Remove ring_colors, sphere_lines, precalculate loop, create canvas
old_ui_start = """    // 3D Sphere lines creation (Modified to a clean 3-axis orthogonal gyroscope)
    uint32_t ring_colors[6] = {0x00FFFF, 0xFF00FF, 0xFFFF00, 0, 0, 0}; // Cyan, Magenta, Yellow for Yaw, Pitch, Roll

    for(int i = 0; i < 6; i++) {
        sphere_lines[i] = lv_line_create(mouse_hud_cont);
        lv_line_set_points(sphere_lines[i], sphere_points[i], SPHERE_RING_POINTS + 1);
        lv_obj_set_style_line_width(sphere_lines[i], 3, 0);
        lv_obj_set_style_line_color(sphere_lines[i], lv_color_hex(ring_colors[i]), 0);
        lv_obj_set_style_line_opa(sphere_lines[i], LV_OPA_90, 0);
        // lv_obj_add_flag(sphere_lines[i], LV_OBJ_FLAG_HIDDEN); // Rings are fixed now
    }"""

new_ui_start = """    // 3D Earth Canvas creation
    earth_canvas = lv_canvas_create(mouse_hud_cont);
    earth_cbuf = heap_caps_malloc(EARTH_DIAM * EARTH_DIAM * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    if (!earth_cbuf) earth_cbuf = heap_caps_malloc(EARTH_DIAM * EARTH_DIAM * sizeof(lv_color_t), MALLOC_CAP_DMA); // Fallback
    lv_canvas_set_buffer(earth_canvas, earth_cbuf, EARTH_DIAM, EARTH_DIAM, LV_IMG_CF_TRUE_COLOR);
    lv_obj_align(earth_canvas, LV_ALIGN_CENTER, 0, 0);
    lv_canvas_fill_bg(earth_canvas, lv_color_hex(0x050510), LV_OPA_TRANSP);"""

content = content.replace(old_ui_start, new_ui_start)

# 4. Remove ring precalculation
old_ring_calc = """    // Precalculate ring vertices for 3 orthogonal gyroscope rings
    for (int ring = 0; ring < 6; ring++) {
        for (int i = 0; i < SPHERE_RING_POINTS; i++) {
            float angle = i * (2.0f * 3.14159265f / SPHERE_RING_POINTS);

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
        }
    }"""
content = content.replace(old_ring_calc, "")

# 5. Remove "Ready" label as requested
old_status = """    lbl_status = lv_label_create(hud_labels_cont);
    lv_label_set_text(lbl_status, "Ready");
    lv_obj_align(lbl_status, LV_ALIGN_CENTER, 0, -15);
    lv_obj_set_style_text_color(lbl_status, lv_color_hex(0xFFFFFF), 0);"""

new_status = """    lbl_status = lv_label_create(hud_labels_cont);
    lv_label_set_text(lbl_status, "");
    lv_obj_align(lbl_status, LV_ALIGN_CENTER, 0, -15);
    lv_obj_set_style_text_color(lbl_status, lv_color_hex(0xFFFFFF), 0);"""
content = content.replace(old_status, new_status)
content = content.replace('lv_label_set_text(lbl_status, "READY");', 'lv_label_set_text(lbl_status, "");')

# 6. Replace sphere draw loop with earth texture mapping
# Find start of Sphere Breathing & Drawing
draw_start_idx = content.find('                        // Sphere Breathing & Drawing')
draw_end_idx = content.find('                        lvgl_unlock();', draw_start_idx)

earth_draw_code = """                        // 3D Earth Texture Mapping Rendering
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
                        
                        // We iterate over the canvas and map each pixel to a 3D ray, then to lon/lat
                        for(int cy = 0; cy < EARTH_DIAM; cy++) {
                            float y = (cy - EARTH_RADIUS) / (float)EARTH_RADIUS;
                            for(int cx = 0; cx < EARTH_DIAM; cx++) {
                                float x = (cx - EARTH_RADIUS) / (float)EARTH_RADIUS;
                                float dist_sq = x*x + y*y;
                                
                                if (dist_sq <= 1.0f) {
                                    // Calculate z on the sphere surface
                                    float z = -sqrtf(1.0f - dist_sq); // negative z points into screen
                                    
                                    // Rotate the 3D point using the inverse IMU rotation
                                    float rx = r00*x + r10*y + r20*z;
                                    float ry = r01*x + r11*y + r21*z;
                                    float rz = r02*x + r12*y + r22*z;
                                    
                                    // Map to longitude and latitude
                                    float u = 0.5f + (atan2f(rz, rx) / (2.0f * 3.14159265f));
                                    float v = 0.5f - (asinf(ry) / 3.14159265f);
                                    
                                    int tx = (int)(u * earth_width) % earth_width;
                                    int ty = (int)(v * earth_height);
                                    if (ty >= earth_height) ty = earth_height - 1;
                                    if (ty < 0) ty = 0;
                                    
                                    uint16_t color_val = earth_texture_map[ty * earth_width + tx];
                                    
                                    // Simple shading based on Z normal
                                    float brightness = -z; // max 1.0 at center, 0 at edge
                                    if (brightness < 0.2f) brightness = 0.2f; // ambient
                                    
                                    // RGB565 to RGB888, shade, back to RGB565 (or directly shade if possible, simplified here)
                                    uint8_t r_col = (color_val >> 11) & 0x1F;
                                    uint8_t g_col = (color_val >> 5) & 0x3F;
                                    uint8_t b_col = color_val & 0x1F;
                                    
                                    r_col = (uint8_t)(r_col * brightness);
                                    g_col = (uint8_t)(g_col * brightness);
                                    b_col = (uint8_t)(b_col * brightness);
                                    
                                    lv_color_t c;
                                    c.ch.red = r_col;
                                    c.ch.green = g_col;
                                    c.ch.blue = b_col;
                                    
                                    earth_cbuf[cy * EARTH_DIAM + cx] = c;
                                } else {
                                    earth_cbuf[cy * EARTH_DIAM + cx] = bg_color;
                                }
                            }
                        }
                        lv_obj_invalidate(earth_canvas);
"""

content = content[:draw_start_idx] + earth_draw_code + content[draw_end_idx:]

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Applied 3D Earth rendering logic.")
