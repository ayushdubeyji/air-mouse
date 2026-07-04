import os
from PIL import Image

def rgb_to_rgb565_be(r, g, b):
    # 5 bits red, 6 bits green, 5 bits blue
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    
    val = (r5 << 11) | (g6 << 5) | b5
    
    # Big Endian: High byte first, then low byte
    high = (val >> 8) & 0xFF
    low = val & 0xFF
    
    return f"0x{high:02X}{low:02X}"

def convert():
    img_path = r"C:\Users\dell\Desktop\s3cam\earth\Maps\Color Map.jpg"
    out_path = r"C:\Users\dell\Desktop\s3cam\src\earth_texture.h"
    
    print(f"Loading {img_path}...")
    try:
        img = Image.open(img_path)
    except Exception as e:
        print(f"Error opening image: {e}")
        return
        
    img = img.convert('RGB')
    
    # Resize to 256x128 using LANCZOS
    new_width = 256
    new_height = 128
    
    print(f"Resizing to {new_width}x{new_height}...")
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    pixels = list(img.getdata())
    
    print("Generating C array...")
    
    with open(out_path, 'w') as f:
        f.write("// Auto-generated RGB565 Earth Texture (standard: R bits15-11, G bits10-5, B bits4-0)\n")
        f.write("#include <stdint.h>\n\n")
        f.write(f"const uint16_t earth_width = {new_width};\n")
        f.write(f"const uint16_t earth_height = {new_height};\n\n")
        f.write("const uint16_t earth_texture_map[] = {\n")
        
        for i, (r, g, b) in enumerate(pixels):
            hex_val = rgb_to_rgb565_be(r, g, b)
            f.write(hex_val)
            if i < len(pixels) - 1:
                f.write(",")
            if (i + 1) % 16 == 0:
                f.write("\n")
                
        f.write("\n};\n")
        
    print(f"Done! Saved to {out_path}")

if __name__ == "__main__":
    convert()
