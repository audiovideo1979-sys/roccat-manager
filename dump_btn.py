"""Dump m_btn_setting from INI snapshots for comparison."""
import re
import sys

def decode_qt_bytearray(data):
    result = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x5c and i+1 < len(data):  # backslash
            c = data[i+1]
            if c == ord('x'):
                i += 2
                hex_str = ''
                while i < len(data) and len(hex_str) < 2:
                    ch = chr(data[i])
                    if ch in '0123456789abcdefABCDEF':
                        hex_str += ch
                        i += 1
                    else:
                        break
                if hex_str:
                    result.append(int(hex_str, 16))
            elif c == ord('0'): result.append(0); i += 2
            elif c == ord('n'): result.append(0x0a); i += 2
            elif c == ord('r'): result.append(0x0d); i += 2
            elif c == ord('t'): result.append(0x09); i += 2
            elif c == ord('f'): result.append(0x0c); i += 2
            elif c == 0x5c: result.append(0x5c); i += 2
            else: result.append(data[i+1]); i += 2
        else:
            result.append(b)
            i += 1
    return bytes(result)

def extract_field(filepath, field_name):
    with open(filepath, 'rb') as f:
        raw = f.read()
    pattern = field_name.encode() + rb'="?@ByteArray\(([^)]*)\)"?'
    m = re.search(pattern, raw)
    if m:
        return decode_qt_bytearray(m.group(1))
    return None

files = sys.argv[1:] if len(sys.argv) > 1 else ['ini_before.bin', 'ini_after_leftclick.bin', 'ini_after_rightclick.bin']

for fname in files:
    data = extract_field(fname, 'm_btn_setting')
    if data:
        print(f'=== {fname} ({len(data)} bytes) ===')
        for row in range(0, len(data), 16):
            hex_part = ' '.join(f'{data[row+i]:02x}' for i in range(min(16, len(data)-row)))
            print(f'  {row:4d} | {hex_part}')
        print()
    else:
        print(f'{fname}: field not found')
