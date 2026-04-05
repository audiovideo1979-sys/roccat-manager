"""Decode Qt ByteArray fields from two INI snapshots and diff them."""
import re
import sys

def decode_qt_bytearray(data):
    """Decode Qt @ByteArray(...) to raw bytes."""
    result = bytearray()
    i = 0
    while i < len(data):
        if data[i:i+1] == b'\\' and i+1 < len(data):
            c = chr(data[i+1])
            if c == 'x':
                # Hex escape: \xN or \xNN
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
            elif c == '0': result.append(0); i += 2
            elif c == 'n': result.append(0x0a); i += 2
            elif c == 'r': result.append(0x0d); i += 2
            elif c == 't': result.append(0x09); i += 2
            elif c == 'f': result.append(0x0c); i += 2
            elif c == '\\': result.append(0x5c); i += 2
            else: result.append(data[i+1]); i += 2
        else:
            result.append(data[i])
            i += 1
    return bytes(result)

def extract_fields(filepath):
    with open(filepath, 'rb') as f:
        raw = f.read()

    fields = {}
    pattern = rb'([A-Za-z_]+)="?@ByteArray\(([^)]*)\)"?'
    for m in re.finditer(pattern, raw):
        key = m.group(1).decode('ascii', errors='replace')
        ba_data = m.group(2)
        decoded = decode_qt_bytearray(ba_data)
        fields[key] = decoded
    return fields

def diff_bytes(name, before, after):
    """Show byte-level diff between two binary blobs."""
    if before == after:
        return

    print(f"\n{'='*60}")
    print(f"CHANGED: {name} ({len(before)} -> {len(after)} bytes)")
    print(f"{'='*60}")

    min_len = min(len(before), len(after))
    changes = []
    for i in range(min_len):
        if before[i] != after[i]:
            changes.append(i)

    if len(before) != len(after):
        print(f"  Size changed by {len(after) - len(before)} bytes")

    print(f"  {len(changes)} bytes differ")

    # Group consecutive changes
    if not changes:
        return

    groups = []
    start = changes[0]
    end = changes[0]
    for c in changes[1:]:
        if c <= end + 4:  # group if within 4 bytes
            end = c
        else:
            groups.append((start, end))
            start = c
            end = c
    groups.append((start, end))

    for g_start, g_end in groups:
        ctx_start = max(0, g_start - 4)
        ctx_end = min(min_len, g_end + 5)

        print(f"\n  Offset {g_start}-{g_end} (0x{g_start:04x}-0x{g_end:04x}):")

        # Before
        line_b = "  Before: "
        for j in range(ctx_start, ctx_end):
            marker = "*" if j in changes else " "
            line_b += f"{marker}{before[j]:02x}"
        print(line_b)

        # After
        line_a = "  After:  "
        for j in range(ctx_start, min(len(after), ctx_end)):
            marker = "*" if j in changes else " "
            line_a += f"{marker}{after[j]:02x}"
        print(line_a)

if __name__ == "__main__":
    f1 = sys.argv[1] if len(sys.argv) > 1 else "ini_before.bin"
    f2 = sys.argv[2] if len(sys.argv) > 2 else "ini_after.bin"

    before_fields = extract_fields(f1)
    after_fields = extract_fields(f2)

    all_keys = sorted(set(list(before_fields.keys()) + list(after_fields.keys())))

    print("Fields found:")
    for k in all_keys:
        b_len = len(before_fields.get(k, b''))
        a_len = len(after_fields.get(k, b''))
        changed = '  ** CHANGED **' if before_fields.get(k) != after_fields.get(k) else ''
        print(f"  {k}: {b_len} -> {a_len} bytes{changed}")

    # Show diffs for changed fields
    for k in all_keys:
        b = before_fields.get(k, b'')
        a = after_fields.get(k, b'')
        if b != a:
            diff_bytes(k, b, a)
