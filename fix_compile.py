with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

# 1. Extract the function
import re
match = re.search(r'static void update_mouse_page_text\(void\) \{.*?\n\}\n', content, flags=re.DOTALL)
if match:
    func_text = match.group(0)
    content = content.replace(func_text, "")

    # 2. Insert it after the lock/config declarations
    insert_point = "static float cfg_deadzone = 10.0f;\n"
    content = content.replace(insert_point, insert_point + "\n" + func_text)

    with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
        f.write(content)
else:
    print("Function not found!")
