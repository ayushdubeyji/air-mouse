with open("src/main.c", "r", encoding="utf-8") as f:
    code = f.read()

# Replace high sensitivity multiplier 0.005f with a much gentler 0.0003f
code = code.replace(
    'dx_val = copysignf(powf(abs_x - cfg_deadzone, 1.35f) * cfg_sensitivity * 0.005f, raw_x);',
    'dx_val = copysignf(powf(abs_x - cfg_deadzone, 1.35f) * cfg_sensitivity * 0.0003f, raw_x);'
)

code = code.replace(
    'dy_val = copysignf(powf(abs_y - cfg_deadzone, 1.35f) * cfg_sensitivity * 0.005f, raw_y);',
    'dy_val = copysignf(powf(abs_y - cfg_deadzone, 1.35f) * cfg_sensitivity * 0.0003f, raw_y);'
)

with open("src/main.c", "w", encoding="utf-8") as f:
    f.write(code)

print("Scaled down Air Mouse sensitivity multiplier to 0.0003f")
