import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\dell\Downloads\ESP32-S3-Touch-LCD-2-SchDoc.md', 'r', encoding='utf-8') as f:
    text = f.read()

# Find all occurrences of LCD_RST and print surrounding characters
for m in re.finditer(r'LCD_RST', text):
    start = max(0, m.start() - 100)
    end = min(len(text), m.end() + 100)
    print(f"Match: {text[start:end]}")
