"""
HID Dongle Write Test — Write profile data through the dongle to the mouse.

Based on spy findings: SWARM II communicates through the dongle's 0xFF03
interface, report 0x06. The dongle relays commands to the mouse wirelessly.

Command format observed:
  Byte[2] = 0x44 (data loaded state)
  Byte[4] = 0x11 (set profile command)
  Byte[5] = 0x01 (sub-command)
  Byte[6] = 0x01
  Byte[7] = 0x5A
  Bytes[8-11] = color RGBA
  Bytes[12-14] = DPI stages (DPI/50)
  Bytes[15-17] = DPI stages duplicate
"""
import hid
import time
import sys

VENDOR = 0x10F5
DONGLE_PID = 0x5017
MOUSE_PID = 0x5019

def open_dongle():
    """Open the dongle's vendor interface (0xFF03)."""
    for d in hid.enumerate(VENDOR, DONGLE_PID):
        if d["usage_page"] == 0xFF03:
            h = hid.device()
            h.open_path(d["path"])
            return h
    return None

def open_mouse():
    """Open a mouse vendor interface (0xFF01) for reading."""
    for d in hid.enumerate(VENDOR, MOUSE_PID):
        if d["usage_page"] == 0xFF01 and d["interface_number"] == 0:
            h = hid.device()
            h.open_path(d["path"])
            h.set_nonblocking(1)
            return h
    return None

def read_dongle_report(dongle):
    """Read current dongle report 0x06."""
    return dongle.get_feature_report(0x06, 256)

def read_mouse_dpi(mouse):
    """Read mouse report 0x06 which has the DPI stage config."""
    data = mouse.get_feature_report(0x06, 256)
    if data and len(data) > 17:
        # Report 0x06: bytes 1-4 are stage1 [DPI_hi, DPI_lo?, R, G]
        # From spy: 06 14 FF 00 00 32 FF FF 00 50 00 FF 00 64 FF FF FF 14
        # Format seems to be: [RID, stage1_dpi/50, R, G, B, stage2_dpi/50, R, G, B, ...]
        stages = []
        for i in range(5):
            offset = 1 + i * 4
            if offset < len(data):
                dpi_val = data[offset] * 50
                stages.append(dpi_val)
        return stages, data
    return [], data

def read_mouse_report_01(mouse):
    """Read mouse report 0x01 — active profile DPI + color."""
    data = mouse.get_feature_report(0x01, 256)
    return data

def hex_line(data, count=32):
    return " ".join("%02X" % b for b in data[:count])

def main():
    print("=" * 60)
    print("ROCCAT Dongle Write Test")
    print("=" * 60)
    print()

    # Open devices
    dongle = open_dongle()
    if not dongle:
        print("ERROR: Cannot open dongle 0xFF03")
        return
    print("Opened dongle 0xFF03")

    mouse = open_mouse()
    if not mouse:
        print("ERROR: Cannot open mouse 0xFF01")
        dongle.close()
        return
    print("Opened mouse 0xFF01 IF=0")
    print()

    # Read baseline
    print("--- BASELINE ---")
    d_report = read_dongle_report(dongle)
    print("Dongle 0x06: %s" % hex_line(d_report))

    m_report_06 = mouse.get_feature_report(0x06, 256)
    m_report_08 = mouse.get_feature_report(0x08, 256)
    m_report_01 = read_mouse_report_01(mouse)
    print("Mouse  0x01: %s" % hex_line(m_report_01))
    print("Mouse  0x06: %s" % hex_line(m_report_06))
    print("Mouse  0x08: %s" % hex_line(m_report_08))
    print()

    # Decode current DPI from report 0x06
    # Baseline: 06 14 FF 00 00 32 FF FF 00 50 00 FF 00 64 FF FF FF 14
    # This looks like 5 stages: each is [DPI/50, color bytes...]
    # Stage 1: 0x14 = 20*50 = 1000 DPI
    # Stage 2: 0x32 = 50*50 = 2500 DPI
    # Stage 3: 0x50 = 80*50 = 4000 DPI
    # Stage 4: 0x64 = 100*50 = 5000 DPI
    # Stage 5: 0x14 = 20*50 = 1000 DPI
    print("Current DPI stages from mouse report 0x06:")
    for i in range(5):
        off = 1 + i * 4
        if off < len(m_report_06):
            dpi = m_report_06[off] * 50
            print("  Stage %d: %d DPI (0x%02X)" % (i + 1, dpi, m_report_06[off]))
    print()

    # =====================================================
    # TEST 1: Write the observed SWARM II command format
    # to the dongle report 0x06
    # =====================================================
    target_dpi = 450
    target_byte = target_dpi // 50  # 0x09

    print("TARGET: Set DPI to %d (byte value 0x%02X)" % (target_dpi, target_byte))
    print()

    # Build command based on observed SWARM II format
    # Start with a copy of the current dongle report
    cmd = bytearray(256)
    cmd[0] = 0x06  # report ID
    cmd[1] = 0x01  # always 0x01
    cmd[2] = 0x44  # state: data loaded
    cmd[3] = 0x08  # always 0x08
    cmd[4] = 0x11  # command: set profile
    cmd[5] = 0x01  # profile index or sub-command
    cmd[6] = 0x01  # parameter
    cmd[7] = 0x5A  # unknown constant
    # Profile color (RGBA) — white
    cmd[8] = 0xFF
    cmd[9] = 0xFF
    cmd[10] = 0xFF
    cmd[11] = 0xFF
    # DPI stages (DPI/50 encoding) — set all to target
    cmd[12] = target_byte  # stage 1
    cmd[13] = target_byte  # stage 2
    cmd[14] = target_byte  # stage 3
    # Second DPI set
    cmd[15] = target_byte
    cmd[16] = target_byte
    cmd[17] = target_byte

    print("--- TEST 1: Write SWARM-style command to dongle ---")
    print("Sending: %s" % hex_line(cmd))

    try:
        result = dongle.send_feature_report(bytes(cmd))
        print("send_feature_report returned: %s" % result)
    except Exception as e:
        print("send_feature_report ERROR: %s" % e)

    time.sleep(0.5)

    # Read back dongle state
    d_after = read_dongle_report(dongle)
    print("Dongle after: %s" % hex_line(d_after))

    # Read mouse state
    m_after_01 = read_mouse_report_01(mouse)
    m_after_06 = mouse.get_feature_report(0x06, 256)
    print("Mouse  0x01 after: %s" % hex_line(m_after_01))
    print("Mouse  0x06 after: %s" % hex_line(m_after_06))
    print()

    # Check if DPI actually changed
    print("DPI stages after write:")
    changed = False
    for i in range(5):
        off = 1 + i * 4
        if off < len(m_after_06):
            dpi = m_after_06[off] * 50
            marker = " <<<" if m_after_06[off] != m_report_06[off] else ""
            if marker:
                changed = True
            print("  Stage %d: %d DPI (0x%02X)%s" % (i + 1, dpi, m_after_06[off], marker))

    print()
    if changed:
        print("*** DPI CHANGED! The dongle write worked! ***")
    else:
        print("DPI unchanged in report 0x06. Trying alternate approaches...")
        print()

        # =====================================================
        # TEST 2: Try writing directly to mouse report 0x06
        # with the DPI data (in case dongle write didn't relay)
        # =====================================================
        print("--- TEST 2: Write DPI directly to mouse report 0x06 ---")
        m_cmd = bytearray(m_report_06)
        # Change stage 1 DPI
        m_cmd[1] = target_byte  # stage 1
        print("Sending to mouse: %s" % hex_line(m_cmd))
        try:
            result = mouse.send_feature_report(bytes(m_cmd))
            print("Mouse send_feature_report returned: %s" % result)
        except Exception as e:
            print("Mouse send_feature_report ERROR: %s" % e)

        time.sleep(0.5)
        m_after2_06 = mouse.get_feature_report(0x06, 256)
        print("Mouse 0x06 after: %s" % hex_line(m_after2_06))
        if m_after2_06[1] == target_byte:
            print("Report updated! But need to check if mouse behavior changed.")
        print()

        # =====================================================
        # TEST 3: Try the transitioning sequence
        # idle(0x4D) -> transitioning(0x46) -> active(0x44)
        # =====================================================
        print("--- TEST 3: Full state machine sequence ---")

        # Step 1: Set transitioning state
        cmd2 = bytearray(256)
        cmd2[0] = 0x06
        cmd2[1] = 0x01
        cmd2[2] = 0x46  # transitioning
        cmd2[3] = 0x08
        print("Step 1 - Transition: %s" % hex_line(cmd2, 8))
        try:
            dongle.send_feature_report(bytes(cmd2))
        except Exception as e:
            print("  Error: %s" % e)
        time.sleep(0.2)

        # Step 2: Load profile data
        cmd3 = bytearray(256)
        cmd3[0] = 0x06
        cmd3[1] = 0x01
        cmd3[2] = 0x44  # data loaded
        cmd3[3] = 0x08
        cmd3[4] = 0x11
        cmd3[5] = 0x01
        cmd3[6] = 0x01
        cmd3[7] = 0x5A
        cmd3[8] = 0xFF  # color R
        cmd3[9] = 0x00  # color G
        cmd3[10] = 0x00  # color B
        cmd3[11] = 0xFF  # color A
        cmd3[12] = target_byte  # DPI stage 1
        cmd3[13] = target_byte  # DPI stage 2
        cmd3[14] = target_byte  # DPI stage 3
        cmd3[15] = target_byte
        cmd3[16] = target_byte
        cmd3[17] = target_byte
        print("Step 2 - Load data: %s" % hex_line(cmd3, 22))
        try:
            dongle.send_feature_report(bytes(cmd3))
        except Exception as e:
            print("  Error: %s" % e)
        time.sleep(0.5)

        # Step 3: Return to idle
        cmd4 = bytearray(256)
        cmd4[0] = 0x06
        cmd4[1] = 0x01
        cmd4[2] = 0x4D  # idle
        cmd4[3] = 0x08
        print("Step 3 - Back to idle: %s" % hex_line(cmd4, 8))
        try:
            dongle.send_feature_report(bytes(cmd4))
        except Exception as e:
            print("  Error: %s" % e)
        time.sleep(0.5)

        # Read final state
        d_final = read_dongle_report(dongle)
        m_final_01 = read_mouse_report_01(mouse)
        m_final_06 = mouse.get_feature_report(0x06, 256)
        print()
        print("--- FINAL STATE ---")
        print("Dongle: %s" % hex_line(d_final))
        print("Mouse 0x01: %s" % hex_line(m_final_01))
        print("Mouse 0x06: %s" % hex_line(m_final_06))

        print()
        print("DPI stages final:")
        for i in range(5):
            off = 1 + i * 4
            if off < len(m_final_06):
                dpi = m_final_06[off] * 50
                marker = " <<<" if m_final_06[off] != m_report_06[off] else ""
                print("  Stage %d: %d DPI (0x%02X)%s" % (i + 1, dpi, m_final_06[off], marker))

    print()
    print("Move your mouse — does the DPI feel different?")
    print("(450 DPI should feel noticeably slower than normal)")

    dongle.close()
    mouse.close()

if __name__ == "__main__":
    main()
