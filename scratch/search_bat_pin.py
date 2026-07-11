import zlib
import re

def parse_texts(filename):
    with open(filename, 'rb') as f:
        content = f.read()
    stream_objs = re.findall(b'<<([^>]*?)>>\\s*stream\\r?\\n(.*?)\\r?\\nendstream', content, re.DOTALL)
    all_texts = []
    for idx, (meta, data) in enumerate(stream_objs):
        try:
            decompressed = zlib.decompress(data)
        except Exception:
            try:
                decompressed = zlib.decompress(data, -15)
            except Exception:
                continue
        text = decompressed.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        cx, cy = 0.0, 0.0
        for line in lines:
            m_td = re.search(r'^\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+T[dD]', line)
            if m_td:
                cx += float(m_td.group(1)); cy += float(m_td.group(2))
            m_tm = re.search(r'^\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+Tm', line)
            if m_tm:
                cx = float(m_tm.group(5)); cy = float(m_tm.group(6))
            m_tj = re.search(r'\((.*?)\)\s*Tj', line)
            if m_tj:
                all_texts.append((idx, cx, cy, m_tj.group(1)))
            m_tj2 = re.search(r'\[(.*?)\]\s*TJ', line)
            if m_tj2:
                str_matches = re.findall(r'\((.*?)\)', m_tj2.group(1))
                all_texts.append((idx, cx, cy, "".join(str_matches)))
    return all_texts

texts = parse_texts("schematic.pdf")
matches = [t for t in texts if 'NLLCD0RST' in t[3]]
for stream, x, y, text in matches:
    print(f"\nMatch: Stream {stream}, x={x:.1f}, y={y:.1f}: {text}")
    nearby = [t for t in texts if t[0] == stream and abs(t[1]-x) < 150 and abs(t[2]-y) < 150]
    nearby.sort(key=lambda t: (t[2], t[1]))
    print("  --- Nearby texts ---")
    for s, cx, cy, ct in nearby:
        print(f"    x={cx:.1f}, y={cy:.1f}: {ct}")
