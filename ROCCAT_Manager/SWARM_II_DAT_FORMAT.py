#!/usr/bin/env python3
"""
ROCCAT SWARM II Profile Export Format (.dat) - Complete Specification & Writer
=============================================================================
Reverse-engineered from Kone XP Air mouse profile exports.

FILE STRUCTURE OVERVIEW
-----------------------
A .dat file consists of:
  1. A 16-byte file header
  2. A sequence of named blocks (TLV-like)

The file uses BIG-ENDIAN for all multi-byte integers EXCEPT DPI values (which are LE16).
Strings are encoded in UTF-16BE.

FILE HEADER (16 bytes)
----------------------
  Offset  Size  Description
  0       4     Magic: always 0x0000005A (BE32)
  4       4     Version1: always 0x00010000 (BE32)
  8       4     Version2: always 0x00010000 (BE32)
  12      2     Block count (BE16) - number of top-level blocks
  14      2     Padding: always 0x0000

BLOCK STRUCTURE
---------------
Each block consists of:
  [name_len: BE16] [name: UTF-16BE, name_len bytes] [null_term: 00 00] [content]

The name_len field gives the byte length of the name string (NOT including the null
terminator). The null terminator is always 2 bytes (00 00).

CONTENT FORMATS
---------------
There are three content format types:

Type 0x0001 (Simple Value) - used by DesktopProfile, AutoSwitch:
  [00 01] [value: BE32]
  Total: 6 bytes, fixed size.

Type 0x000C / 0x000A (Data Block) - used by KoneXPAirButtons, KoneXPAirMain,
  KoneXPAirMacros, QuickLaunch, TalkKeyInfor, ProfileImage, ProfileName:
  [00 TYPE] [00 00 00] [data_len: BE16] [data: data_len bytes] [trailing: 00 00]
  Where TYPE is 0x0C or 0x0A.
  Total: 7 + data_len + 2 = data_len + 9 bytes.
  EXCEPTION: The very LAST block in the file omits the trailing 00 00,
  so its total is data_len + 7 bytes.

Type ProfileColor (Fixed Format):
  [10 03 00 01 FF FF] [R R] [G G] [B B] [00 00 00 00]
  Total: 16 bytes, fixed size.
  Color components are each DOUBLED (e.g., R=0xC5 is stored as C5 C5).

KNOWN BLOCKS
------------
Block Name          Content Type  Description
-----------         ------------  -----------
AutoSwitch          0x0001        Auto-switch enabled flag (value=0x00010000 when enabled)
AutoSwitchApp       0x000C        App paths for auto-switch (variable size)
DesktopProfile      0x0001        Desktop profile flag (value always 0x00000000)
KoneXPAirButtons    0x000C        Button assignments (data_len always 129)
KoneXPAirMacros     0x000C        Macro data (data_len always 31414, mostly zeros)
KoneXPAirMain       0x000C        DPI, polling rate, LED settings (data_len always 82)
ProfileColor        Fixed         Profile tab color in SWARM UI
ProfileImage        0x000A        Icon path string (UTF-16BE)
ProfileName         0x000A        Profile name string (UTF-16BE)
QuickLaunch         0x000C        Quick launch settings (data_len=4, all zeros)
TalkKeyInfor        0x000C        Talk/AIMO key info (data_len=4, all zeros)

BLOCK ORDER
-----------
Minimal file (6 blocks, ~651 bytes - importable by SWARM II):
  DesktopProfile, KoneXPAirButtons, KoneXPAirMain, ProfileColor,
  ProfileImage, ProfileName

Full file (10-11 blocks, ~32KB):
  AutoSwitch, [AutoSwitchApp], DesktopProfile, KoneXPAirButtons,
  KoneXPAirMacros, KoneXPAirMain, ProfileColor, ProfileImage,
  ProfileName, QuickLaunch, TalkKeyInfor

KoneXPAirButtons DATA (129 bytes)
---------------------------------
  Offset  Size  Description
  0-2     3     Padding: 00 00 00
  3-5     3     Identifier: 7D 07 7D (constant)
  6       1     Profile flags (0x00 = default, 0x01 = modified)
  7-126   120   30 button entries, 4 bytes each (15 normal + 15 Easy-Shift)
  127-128 2     Checksum/hash bytes (varies per profile)

  Button Entry Format (4 bytes each):
    For non-keyboard actions:  [00] [00] [action_id] [action_type]
    For keyboard mappings:     [00] [HID_keycode] [modifiers] [06]

  Action Types:
    0x01 = Mouse button (action_id: 1=LClick, 2=RClick, 3=MClick, 5=Forward,
                          6=Back, 7=DPI+, 8=DPI-, 9=ScrollUp, 10=ScrollDown)
    0x02 = Scroll action (action_id: 2=TiltLeft, 3=TiltRight)
    0x03 = Special function (action_id: 2=Volume+, 3=Volume-, 4=EasyShift,
                              7=DPICycleUp, 8=DPICycleDown)
    0x04 = Easy-Aim (action_id: typically 0)
    0x06 = Keyboard key (HID keycode + modifier bitmask)
    0x08 = DPI action (action_id: 1=DPICycle, 11=EasyShiftDPI)
    0x0A = Profile switch (action_id: 1=CycleProfiles)
    0x00 = Disabled (all bytes zero)

  Keyboard Modifier Bitmask (for action_type 0x06):
    0x01 = Ctrl
    0x02 = Shift
    0x04 = Alt
    0x08 = GUI/Win

  Button Slot Mapping (30 entries):
    Slot  0 = Left Click (normal)
    Slot  1 = Right Click (normal)
    Slot  2 = Middle Click / Scroll Wheel (normal)
    Slot  3 = Scroll Up (normal)
    Slot  4 = Scroll Down (normal)
    Slot  5 = Forward / Thumb Front (normal)
    Slot  6 = Back / Thumb Rear (normal)
    Slot  7 = Scroll Tilt Left (normal)
    Slot  8 = Scroll Tilt Right (normal)
    Slot  9 = Top Button Front (normal)
    Slot 10 = Top Button Rear (normal)
    Slot 11 = DPI Up (normal)
    Slot 12 = DPI Down (normal)
    Slot 13 = Profile Button (normal)
    Slot 14 = Easy-Shift Button (normal)
    Slots 15-29 = Easy-Shift versions of slots 0-14

KoneXPAirMain DATA (82 bytes)
------------------------------
  Offset  Size  Description
  0-2     3     Padding: 00 00 00
  3-5     3     Identifier: 4E 06 4E (constant)
  6       1     Profile modification flag (0=default, 1=modified)
  7       1     Wired polling rate (0x00=default/125Hz?, 0x06=1000Hz)
  8       1     Wireless polling rate (0x00=default/125Hz?, 0x06=1000Hz)
  9       1     DPI configuration flags (0x1F=default 5-stage, 0x02=customized)
  10      1     Active DPI stage index (1-based, typically 0x01)
  11-20   10    5 DPI stage values (LE16 each, in units of DPI)
                 Default: 400, 800, 1200, 1600, 3200
  21-30   10    5 backup/original DPI values (LE16 each)
                 All zeros in default profile; copy of defaults in customized profiles
  31      1     Padding: 0x00
  32      1     Padding: 0x00
  33      1     Constant: 0x03
  34      1     LED effect mode:
                 0x09 = AIMO intelligent lighting
                 0x0A = Custom/static lighting
  35      1     LED sub-parameter (0x06 for AIMO, 0x01 for custom)
  36      1     LED parameter (0xFF for AIMO defaults, 0x00 for custom)
  37      1     Number of DPI stages: 0x05
  38-39   2     Padding: 00 00
  40-74   35    7 LED zone entries (5 bytes each):
                 [zone_effect] [brightness/alpha] [R] [G] [B]
                 In AIMO mode: zone_effect = zone index (0-6), colors ignored
                 In custom mode: zone_effect = effect type:
                   0x01=static, 0x14=breathing/wave
  75-79   5     Profile summary color:
                 [mode] [brightness] [R] [G] [B]
                 brightness: 0xFF=full, 0x64=100 (customized profiles)
  80-81   2     Trailing bytes (checksum/hash, varies per profile)

ProfileColor DATA (16 bytes, fixed)
------------------------------------
  Offset  Size  Description
  0-1     2     Header: 10 03
  2-3     2     Flags: 00 01
  4-5     2     Alpha: FF FF
  6-7     2     Red (doubled, e.g., C5 C5 for R=0xC5)
  8-9     2     Green (doubled)
  10-11   2     Blue (doubled)
  12-15   4     Padding: 00 00 00 00

AutoSwitchApp DATA FORMAT
--------------------------
  [num_apps: BE32]
  For each app:
    [path_byte_len: BE32] [path: UTF-16BE, path_byte_len bytes]
  No null terminators between entries.

ProfileImage DATA
-----------------
  UTF-16BE string containing the icon resource path.
  Default: ":/icons/resource/graphic/icons/Basics/profile_icons/profile_default_icon.png"

ProfileName DATA
----------------
  UTF-16BE string containing the profile name.
"""

import struct
from typing import Optional


def _encode_utf16be(text: str) -> bytes:
    """Encode a string as UTF-16BE (no BOM, no null terminator)."""
    return text.encode('utf-16-be')


def _write_block_name(name: str) -> bytes:
    """Write a block name header: [name_len: BE16] [name: UTF-16BE] [null: 00 00]"""
    encoded = _encode_utf16be(name)
    return struct.pack(">H", len(encoded)) + encoded + b'\x00\x00'


def _write_simple_content(value: int) -> bytes:
    """Write type 0x0001 content: [00 01] [value: BE32]"""
    return b'\x00\x01' + struct.pack(">I", value)


def _write_data_content(type_byte: int, data: bytes, is_last_block: bool = False) -> bytes:
    """Write type 0x000C or 0x000A content.

    Format: [00 TYPE] [00 00 00] [data_len: BE16] [data] [trailing 00 00]
    The trailing 00 00 is omitted for the last block in the file.
    """
    header = bytes([0x00, type_byte, 0x00, 0x00, 0x00])
    data_len = struct.pack(">H", len(data))
    result = header + data_len + data
    if not is_last_block:
        result += b'\x00\x00'
    return result


def _write_profile_color(r: int, g: int, b: int) -> bytes:
    """Write ProfileColor content (16 bytes fixed format).

    Colors are doubled: e.g., R=0xC5 -> C5 C5.
    """
    return bytes([
        0x10, 0x03, 0x00, 0x01, 0xFF, 0xFF,
        r, r, g, g, b, b,
        0x00, 0x00, 0x00, 0x00
    ])


def make_button_data(
    button_assignments: Optional[list] = None,
    profile_flags: int = 0x00,
    checksum: bytes = b'\x00\x00'
) -> bytes:
    """Build 129-byte KoneXPAirButtons data block.

    button_assignments: list of 30 tuples (b0, b1, b2, b3) for each button slot.
                        If None, uses default assignments.
    profile_flags: 0x00 for default, 0x01 for modified.
    checksum: 2 trailing bytes.
    """
    if button_assignments is None:
        # Default button assignments for Kone XP Air
        button_assignments = [
            (0x00, 0x00, 0x01, 0x01),  # Slot 0:  Left Click -> Left Click
            (0x00, 0x00, 0x02, 0x01),  # Slot 1:  Right Click -> Right Click
            (0x00, 0x00, 0x03, 0x01),  # Slot 2:  Middle Click -> Middle Click
            (0x00, 0x00, 0x09, 0x01),  # Slot 3:  Scroll Up -> Scroll Up
            (0x00, 0x00, 0x0A, 0x01),  # Slot 4:  Scroll Down -> Scroll Down
            (0x00, 0x00, 0x05, 0x01),  # Slot 5:  Forward -> Forward
            (0x00, 0x00, 0x06, 0x01),  # Slot 6:  Back -> Back
            (0x00, 0x00, 0x02, 0x02),  # Slot 7:  Tilt Left -> Scroll Tilt Left
            (0x00, 0x00, 0x03, 0x02),  # Slot 8:  Tilt Right -> Scroll Tilt Right
            (0x00, 0x14, 0x00, 0x06),  # Slot 9:  Top Front -> Keyboard 'q' (HID 0x14)
            (0x00, 0x08, 0x00, 0x06),  # Slot 10: Top Rear -> Keyboard 'e' (HID 0x08)
            (0x00, 0x00, 0x07, 0x01),  # Slot 11: DPI Up -> DPI Up
            (0x00, 0x00, 0x08, 0x01),  # Slot 12: DPI Down -> DPI Down
            (0x00, 0x00, 0x01, 0x0A),  # Slot 13: Profile -> Profile Cycle
            (0x00, 0x00, 0x01, 0x08),  # Slot 14: Easy-Shift -> DPI Cycle
            # Easy-Shift versions (slots 15-29)
            (0x00, 0x00, 0x01, 0x01),  # ES Slot 0: Left Click
            (0x00, 0x00, 0x02, 0x01),  # ES Slot 1: Right Click
            (0x00, 0x00, 0x04, 0x03),  # ES Slot 2: Easy-Shift function
            (0x00, 0x00, 0x07, 0x03),  # ES Slot 3: DPI Cycle Up
            (0x00, 0x00, 0x08, 0x03),  # ES Slot 4: DPI Cycle Down
            (0x00, 0x4B, 0x00, 0x06),  # ES Slot 5: Keyboard 'Page Up' (HID 0x4B)
            (0x00, 0x4E, 0x00, 0x06),  # ES Slot 6: Keyboard 'Page Down' (HID 0x4E)
            (0x00, 0x19, 0x01, 0x06),  # ES Slot 7: Keyboard Ctrl+V (HID 0x19, mod 0x01)
            (0x00, 0x06, 0x01, 0x06),  # ES Slot 8: Keyboard Ctrl+C (HID 0x06, mod 0x01)
            (0x00, 0x4C, 0x00, 0x06),  # ES Slot 9: Keyboard 'Delete' (HID 0x4C)
            (0x00, 0x49, 0x00, 0x06),  # ES Slot 10: Keyboard 'Insert' (HID 0x49)
            (0x00, 0x00, 0x02, 0x03),  # ES Slot 11: Volume Up
            (0x00, 0x00, 0x03, 0x03),  # ES Slot 12: Volume Down
            (0x00, 0x00, 0x00, 0x00),  # ES Slot 13: Disabled
            (0x00, 0x00, 0x0B, 0x08),  # ES Slot 14: ES DPI action
        ]

    assert len(button_assignments) == 30, "Must provide exactly 30 button entries"

    data = b'\x00\x00\x00'  # Padding
    data += b'\x7D\x07\x7D'  # Identifier
    data += bytes([profile_flags])  # Profile flags

    for entry in button_assignments:
        data += bytes(entry)

    data += checksum
    assert len(data) == 129, f"Button data must be 129 bytes, got {len(data)}"
    return data


def make_main_data(
    dpi_stages: Optional[list] = None,
    backup_dpi: Optional[list] = None,
    active_dpi_stage: int = 1,
    polling_rate_wired: int = 0x00,
    polling_rate_wireless: int = 0x00,
    dpi_flags: int = 0x1F,
    profile_flag: int = 0x00,
    led_effect: int = 0x09,
    led_sub: int = 0x06,
    led_param: int = 0xFF,
    led_zones: Optional[list] = None,
    profile_color_rgb: tuple = (0xC5, 0x0B, 0xDC),
    profile_color_brightness: int = 0xFF,
    trailing: bytes = b'\x00\x00'
) -> bytes:
    """Build 82-byte KoneXPAirMain data block.

    dpi_stages: list of 5 DPI values (int, e.g., [400, 800, 1200, 1600, 3200])
    backup_dpi: list of 5 backup DPI values (None = all zeros for default)
    led_zones: list of 7 tuples (effect_mode, brightness, R, G, B) for LED zones
    """
    if dpi_stages is None:
        dpi_stages = [400, 800, 1200, 1600, 3200]
    if backup_dpi is None:
        backup_dpi = [0, 0, 0, 0, 0]
    if led_zones is None:
        # Default AIMO lighting (all white, each zone has sequential index as effect byte)
        led_zones = [(i, 0xFF, 0xFF, 0xFF, 0xFF) for i in range(7)]

    assert len(dpi_stages) == 5
    assert len(backup_dpi) == 5
    assert len(led_zones) == 7

    data = b'\x00\x00\x00'  # Padding
    data += b'\x4E\x06\x4E'  # Identifier
    data += bytes([profile_flag])
    data += bytes([polling_rate_wired, polling_rate_wireless])
    data += bytes([dpi_flags])
    data += bytes([active_dpi_stage])

    # DPI stages (LE16)
    for dpi in dpi_stages:
        data += struct.pack("<H", dpi)

    # Backup DPI stages (LE16)
    for dpi in backup_dpi:
        data += struct.pack("<H", dpi)

    data += b'\x00\x00'  # Padding
    data += bytes([0x03])  # Constant
    data += bytes([led_effect])  # LED effect mode
    data += bytes([led_sub])  # LED sub-parameter
    data += bytes([led_param])  # LED parameter
    data += bytes([0x05])  # Number of DPI stages
    data += b'\x00\x00'  # Padding

    # 7 LED zone entries
    for mode, brightness, r, g, b in led_zones:
        data += bytes([mode, brightness, r, g, b])

    # Profile summary color
    data += bytes([0x01, profile_color_brightness])
    data += bytes(profile_color_rgb)

    data += trailing

    assert len(data) == 82, f"Main data must be 82 bytes, got {len(data)}"
    return data


def make_profile_image_data(
    path: str = ":/icons/resource/graphic/icons/Basics/profile_icons/profile_default_icon.png"
) -> bytes:
    """Build ProfileImage data (UTF-16BE encoded path)."""
    return _encode_utf16be(path)


def make_profile_name_data(name: str) -> bytes:
    """Build ProfileName data (UTF-16BE encoded name)."""
    return _encode_utf16be(name)


def make_macros_data() -> bytes:
    """Build empty KoneXPAirMacros data (31414 bytes, mostly zeros).

    The macro block has a small header followed by a large zero-filled buffer.
    """
    # Header from observed data
    header = bytes.fromhex("0000001e00000413081304000100000000000000000000000000000000000000")
    padding = b'\x00' * (31414 - len(header))
    return header + padding


def make_quicklaunch_data() -> bytes:
    """Build empty QuickLaunch data (4 bytes)."""
    return b'\x00\x00\x00\x00'


def make_talkkey_data() -> bytes:
    """Build empty TalkKeyInfor data (4 bytes)."""
    return b'\x00\x00\x00\x00'


def write_minimal_dat(
    profile_name: str = "DEFAULT PROFILE 01",
    profile_color_rgb: tuple = (0xC5, 0x0B, 0xDC),
    dpi_stages: Optional[list] = None,
    button_assignments: Optional[list] = None,
    output_path: str = "output.dat"
) -> bytes:
    """Write a minimal 6-block .dat file that SWARM II can import.

    This produces a file similar to KONE_XP_AIR.dat (~651 bytes).
    Blocks: DesktopProfile, KoneXPAirButtons, KoneXPAirMain, ProfileColor,
            ProfileImage, ProfileName
    """
    blocks = []

    # Block 1: DesktopProfile (simple value = 0)
    blocks.append(("DesktopProfile", _write_simple_content(0x00000000)))

    # Block 2: KoneXPAirButtons
    btn_data = make_button_data(button_assignments=button_assignments)
    blocks.append(("KoneXPAirButtons", _write_data_content(0x0C, btn_data, is_last_block=False)))

    # Block 3: KoneXPAirMain
    main_data = make_main_data(dpi_stages=dpi_stages, profile_color_rgb=profile_color_rgb)
    blocks.append(("KoneXPAirMain", _write_data_content(0x0C, main_data, is_last_block=False)))

    # Block 4: ProfileColor
    r, g, b = profile_color_rgb
    blocks.append(("ProfileColor", _write_profile_color(r, g, b)))

    # Block 5: ProfileImage
    img_data = make_profile_image_data()
    blocks.append(("ProfileImage", _write_data_content(0x0A, img_data, is_last_block=False)))

    # Block 6: ProfileName (LAST BLOCK - no trailing 00 00)
    name_data = make_profile_name_data(profile_name)
    blocks.append(("ProfileName", _write_data_content(0x0A, name_data, is_last_block=True)))

    # Build the file
    num_blocks = len(blocks)
    file_header = struct.pack(">I", 0x0000005A)  # Magic
    file_header += struct.pack(">I", 0x00010000)  # Version1
    file_header += struct.pack(">I", 0x00010000)  # Version2
    file_header += struct.pack(">H", num_blocks)  # Block count
    file_header += b'\x00\x00'  # Padding

    file_data = file_header
    for name, content in blocks:
        file_data += _write_block_name(name)
        file_data += content

    if output_path:
        with open(output_path, "wb") as f:
            f.write(file_data)

    return file_data


def write_full_dat(
    profile_name: str = "My Profile",
    profile_color_rgb: tuple = (0xC5, 0x0B, 0xDC),
    dpi_stages: Optional[list] = None,
    button_assignments: Optional[list] = None,
    auto_switch_apps: Optional[list] = None,
    output_path: str = "output.dat"
) -> bytes:
    """Write a full .dat file with all standard blocks (~32KB).

    Blocks: AutoSwitch, [AutoSwitchApp], DesktopProfile, KoneXPAirButtons,
            KoneXPAirMacros, KoneXPAirMain, ProfileColor, ProfileImage,
            ProfileName, QuickLaunch, TalkKeyInfor
    """
    blocks = []
    has_app_switch = auto_switch_apps is not None and len(auto_switch_apps) > 0

    # Block: AutoSwitch
    # Value 0x00010000 = enabled
    blocks.append(("AutoSwitch", _write_simple_content(0x00010000)))

    # Block: AutoSwitchApp (optional)
    if has_app_switch:
        app_data = struct.pack(">I", len(auto_switch_apps))
        for app_path in auto_switch_apps:
            path_bytes = _encode_utf16be(app_path)
            app_data += struct.pack(">I", len(path_bytes))
            app_data += path_bytes
        blocks.append(("AutoSwitchApp", _write_data_content(0x0C, app_data, is_last_block=False)))

    # Block: DesktopProfile
    blocks.append(("DesktopProfile", _write_simple_content(0x00000000)))

    # Block: KoneXPAirButtons
    btn_data = make_button_data(button_assignments=button_assignments)
    blocks.append(("KoneXPAirButtons", _write_data_content(0x0C, btn_data, is_last_block=False)))

    # Block: KoneXPAirMacros
    macro_data = make_macros_data()
    blocks.append(("KoneXPAirMacros", _write_data_content(0x0C, macro_data, is_last_block=False)))

    # Block: KoneXPAirMain
    main_data = make_main_data(
        dpi_stages=dpi_stages,
        backup_dpi=[400, 800, 1200, 1600, 3200],  # Always include defaults as backup
        profile_color_rgb=profile_color_rgb,
        polling_rate_wired=0x06,
        polling_rate_wireless=0x06,
        dpi_flags=0x02,
        profile_flag=0x00,
        profile_color_brightness=0x64,
    )
    blocks.append(("KoneXPAirMain", _write_data_content(0x0C, main_data, is_last_block=False)))

    # Block: ProfileColor
    r, g, b = profile_color_rgb
    blocks.append(("ProfileColor", _write_profile_color(r, g, b)))

    # Block: ProfileImage
    img_data = make_profile_image_data()
    blocks.append(("ProfileImage", _write_data_content(0x0A, img_data, is_last_block=False)))

    # Block: ProfileName
    name_data = make_profile_name_data(profile_name)
    blocks.append(("ProfileName", _write_data_content(0x0A, name_data, is_last_block=False)))

    # Block: QuickLaunch
    ql_data = make_quicklaunch_data()
    blocks.append(("QuickLaunch", _write_data_content(0x0C, ql_data, is_last_block=False)))

    # Block: TalkKeyInfor (LAST BLOCK)
    tk_data = make_talkkey_data()
    blocks.append(("TalkKeyInfor", _write_data_content(0x0C, tk_data, is_last_block=True)))

    # Build the file
    num_blocks = len(blocks)
    file_header = struct.pack(">I", 0x0000005A)
    file_header += struct.pack(">I", 0x00010000)
    file_header += struct.pack(">I", 0x00010000)
    file_header += struct.pack(">H", num_blocks)
    file_header += b'\x00\x00'

    file_data = file_header
    for name, content in blocks:
        file_data += _write_block_name(name)
        file_data += content

    if output_path:
        with open(output_path, "wb") as f:
            f.write(file_data)

    return file_data


# ============================================================================
# HELPER: Button assignment builder
# ============================================================================

def mouse_button(button_id: int) -> tuple:
    """Create a mouse button action entry. IDs: 1=Left, 2=Right, 3=Middle, 5=Fwd, 6=Back, etc."""
    return (0x00, 0x00, button_id, 0x01)

def scroll_action(scroll_id: int) -> tuple:
    """Create a scroll action entry. IDs: 2=TiltLeft, 3=TiltRight."""
    return (0x00, 0x00, scroll_id, 0x02)

def keyboard_key(hid_keycode: int, modifiers: int = 0x00) -> tuple:
    """Create a keyboard key entry. Uses HID usage codes.

    Common HID keycodes:
      0x04='a', 0x05='b', ..., 0x1D='z'
      0x1E='1', ..., 0x27='0'
      0x28=Enter, 0x29=Escape, 0x2A=Backspace, 0x2B=Tab, 0x2C=Space
      0x3A=F1, ..., 0x45=F12
      0x49=Insert, 0x4A=Home, 0x4B=PageUp, 0x4C=Delete, 0x4D=End, 0x4E=PageDown
    Modifiers: 0x01=Ctrl, 0x02=Shift, 0x04=Alt, 0x08=GUI
    """
    return (0x00, hid_keycode, modifiers, 0x06)

def special_function(func_id: int) -> tuple:
    """Create a special function entry. IDs: 2=Vol+, 3=Vol-, 4=EasyShift, 7=DPIUp, 8=DPIDown."""
    return (0x00, 0x00, func_id, 0x03)

def dpi_action(action_id: int = 1) -> tuple:
    """Create a DPI action entry. 1=Cycle, 11=EasyShiftDPI."""
    return (0x00, 0x00, action_id, 0x08)

def profile_switch(switch_id: int = 1) -> tuple:
    """Create a profile switch entry. 1=CycleProfiles."""
    return (0x00, 0x00, switch_id, 0x0A)

def disabled() -> tuple:
    """Create a disabled button entry."""
    return (0x00, 0x00, 0x00, 0x00)


# ============================================================================
# PARSER: Read and dump .dat files
# ============================================================================

KNOWN_BLOCK_NAMES = {
    "AutoSwitch", "AutoSwitchApp", "DesktopProfile", "KoneXPAirButtons",
    "KoneXPAirMacros", "KoneXPAirMain", "ProfileColor", "ProfileImage",
    "ProfileName", "QuickLaunch", "TalkKeyInfor"
}


def parse_dat(filepath: str) -> dict:
    """Parse a SWARM II .dat file and return its structure."""
    with open(filepath, "rb") as f:
        data = f.read()

    result = {
        "file_size": len(data),
        "magic": struct.unpack_from(">I", data, 0)[0],
        "version1": struct.unpack_from(">I", data, 4)[0],
        "version2": struct.unpack_from(">I", data, 8)[0],
        "block_count": struct.unpack_from(">H", data, 12)[0],
        "blocks": []
    }

    # Find all blocks
    found = []
    pos = 16
    while pos < len(data) - 10:
        nl = struct.unpack_from(">H", data, pos)[0]
        if 8 <= nl <= 100 and nl % 2 == 0:
            name_end = pos + 2 + nl
            if name_end + 2 <= len(data):
                if data[name_end] == 0 and data[name_end + 1] == 0:
                    try:
                        name = data[pos + 2:name_end].decode('utf-16-be')
                        if name in KNOWN_BLOCK_NAMES:
                            found.append((pos, name, nl))
                    except:
                        pass
        pos += 1

    for i, (offset, name, nl) in enumerate(found):
        cs = offset + 2 + nl + 2
        ce = found[i + 1][0] if i + 1 < len(found) else len(data)
        content = data[cs:ce]

        block_info = {
            "name": name,
            "offset": offset,
            "content_offset": cs,
            "content_len": len(content),
            "content_raw": content,
        }

        # Decode based on block type
        if name == "ProfileName" and len(content) >= 7:
            dl = struct.unpack_from(">H", content, 5)[0]
            block_info["profile_name"] = content[7:7 + dl].decode('utf-16-be', errors='replace')

        elif name == "ProfileImage" and len(content) >= 7:
            dl = struct.unpack_from(">H", content, 5)[0]
            block_info["image_path"] = content[7:7 + dl].decode('utf-16-be', errors='replace')

        elif name == "ProfileColor" and len(content) >= 12:
            block_info["color_rgb"] = (content[6], content[8], content[10])

        elif name == "KoneXPAirMain" and len(content) >= 21:
            md = content[7:]  # skip type header
            dpis = [struct.unpack_from("<H", md, 11 + i * 2)[0] for i in range(5)]
            block_info["dpi_stages"] = dpis
            block_info["polling_wired"] = md[7]
            block_info["polling_wireless"] = md[8]

        elif name == "KoneXPAirButtons" and len(content) >= 7:
            md = content[7:]  # skip type header
            entries = []
            for j in range(30):
                off = 7 + j * 4
                if off + 4 <= len(md):
                    entries.append(tuple(md[off:off + 4]))
            block_info["button_entries"] = entries

        result["blocks"].append(block_info)

    return result


# ============================================================================
# MAIN: Test by generating and comparing files
# ============================================================================

if __name__ == "__main__":
    import os

    # Test 1: Generate a minimal .dat file
    print("=== Test 1: Generate minimal .dat ===")
    output = write_minimal_dat(
        profile_name="Test Profile",
        profile_color_rgb=(0xFF, 0x00, 0x80),
        dpi_stages=[800, 1600, 3200, 6400, 12800],
        output_path="ROCCAT_Manager/profiles/test_minimal.dat"
    )
    print(f"Generated {len(output)} bytes")

    # Test 2: Parse the generated file
    print("\n=== Test 2: Parse generated file ===")
    parsed = parse_dat("ROCCAT_Manager/profiles/test_minimal.dat")
    print(f"Blocks: {parsed['block_count']}")
    for block in parsed["blocks"]:
        print(f"  {block['name']}: {block['content_len']} bytes")
        if "profile_name" in block:
            print(f"    Name: {block['profile_name']}")
        if "dpi_stages" in block:
            print(f"    DPI: {block['dpi_stages']}")
        if "color_rgb" in block:
            print(f"    Color: {block['color_rgb']}")

    # Test 3: Parse the original KONE_XP_AIR.dat and compare
    print("\n=== Test 3: Parse original KONE_XP_AIR.dat ===")
    original = parse_dat("ROCCAT_Manager/profiles/KONE_XP_AIR.dat")
    print(f"Blocks: {original['block_count']}")
    for block in original["blocks"]:
        print(f"  {block['name']}: {block['content_len']} bytes")
        if "profile_name" in block:
            print(f"    Name: {block['profile_name']}")
        if "dpi_stages" in block:
            print(f"    DPI: {block['dpi_stages']}")
        if "color_rgb" in block:
            print(f"    Color: {block['color_rgb']}")

    # Test 4: Verify our minimal file matches KONE structure
    print("\n=== Test 4: Structural comparison ===")
    for orig_block in original["blocks"]:
        name = orig_block["name"]
        gen_block = next((b for b in parsed["blocks"] if b["name"] == name), None)
        if gen_block:
            match = orig_block["content_len"] == gen_block["content_len"]
            print(f"  {name}: orig={orig_block['content_len']} gen={gen_block['content_len']} {'OK' if match else 'MISMATCH'}")
        else:
            print(f"  {name}: MISSING in generated file")

    # Clean up test file
    os.remove("ROCCAT_Manager/profiles/test_minimal.dat")
    print("\nTest file cleaned up.")
