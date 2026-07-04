with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Add #include "esp_mac.h"
include_block = '#include "esp_event.h"\n#include "esp_mac.h"'
if '#include "esp_mac.h"' not in content:
    content = content.replace('#include "esp_event.h"', include_block)

# 2. Add MAC address changing logic at the beginning of app_main
app_main_old = """void app_main(void)
{
    esp_err_t ret = nvs_flash_init();"""

app_main_new = """void app_main(void)
{
    // Change base MAC address slightly to force Android to clear cached BLE HID descriptors
    uint8_t base_mac[6];
    if (esp_read_mac(base_mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        base_mac[5] ^= 0x01; // Toggle last bit to guarantee a unique MAC address
        esp_base_mac_addr_set(base_mac);
    }

    esp_err_t ret = nvs_flash_init();"""

if app_main_old in content:
    content = content.replace(app_main_old, app_main_new)
    with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
        f.write(content)
    print("Success")
else:
    print("Failed to locate app_main block")
