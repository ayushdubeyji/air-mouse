idf_component_register(SRCS "main.c" "ble_mouse.c" "mahony.c"
                    INCLUDE_DIRS "."
                    PRIV_REQUIRES esp_wifi esp_http_server bt)
