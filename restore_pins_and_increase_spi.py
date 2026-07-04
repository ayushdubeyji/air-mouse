with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Restore original camera pins
camera_pins_old = """#define Y9_GPIO_NUM 12
#define Y8_GPIO_NUM 14
#define Y7_GPIO_NUM 15
#define Y6_GPIO_NUM 16
#define Y5_GPIO_NUM 18
#define Y4_GPIO_NUM 20
#define Y3_GPIO_NUM 22
#define Y2_GPIO_NUM 19
#define VSYNC_GPIO_NUM 7
#define HREF_GPIO_NUM 9
#define PCLK_GPIO_NUM 17"""

camera_pins_new = """#define Y9_GPIO_NUM 2
#define Y8_GPIO_NUM 7
#define Y7_GPIO_NUM 10
#define Y6_GPIO_NUM 14
#define Y5_GPIO_NUM 11
#define Y4_GPIO_NUM 15
#define Y3_GPIO_NUM 13
#define Y2_GPIO_NUM 12
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM 4
#define PCLK_GPIO_NUM 9"""

code = code.replace(camera_pins_old, camera_pins_new)

# Re-define top camera configs
camera_top_old = """#define PWDN_GPIO_NUM 8
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 13
#define SIOD_GPIO_NUM 11
#define SIOC_GPIO_NUM 10"""

camera_top_new = """#define PWDN_GPIO_NUM 17
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 8
#define SIOD_GPIO_NUM 21
#define SIOC_GPIO_NUM 16"""

code = code.replace(camera_top_old, camera_top_new)

# 2. Increase SPI bus max_transfer_sz to hold full camera frame
old_spi_init = """.quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 4000,"""

new_spi_init = """.quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 320 * 240 * 2,"""

code = code.replace(old_spi_init, new_spi_init)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Restored original camera pins and increased SPI transfer size to 153,600 bytes")
