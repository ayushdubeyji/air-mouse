with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Lower XCLK frequency to 10MHz to prevent VSYNC overflow
code = code.replace(
    'config.xclk_freq_hz = 20000000;',
    'config.xclk_freq_hz = 10000000;'
)

# 2. Change grab mode to CAMERA_GRAB_LATEST for real-time lag-free streaming
code = code.replace(
    'config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;',
    'config.grab_mode = CAMERA_GRAB_LATEST;'
)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Lowered camera XCLK to 10MHz and changed grab mode to CAMERA_GRAB_LATEST")
