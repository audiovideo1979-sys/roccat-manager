"""Parse KONE_XP_AIR_TB.ini - read raw bytes and decode Qt ByteArray."""
import re

ini_path = r"C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_TB.ini"

with open(ini_path, 'rb') as f:
    raw = f.read()

# Find MainSetting line
idx = raw.find(b'MainSetting=@ByteArray(')
start = idx + len(b'MainSetting=@ByteArray(')

# Find matching closing paren - scan for unescaped )
i = start
depth = 0
while i < len(raw):
    if raw[i] == ord(')') and (i == 0 or raw[i-1] != ord('\\')):
        break
    i += 1
end = i

chunk = raw[start:end]
print(f"Raw ByteArray: {len(chunk)} bytes")
print(f"First 100 raw: {chunk[:100]}")
print()

# Qt ByteArray decoding:
# \xNN = hex byte (1-2 hex digits)
# \0 = null
# \n = newline (0x0a)
# \r = CR (0x0d)
# \t = tab (0x09)
# \f = form feed (0x0c)
# \\ = backslash
# printable chars = themselves
data = []
i = 0
while i < len(chunk):
    if chunk[i] == ord('\\') and i + 1 < len(chunk):
        nc = chunk[i+1]
        if nc == ord('x'):
            # Read 1-2 hex digits
            hex_s = ""
            j = i + 2
            while j < len(chunk) and j < i + 4:
                c = chr(chunk[j])
                if c in '0123456789abcdefABCDEF':
                    hex_s += c
                    j += 1
                else:
                    break
            if hex_s:
                data.append(int(hex_s, 16))
                i = j
                continue
        elif nc == ord('0'):
            data.append(0)
            i += 2
            continue
        elif nc == ord('n'):
            data.append(0x0a)
            i += 2
            continue
        elif nc == ord('r'):
            data.append(0x0d)
            i += 2
            continue
        elif nc == ord('t'):
            data.append(0x09)
            i += 2
            continue
        elif nc == ord('f'):
            data.append(0x0c)
            i += 2
            continue
        elif nc == ord('\\'):
            data.append(ord('\\'))
            i += 2
            continue
    data.append(chunk[i])
    i += 1

print(f"Decoded: {len(data)} bytes")
print()

# Hex dump
for row in range(0, min(len(data), 400), 25):
    hex_str = ' '.join(f'{b:02x}' for b in data[row:row+25])
    print(f"  {row:4d}: {hex_str}")

print()

# The structure should be:
# 4 bytes: number of profiles (big-endian int32)
# For each profile:
#   4 bytes: profile length (big-endian int32)
#   N bytes: profile data
if len(data) >= 4:
    num_profiles = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
    print(f"Number of profiles: {num_profiles}")

    offset = 4
    for p in range(min(num_profiles, 5)):
        if offset + 4 > len(data):
            break
        plen = (data[offset] << 24) | (data[offset+1] << 16) | (data[offset+2] << 8) | data[offset+3]
        print(f"\nProfile {p+1}: length={plen} bytes, offset={offset+4}")
        offset += 4

        if offset + plen > len(data):
            print(f"  (truncated, only {len(data)-offset} bytes left)")
            plen = len(data) - offset

        pdata = data[offset:offset+plen]
        hex_str = ' '.join(f'{b:02x}' for b in pdata[:30])
        print(f"  Data: {hex_str}")

        # Try to decode DPI values (16-bit LE starting at various offsets)
        if len(pdata) >= 17:
            # Try offsets 6-16 for DPI values
            for dpi_start in [5, 6, 7]:
                dpis = []
                for d in range(5):
                    off = dpi_start + d * 2
                    if off + 1 < len(pdata):
                        dpi = pdata[off] | (pdata[off+1] << 8)
                        dpis.append(dpi)
                if any(50 <= d <= 20000 for d in dpis):
                    print(f"  DPI values (offset {dpi_start}): {dpis}")

        offset += plen
