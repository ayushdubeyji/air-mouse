with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update display SPI max_transfer_sz to match 240x40 partial buffer size (19,200 bytes)
old_spi_init = """.quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 320 * 240 * 2,"""

new_spi_init = """.quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 240 * 40 * 2,"""

code = code.replace(old_spi_init, new_spi_init)

# 2. Update lv_port_disp_init to allocate 240x40 partial buffers in internal DMA RAM
old_lv_port = """void lv_port_disp_init(void)
{
    static lv_disp_draw_buf_t draw_buf;
    lv_color_t *buf1 = heap_caps_malloc(EXAMPLE_LCD_H_RES * EXAMPLE_LCD_V_RES * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    assert(buf1);
    lv_color_t *buf2 = heap_caps_malloc(EXAMPLE_LCD_H_RES * EXAMPLE_LCD_V_RES * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    assert(buf2);
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2,
                          EXAMPLE_LCD_H_RES * EXAMPLE_LCD_V_RES); /*Initialize the display buffer*/"""

new_lv_port = """void lv_port_disp_init(void)
{
    static lv_disp_draw_buf_t draw_buf;
    lv_color_t *buf1 = heap_caps_malloc(EXAMPLE_LCD_H_RES * 40 * sizeof(lv_color_t), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    assert(buf1);
    lv_color_t *buf2 = heap_caps_malloc(EXAMPLE_LCD_H_RES * 40 * sizeof(lv_color_t), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    assert(buf2);
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2,
                          EXAMPLE_LCD_H_RES * 40); /*Initialize the display buffer*/"""

code = code.replace(old_lv_port, new_lv_port)

# Set full_refresh to 0
code = code.replace("disp_drv.full_refresh = 1;", "disp_drv.full_refresh = 0;")

# 3. Update camera resolution configuration to 240x240 (square)
code = code.replace("config.frame_size = FRAMESIZE_QVGA;", "config.frame_size = FRAMESIZE_240X240;")

# 4. Remove dynamic swap_xy logic
code = code.replace("esp_lcd_panel_swap_xy(panel_handle, true); // Set to landscape for 320x240 camera", "")
code = code.replace("esp_lcd_panel_swap_xy(panel_handle, false); // Set back to portrait 240x320 for menu", "")

# 5. Rewrite camera_task to use LVGL rendering
old_camera_task = """static void camera_task(void *param)
{
    camera_fb_t *pic;
    lv_img_dsc_t img_dsc;
    img_dsc.header.always_zero = 0;
    img_dsc.header.w = 320;
    img_dsc.header.h = 240;
    img_dsc.data_size = 320 * 240 * 2;
    img_dsc.header.cf = LV_IMG_CF_TRUE_COLOR;
    img_dsc.data = NULL;

    while (1)
    {
        if (current_state == STATE_LOCAL_FEED) {
            pic = esp_camera_fb_get();
            if (NULL != pic)
            {
                // Swap bytes for RGB565 to match ST7789 LCD expectations
                uint16_t *pixels = (uint16_t *)pic->buf;
                size_t num_pixels = (pic->width * pic->height);
                for (size_t i = 0; i < num_pixels; i++) {
                    pixels[i] = (pixels[i] >> 8) | (pixels[i] << 8);
                }

                if (lvgl_lock(-1))
                {
                    // Draw directly to the display to prevent tearing and freeze from async LVGL read
                    esp_lcd_panel_draw_bitmap(panel_handle, 0, 0, pic->width, pic->height, pic->buf);
                    lvgl_unlock();
                }
                esp_camera_fb_return(pic);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(15));
    }
    vTaskDelete(NULL);
}"""

new_camera_task = """static void camera_task(void *param)
{
    camera_fb_t *pic;
    lv_img_dsc_t img_dsc;
    img_dsc.header.always_zero = 0;
    img_dsc.header.w = 240;
    img_dsc.header.h = 240;
    img_dsc.data_size = 240 * 240 * 2;
    img_dsc.header.cf = LV_IMG_CF_TRUE_COLOR;
    img_dsc.data = NULL;

    while (1)
    {
        if (current_state == STATE_LOCAL_FEED) {
            pic = esp_camera_fb_get();
            if (NULL != pic)
            {
                // Swap bytes for RGB565 to match ST7789 LCD expectations
                uint16_t *pixels = (uint16_t *)pic->buf;
                size_t num_pixels = (pic->width * pic->height);
                for (size_t i = 0; i < num_pixels; i++) {
                    pixels[i] = (pixels[i] >> 8) | (pixels[i] << 8);
                }

                img_dsc.data = pic->buf;
                if (lvgl_lock(-1))
                {
                    lv_img_set_src(img_camera, &img_dsc);
                    lv_obj_invalidate(img_camera);
                    lvgl_unlock();
                }
                esp_camera_fb_return(pic);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(15));
    }
    vTaskDelete(NULL);
}"""

code = code.replace(old_camera_task, new_camera_task)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully updated main.c to use 240x40 DMA buffers and 240x240 LVGL camera rendering")
