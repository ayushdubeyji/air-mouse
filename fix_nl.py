with open("C:/Users/dell/Desktop/s3cam/src/main.c", "r") as f:
    content = f.read()

import re
content = re.sub(r'\\n"', r'\n"', content)

with open("C:/Users/dell/Desktop/s3cam/src/main.c", "w") as f:
    f.write(content)
