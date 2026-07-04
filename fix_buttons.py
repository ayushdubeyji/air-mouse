import re

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# Replace button task
start_idx = content.find("} else if (event == 2) { // Double click:")
if start_idx != -1:
    end_idx = content.find("} else if (event == 1) { // Long press: Back to menu", start_idx)
    content = content[:start_idx] + "} else if (event == 2) { // Double click: Cycle Settings\n                static int setting_focus = 0;\n                setting_focus = (setting_focus + 1) % 5;\n                if (setting_focus == 0) { cfg_sensitivity += 0.5f; if (cfg_sensitivity > 4.0f) cfg_sensitivity = 0.5f; }\n                else if (setting_focus == 1) { cfg_deadzone += 5.0f; if (cfg_deadzone > 30.0f) cfg_deadzone = 5.0f; }\n                else if (setting_focus == 2) { cfg_invert_x = !cfg_invert_x; }\n                else if (setting_focus == 3) { cfg_invert_y = !cfg_invert_y; }\n                else if (setting_focus == 4) { cfg_swap_xy = !cfg_swap_xy; }\n            " + content[end_idx:]

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)
