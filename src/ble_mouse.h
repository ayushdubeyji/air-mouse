#pragma once
#include <stdint.h>
#include <stdbool.h>

void ble_mouse_init(int device_id);
void ble_mouse_send_report(int8_t dx, int8_t dy, int8_t wheel, uint8_t buttons);
void ble_mouse_send_keyboard(uint8_t modifier, uint8_t key1);
void ble_mouse_send_media(uint8_t media_keys);
void ble_keyboard_send_consumer(uint16_t key);
bool ble_mouse_is_connected(void);
