with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# Add esp_log_level_set to suppress cam_hal VSYNC overflow logs
old_camera_init_check = """    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK)
    {
        printf("Camera init failed with error 0x%x", err);
        vTaskDelete(NULL);
        return;
    }"""

new_camera_init_check = """    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK)
    {
        printf("Camera init failed with error 0x%x", err);
        vTaskDelete(NULL);
        return;
    }
    esp_log_level_set("cam_hal", ESP_LOG_ERROR);"""

code = code.replace(old_camera_init_check, new_camera_init_check)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Suppressed cam_hal warnings in main.c")
