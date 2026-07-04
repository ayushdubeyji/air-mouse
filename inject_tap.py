with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Enable Tap Engine in imu_init
imu_init_old = """
        i2c_write_reg(0x02, 0x40); // CTRL1: Enable Auto-Increment (Bit 6 = 1)
        i2c_write_reg(0x03, 0x24); // CTRL2
        i2c_write_reg(0x04, 0x64); // CTRL3
        i2c_write_reg(0x08, 0x03); // CTRL7
        ESP_LOGI(TAG, "QMI8658 registers configured successfully!");
"""
imu_init_new = """
        i2c_write_reg(0x02, 0x40); // CTRL1: Enable Auto-Increment (Bit 6 = 1)
        i2c_write_reg(0x03, 0x24); // CTRL2
        i2c_write_reg(0x04, 0x64); // CTRL3
        i2c_write_reg(0x08, 0x03); // CTRL7
        i2c_write_reg(0x09, 0x01); // CTRL8: Enable Tap Engine
        ESP_LOGI(TAG, "QMI8658 registers configured successfully!");
"""
content = content.replace(imu_init_old, imu_init_new)

# 2. Add tap detection variables to imu_task
imu_task_old = """
static void imu_task(void *param) {
    uint8_t data[12];
    int calib_count = 0;
    long sum_gx = 0, sum_gy = 0, sum_gz = 0;

    while(1) {
        // Read 12 bytes starting at 0x35 (ACCEL_X_L) to get Accel + Gyro
"""
imu_task_new = """
static void imu_task(void *param) {
    uint8_t data[12];
    int calib_count = 0;
    long sum_gx = 0, sum_gy = 0, sum_gz = 0;
    uint32_t last_tap_time = 0;
    int total_taps = 0;

    while(1) {
        // --- Tap Detection Logic ---
        uint8_t status_int = 0;
        if (i2c_read_reg(0x2D, &status_int, 1) == ESP_OK) {
            if (status_int & 0x02) { // Tap interrupt bit
                uint8_t tap_status = 0;
                i2c_read_reg(0x59, &tap_status, 1);
                int tap_num = tap_status & 0x03; // 1 = Single, 2 = Double
                if (tap_num == 1 || tap_num == 2) {
                    uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;
                    if (now - last_tap_time > 400) {
                        total_taps = 0;
                    }
                    total_taps += tap_num;
                    last_tap_time = now;
                    ESP_LOGI(TAG, "Sensor Tap detected! Num: %d, Total: %d", tap_num, total_taps);
                }
            }
        }
        
        uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;
        if (total_taps > 0 && (now - last_tap_time > 350)) {
            ESP_LOGI(TAG, "Processing taps: %d", total_taps);
            if (total_taps == 1) {
                if (mouse_active) {
                    ble_mouse_send_report(0, 0, 0x01); // Left Click
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_report(0, 0, 0x00);
                }
            } else if (total_taps == 2) {
                if (mouse_active) {
                    ble_mouse_send_report(0, 0, 0x02); // Right Click
                    vTaskDelay(pdMS_TO_TICKS(50));
                    ble_mouse_send_report(0, 0, 0x00);
                }
            } else if (total_taps >= 3) {
                if (mouse_active) {
                    handle_button_event(1); // Long press simulates 'Exit'
                }
            }
            total_taps = 0;
        }
        // ---------------------------

        // Read 12 bytes starting at 0x35 (ACCEL_X_L) to get Accel + Gyro
"""
content = content.replace(imu_task_old, imu_task_new)

# 3. Add handle_button_event declaration above imu_task if it's not there so we can call it
# Actually, handle_button_event is defined BEFORE imu_task in main.c, so it's already in scope!
# (handle_button_event is near line 400, imu_task is near line 500)

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)
