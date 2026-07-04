import re

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

pattern = re.compile(r'(if\s*\(lvgl_lock\(-1\)\)\s*\{\s*// 3D Cube Rotation using Quaternions.*?lvgl_unlock\(\);\s*\})', re.DOTALL)
match = pattern.search(content)

if match:
    old_block = match.group(1)
    new_block = """static uint32_t last_cube_draw = 0;
                uint32_t current_time = xTaskGetTickCount() * portTICK_PERIOD_MS;
                // Throttle cube drawing to ~30 FPS to stop LVGL lag and free CPU
                if (current_time - last_cube_draw > 33) {
                    last_cube_draw = current_time;
                    """ + old_block + """
                }"""
    content = content.replace(old_block, new_block)
    with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
        f.write(content)
    print("Success")
else:
    print("Not found")
