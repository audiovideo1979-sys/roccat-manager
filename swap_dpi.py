"""Simple DPI swap in the INI file using direct byte replacement."""
import shutil
import sys
import os

ini_path = r"C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_TB.ini"

target_dpi = 450
if len(sys.argv) > 1:
    target_dpi = int(sys.argv[1])

# Read raw file
with open(ini_path, 'rb') as f:
    raw = f.read()

# Current DPI is 1000 = 0x03E8
# In Qt ByteArray: \xe8\x3
# As raw bytes in the file: backslash x e 8 backslash x 3
old_lo = 0xE8
old_hi = 0x03

new_lo = target_dpi & 0xFF
new_hi = (target_dpi >> 8) & 0xFF

# Build the search/replace byte patterns as they appear in the file
def qt_encode_byte(b):
    """Encode a single byte as Qt ByteArray escape."""
    if b == 0:
        return b"\\0"
    elif b == 0x0a:
        return b"\\n"
    elif b == 0x0c:
        return b"\\f"
    elif b == 0x09:
        return b"\\t"
    elif b == 0x0d:
        return b"\\r"
    elif b == ord('\\'):
        return b"\\\\"
    elif 32 <= b < 127 and b not in (ord('('), ord(')')):
        return bytes([b])
    else:
        return ("\\x%x" % b).encode()

old_pattern = qt_encode_byte(old_lo) + qt_encode_byte(old_hi)
new_pattern = qt_encode_byte(new_lo) + qt_encode_byte(new_hi)

print(f"Replacing DPI 1000 -> {target_dpi}")
print(f"  Old pattern: {old_pattern}")
print(f"  New pattern: {new_pattern}")

count = raw.count(old_pattern)
print(f"  Found {count} occurrences in file")

if count == 0:
    print("No matches found! Let me search for the current DPI value...")
    # Try to find what DPI values are in the file
    # Search for common DPI patterns
    for test_dpi in [400, 450, 800, 900, 1000, 1050, 1200, 1600, 2500, 3200]:
        lo = test_dpi & 0xFF
        hi = (test_dpi >> 8) & 0xFF
        pat = qt_encode_byte(lo) + qt_encode_byte(hi)
        c = raw.count(pat)
        if c > 0:
            print(f"  DPI {test_dpi} ({pat}): {c} occurrences")
    sys.exit(1)

# Backup
bak = ini_path + ".bak3"
shutil.copy2(ini_path, bak)

# Replace
new_raw = raw.replace(old_pattern, new_pattern)
with open(ini_path, 'wb') as f:
    f.write(new_raw)

print(f"\nDone! Replaced {count} occurrences.")
print("Now restart Swarm II to apply.")
