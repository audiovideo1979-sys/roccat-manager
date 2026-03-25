"""Parse KONE_XP_AIR_TB.ini to find DPI profile data."""
import struct

ini_path = r"C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_TB.ini"

with open(ini_path, 'rb') as f:
    content = f.read()

# Find MainSetting=@ByteArray(...)
marker = b'MainSetting=@ByteArray('
idx = content.find(marker)
if idx < 0:
    print("MainSetting not found")
    exit()

start = idx + len(marker)
end = content.find(b')', start)
raw = content[start:end]

# Qt ByteArray uses \xNN for non-printable bytes
# Parse it properly
data = []
i = 0
while i < len(raw):
    b = raw[i]
    if b == ord('\\') and i + 1 < len(raw):
        next_b = raw[i + 1]
        if next_b == ord('x') and i + 3 < len(raw):
            hex_str = chr(raw[i+2]) + chr(raw[i+3])
            try:
                val = int(hex_str, 16)
                data.append(val)
                i += 4
                continue
            except ValueError:
                pass
        elif next_b == ord('0'):
            data.append(0)
            i += 2
            continue
        elif next_b == ord('n'):
            data.append(0x0a)
            i += 2
            continue
        elif next_b == ord('\\'):
            data.append(ord('\\'))
            i += 2
            continue
    data.append(b)
    i += 1

print(f"Decoded {len(data)} bytes from MainSetting")
print()

# Show hex dump of first 320 bytes
for row in range(0, min(len(data), 320), 16):
    hex_str = ' '.join(f'{b:02x}' for b in data[row:row+16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[row:row+16])
    print(f"  {row:04x}: {hex_str:<48s}  {ascii_str}")

print()

# Search for DPI values (16-bit LE)
print("DPI value search:")
for offset in range(0, min(len(data) - 1, 2000)):
    val = data[offset] | (data[offset + 1] << 8)
    if val in [400, 450, 500, 700, 800, 900, 1000, 1050, 1200, 1600, 2500, 3200, 4000]:
        print(f"  DPI {val} at offset {offset} (0x{offset:04x})")

# Also look for profile structure: 06 4e pattern
print()
print("Profile headers (06 4e or 06 XX 00 06 06):")
for i in range(len(data) - 5):
    if data[i] == 0x06 and data[i+1] == 0x4e:
        hex_str = ' '.join(f'{b:02x}' for b in data[i:i+30])
        print(f"  offset {i}: {hex_str}")
    elif data[i] == 0x06 and data[i+3] == 0x06 and data[i+4] == 0x06:
        hex_str = ' '.join(f'{b:02x}' for b in data[i:i+30])
        print(f"  offset {i}: {hex_str}")
