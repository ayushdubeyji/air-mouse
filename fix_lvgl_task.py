with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

task_old = """static void task(void *param)
{
    // ESP_LOGI(TAG, "run");
    while (1)
    {
        uint32_t task_delay_ms = EXAMPLE_LVGL_TASK_MAX_DELAY_MS;
        while (1)
        {
            // Lock the mutex due to the LVGL APIs are not thread-safe
            if (lvgl_lock(-1))
            {
                task_delay_ms = lv_timer_handler();
                // Release the mutex
                lvgl_unlock();
            }
            if (task_delay_ms > EXAMPLE_LVGL_TASK_MAX_DELAY_MS)
            {
                task_delay_ms = EXAMPLE_LVGL_TASK_MAX_DELAY_MS;
            }
            else if (task_delay_ms < EXAMPLE_LVGL_TASK_MIN_DELAY_MS)
            {
                task_delay_ms = EXAMPLE_LVGL_TASK_MIN_DELAY_MS;
            }
            vTaskDelay(pdMS_TO_TICKS(task_delay_ms));
        }
    }
}"""

task_new = """static void task(void *param)
{
    while (1)
    {
        // Flush and process graphics at a stable 60 FPS (approx 16ms delay)
        // This is crucial for rendering fluid animations / 3D updates driven by external tasks
        if (lvgl_lock(-1))
        {
            lv_timer_handler();
            lvgl_unlock();
        }
        vTaskDelay(pdMS_TO_TICKS(16));
    }
}"""

if task_old in content:
    content = content.replace(task_old, task_new)
    with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
        f.write(content)
    print("Success")
else:
    # Try with raw string replaces or regex if formatting differs slightly
    import re
    pattern = re.compile(r'static void task\(void \*param\)\s*\{\s*// ESP_LOGI\(TAG, "run"\);\s*while \(1\).*?vTaskDelay\(pdMS_TO_TICKS\(task_delay_ms\)\);\s*\}\s*\}\s*\}', re.DOTALL)
    match = pattern.search(content)
    if match:
        content = content.replace(match.group(0), task_new)
        with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
            f.write(content)
        print("Success regex")
    else:
        print("Not found")
