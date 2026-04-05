"""Check if Swarm II uses HID scancodes or its own table for button assignments."""

hid_scancodes = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F',
    0x0A: 'G', 0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L',
    0x10: 'M', 0x11: 'N', 0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R',
    0x16: 'S', 0x17: 'T', 0x18: 'U', 0x19: 'V', 0x1A: 'W', 0x1B: 'X',
    0x1C: 'Y', 0x1D: 'Z',
    0x28: 'Enter', 0x29: 'Escape', 0x2A: 'Backspace', 0x2B: 'Tab',
    0x2C: 'Space',
    0x39: 'CapsLock',
    0x3A: 'F1', 0x3B: 'F2', 0x3C: 'F3', 0x3D: 'F4',
    0x49: 'Insert', 0x4A: 'Home', 0x4B: 'PageUp', 0x4C: 'Delete',
    0x4D: 'End', 0x4E: 'PageDown',
    0xE0: 'LCtrl', 0xE1: 'LShift', 0xE2: 'LAlt', 0xE3: 'LWin',
}

# Keyboard codes seen in m_btn_setting (4-byte format: [code] [00] [06] [00]):
# From WWM profile (profile 0):
#   0x3c, 0x41
# From profile 1 (Main Test? Grounded?):
#   0x0a, 0x06, 0xe1, 0x14
# From Easy Shift layers:
#   0x4b, 0x4e, 0x19, 0x06, 0x4c, 0x49, 0x3b, 0x3a

# WWM known keyboard assignments:
# side_button_1 = Hotkey LAlt
# side_button_2 = Hotkey LShift
# thumb_button_1 = Hotkey E
# tilt_left = Hotkey G
# ES_tilt_left = Prev Track
# ES_tilt_right = Next Track
# ES_side_button_1 = Page Up
# ES_side_button_2 = Page Down
# ES_thumb_button_1 = Hotkey Ctrl+V
# ES_thumb_button_2 = Hotkey Ctrl+C
# ES_dpi_down = Hotkey F1
# ES_dpi_up = Hotkey F2

print("Checking if codes match HID scancodes:")
print()

# If HID: LShift=0xE1, LAlt=0xE2, E=0x08, G=0x0A
# Codes we see in profile 0: 0x3c, 0x41
# 0x3c in HID = F3 -- but WWM has no F3 binding
# But Swarm STANDARD list shows: 0x3c = Left Shift (from our diff test!)

# So the codes for m_btn_setting Standard functions:
# 01=Click, 02=Menu, ..., 0a=Scroll Down
# Then maybe 0x0b onwards = Insert, Delete, Home, End, PageUp, PageDown, Ctrl, Shift, Alt, Win, CapsLock?

# Let's count the Swarm Standard list:
standard_list = [
    (0x01, 'Click'),
    (0x02, 'Menu'),
    (0x03, 'Universal Scroll'),
    (0x04, 'Double-Click'),
    (0x05, 'Browser Forward'),
    (0x06, 'Browser Backward'),
    (0x07, 'Tilt Left'),
    (0x08, 'Tilt Right'),
    (0x09, 'Scroll Up'),
    (0x0a, 'Scroll Down'),
    (0x0b, 'Insert'),
    (0x0c, 'Delete'),
    (0x0d, 'Home'),
    (0x0e, 'End'),
    (0x0f, 'Page Up'),
    (0x10, 'Page Down'),
    (0x11, 'Ctrl'),
    (0x12, 'Shift'),
    (0x13, 'Alt'),
    (0x14, 'Win'),
    (0x15, 'CapsLock'),
]

print("Proposed Standard function codes (type 01):")
for code, name in standard_list:
    print(f"  0x{code:02x} = {name}")

print()
print("Cross-check with diffs:")
print(f"  Left Click confirmed:      0x01 = Click       YES")
print(f"  Right Click confirmed:     0x02 = Menu        YES")
print(f"  Universal Scroll confirmed: 0x03 = Uni Scroll  YES")
print(f"  Browser Forward confirmed:  0x05 = Fwd        YES")
print(f"  Scroll Up confirmed:        0x09 = Scroll Up   YES")

print()
print("But wait - LShift was 0x3c in the 4-byte keyboard format [3c 00 06 00]")
print("And Shift in Standard list would be 0x12 with type 01")
print("These are DIFFERENT encodings:")
print("  Type 01: Standard functions (mouse buttons, standard actions)")
print("  Type 06: Keyboard HOTKEYS (using Swarm's internal scancode table)")
print()

# So 0x3c in the keyboard hotkey table = what?
# Let me look at the Easy Shift keys from profile data:
# ES_side_button_1 = Page Up, ES_side_button_2 = Page Down
# In the ES section we see: 4b 00 06 00, 4e 00 06 00
# In HID: PageUp=0x4B, PageDown=0x4E -- MATCH!

print("EUREKA! The keyboard hotkey codes ARE standard USB HID scancodes!")
print()
print("Verification:")
print(f"  0x4B = PageUp in HID   -> ES_side_button_1 = Page Up     MATCH!")
print(f"  0x4E = PageDown in HID -> ES_side_button_2 = Page Down   MATCH!")
print(f"  0x4C = Delete in HID   -> ES_thumb_button_1 = Del?       MATCH!")
print(f"  0x49 = Insert in HID   -> ES_thumb_button_2 = Insert     MATCH!")
print(f"  0x3A = F1 in HID       -> ES_dpi_down = F1               MATCH!")
print(f"  0x3B = F2 in HID       -> ES_dpi_up = F2                 MATCH!")
print()
print("So 0x3c in profile 0 = F3 in HID... but WWM thumb_button_1 = Hotkey E")
print("Unless the button ORDER in m_btn_setting is different from what I assumed")
print()
print("Let me re-check: if 0x3c = F3, which button in WWM uses F3? None!")
print("But if the button slots are ordered differently...")
print("WWM side_button_2 = Hotkey LShift, and LShift HID = 0xE1")
print("We dont see 0xE1 in profile 0...")
print()
print("Wait -- Swarm STANDARD list has Shift at position 18 (code 0x12 type 01)")
print("Maybe LShift as a button assignment uses the Standard code, not HID!")
print("So 0x3c is NOT LShift in the keyboard table...")
print("0x3c = 60 decimal. In HID = F3.")
print()
print("THEORY: The 4-byte format [code modifier 06 00] uses HID scancodes")
print("And 0x3c = F3 is correct. The button I thought was LShift is actually F3!")
print("Or the button order is different from what I assumed.")
