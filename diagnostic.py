import re

ws = open('src/webserver.c', encoding='utf-8').read()
code = open('src/main.c', encoding='utf-8').read()
sdk = open('sdkconfig.esp32-s3-lcd-2', encoding='utf-8').read()

print('=== webserver.c init order ===')
lines = ws.split('\n')
for i, l in enumerate(lines):
    triggers = ['esp_netif_init', 'esp_wifi_init', 'esp_wifi_start', 
                'esp_netif_create', 'httpd_start', 'toggle_wifi', 
                'esp_camera_init']
    if any(x in l for x in triggers):
        print('  Line %d: %s' % (i+1, l.strip()))

print()
print('=== sdkconfig coex check ===')
keys = ['CONFIG_ESP_COEX_SW_COEXIST_ENABLE', 'CONFIG_BT_NIMBLE_ENABLED',
        'CONFIG_ESP_WIFI_ENABLED', 'CONFIG_BT_ENABLED',
        'CONFIG_BT_NIMBLE_MAX_CONNECTIONS', 'CONFIG_ESP_WIFI_NVS_ENABLED']
for key in keys:
    m = re.search(r'^' + key + r'=.*', sdk, re.MULTILINE)
    print('  %s: %s' % (key, m.group() if m else 'NOT FOUND'))

print()
print('=== main.c: nvs/event/ble/webserver line numbers ===')
for label, pattern in [('nvs_flash_init', 'nvs_flash_init'), 
                        ('esp_event_loop', 'esp_event_loop_create_default'),
                        ('ble_mouse_init', 'ble_mouse_init'),
                        ('start_webserver', 'start_webserver'),
                        ('esp_base_mac_addr_set', 'esp_base_mac_addr_set')]:
    idxs = [i+1 for i,l in enumerate(code.split('\n')) if pattern in l]
    print('  %s: lines %s' % (label, idxs))

print()
print('=== BLE advertising interval check (ble_mouse.c) ===')
ble = open('src/ble_mouse.c', encoding='utf-8').read()
lines = ble.split('\n')
for i, l in enumerate(lines):
    if any(x in l for x in ['itvl_min', 'itvl_max', 'adv_params']):
        print('  Line %d: %s' % (i+1, l.strip()))
