with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Lower LCD Pixel Clock to a highly stable 40 MHz (from 80 MHz)
code = code.replace(
    '#define EXAMPLE_LCD_PIXEL_CLOCK_HZ (80 * 1000 * 1000)',
    '#define EXAMPLE_LCD_PIXEL_CLOCK_HZ (40 * 1000 * 1000)'
)

# 2. Increase camera task priority and stack size to prevent VSYNC overflow
old_task_create = 'xTaskCreatePinnedToCore(camera_task, "camera_task_task", 1024 * 3, NULL, 1, NULL, 0);'
new_task_create = 'xTaskCreatePinnedToCore(camera_task, "camera_task_task", 1024 * 6, NULL, 5, NULL, 0);'

code = code.replace(old_task_create, new_task_create)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Adjusted LCD clock to 40MHz and increased camera task priority to 5")
