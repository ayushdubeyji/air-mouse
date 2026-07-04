with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace driver/i2c.h with driver/i2c_master.h
code = code.replace('#include "driver/i2c.h"', '#include "driver/i2c_master.h"')

# 2. Re-write QMI8658 I2C driver to use the new driver_ng I2C master API
old_i2c_impl = """#define QMI8658_ADDR 0x6B
static float gyro_off_x = 0, gyro_off_y = 0, gyro_off_z = 0;
static bool is_calibrating = false;
static bool mouse_active = false;

static esp_err_t i2c_write_reg(uint8_t reg, uint8_t data) {
    uint8_t write_buf[2] = {reg, data};
    return i2c_master_write_to_device(EXAMPLE_I2C_NUM, QMI8658_ADDR, write_buf, 2, pdMS_TO_TICKS(100));
}
static esp_err_t i2c_read_reg(uint8_t reg, uint8_t *data, size_t len) {
    return i2c_master_write_read_device(EXAMPLE_I2C_NUM, QMI8658_ADDR, &reg, 1, data, len, pdMS_TO_TICKS(100));
}

static void imu_init(void) {
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = EXAMPLE_PIN_NUM_I2C_SDA,
        .scl_io_num = EXAMPLE_PIN_NUM_I2C_SCL,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = 400000,
    };
    i2c_param_config(EXAMPLE_I2C_NUM, &conf);
    i2c_driver_install(EXAMPLE_I2C_NUM, conf.mode, 0, 0, 0);"""

new_i2c_impl = """#define QMI8658_ADDR 0x6B
static float gyro_off_x = 0, gyro_off_y = 0, gyro_off_z = 0;
static bool is_calibrating = false;
static bool mouse_active = false;

static i2c_master_dev_handle_t imu_dev_handle = NULL;

static esp_err_t i2c_write_reg(uint8_t reg, uint8_t data) {
    uint8_t write_buf[2] = {reg, data};
    return i2c_master_transmit(imu_dev_handle, write_buf, 2, pdMS_TO_TICKS(100));
}
static esp_err_t i2c_read_reg(uint8_t reg, uint8_t *data, size_t len) {
    return i2c_master_transmit_receive(imu_dev_handle, &reg, 1, data, len, pdMS_TO_TICKS(100));
}

static void imu_init(void) {
    i2c_master_bus_config_t i2c_mst_config = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = EXAMPLE_I2C_NUM,
        .scl_io_num = EXAMPLE_PIN_NUM_I2C_SCL,
        .sda_io_num = EXAMPLE_PIN_NUM_I2C_SDA,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus_handle;
    ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config, &bus_handle));

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = QMI8658_ADDR,
        .scl_speed_hz = 400000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle, &dev_cfg, &imu_dev_handle));"""

code = code.replace(old_i2c_impl, new_i2c_impl)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated I2C driver to new ESP-IDF driver_ng API")
