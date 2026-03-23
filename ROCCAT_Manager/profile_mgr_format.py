#!/usr/bin/env python3
"""
ROCCAT SWARM II Profile Manager File Format (.dat) - Multi-Profile Container
=============================================================================
Reverse-engineered from KONE XP Air Profile_Mgr.dat and Stored_Profile_Mgr.dat files.

These files store MULTIPLE profiles in a single container, unlike the single-profile
export .dat files documented in SWARM_II_DAT_FORMAT.py.

There are TWO Profile Manager files per device:
  - <DEVICE>_Profile_Mgr.dat       = "Onboard" profiles (loaded on the mouse hardware)
  - <DEVICE>_Stored_Profile_Mgr.dat = "Stored" profiles (saved in SWARM software only)

Location: %APPDATA%/Turtle Beach/Swarm II/Setting/

FILE STRUCTURE OVERVIEW
-----------------------
  1. File Header (16 bytes, or 14 bytes if profile_count=0)
  2. Profile 0: Sub-header (4 bytes) + blocks
  3. Profile 1: Sub-header (4 bytes) + blocks
  ... and so on for each profile

FILE HEADER (16 bytes)
----------------------
  Offset  Size  Field              Description
  0       4     magic              BE32, device type (0x5A = KONE XP Air, 0x5C = Docking Station)
  4       2     version            BE16, always 0x0001
  6       2     stored_flag        BE16, 0x0000 = onboard profiles, 0xFFFF = stored profiles
  8       2     active_profile     BE16, 0-based index of active profile; 0xFFFF = none (stored files)
  10      2     padding            BE16, always 0x0000
  12      2     profile_count      BE16, number of profiles in this file (0-N)
  14      2     padding            BE16, always 0x0000 (omitted entirely when profile_count=0)

  When profile_count=0, the file is only 14 bytes (no trailing padding, no profile data).
  When profile_count>0, the file is 16 bytes followed by concatenated profile sections.

  Comparison with single-profile export .dat header:
    Single-profile:  magic(4) + version1(4=0x00010000) + version2(4=0x00010000) + block_count(2) + pad(2)
    Multi-profile:   magic(4) + version(2=0x0001) + stored_flag(2) + active(2) + pad(2) + count(2) + pad(2)
    Key difference: bytes 8-9 distinguish them. Single-profile has 0x0001 (part of version2),
    multi-profile onboard has 0x0000-0x0004 (active index), stored has 0xFFFF.

PER-PROFILE SECTION
--------------------
Each profile section consists of:
  [block_count: BE16] [padding: BE16 = 0x0000] [block_0] [block_1] ... [block_N-1]

  The block_count and blocks use the SAME format as single-profile .dat exports
  (documented in SWARM_II_DAT_FORMAT.py), with one critical difference:

  TRAILING BYTES RULE: The trailing 00 00 after data blocks is omitted ONLY for
  the very last block of the very last profile in the file. All other data blocks
  (including the last block of non-final profiles) retain their trailing 00 00.

OBSERVED BLOCK CONFIGURATIONS
------------------------------
Profiles can have varying numbers of blocks (6 to 11):

  6 blocks (minimal, ~631 bytes):
    DesktopProfile, KoneXPAirButtons, KoneXPAirMain, ProfileColor, ProfileImage, ProfileName

  9 blocks (~31.4 KB with macros):
    DesktopProfile, KoneXPAirButtons, KoneXPAirMacros, KoneXPAirMain,
    ProfileColor, ProfileImage, ProfileName, QuickLaunch, TalkKeyInfor

  10 blocks (with auto-switch enabled but no apps):
    AutoSwitch, DesktopProfile, KoneXPAirButtons, KoneXPAirMacros, KoneXPAirMain,
    ProfileColor, ProfileImage, ProfileName, QuickLaunch, TalkKeyInfor

  11 blocks (full, with auto-switch apps):
    AutoSwitch, AutoSwitchApp, DesktopProfile, KoneXPAirButtons, KoneXPAirMacros,
    KoneXPAirMain, ProfileColor, ProfileImage, ProfileName, QuickLaunch, TalkKeyInfor

ACTIVE PROFILE INDEX
--------------------
  For onboard Profile_Mgr.dat, the active_profile field (bytes 8-9) indicates which
  profile is currently selected on the mouse (0-based). For example, active_profile=4
  means the 5th profile is active. This corresponds to the profile the mouse is
  currently using.

  For stored Stored_Profile_Mgr.dat, active_profile is always 0xFFFF (no active profile).

STORED FLAG
-----------
  Bytes 6-7 distinguish onboard from stored files:
    0x0000 = onboard (profiles loaded on mouse hardware)
    0xFFFF = stored (profiles saved in software only)

PROFILE SIZE ESTIMATES
-----------------------
  - Minimal profile (6 blocks, no macros): ~631 bytes
  - Full profile (11 blocks, with macros): ~32 KB
  - The KoneXPAirMacros block alone is ~31.4 KB (mostly zeros)
  - 5 full profiles: ~160 KB; 5 minimal profiles: ~3.2 KB
"""

import struct
import os
import sys
from typing import Optional, List, Dict, Any

# Add parent path for importing single-profile format
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KNOWN_BLOCK_NAMES = {
    "AutoSwitch", "AutoSwitchApp", "DesktopProfile", "KoneXPAirButtons",
    "KoneXPAirMacros", "KoneXPAirMain", "ProfileColor", "ProfileImage",
    "ProfileName", "QuickLaunch", "TalkKeyInfor"
}

# Content type constants
CONTENT_SIMPLE = 0x0001       # DesktopProfile, AutoSwitch
CONTENT_DATA_0C = 0x000C      # KoneXPAirButtons, KoneXPAirMacros, KoneXPAirMain, etc.
CONTENT_DATA_0A = 0x000A      # ProfileImage, ProfileName
CONTENT_PROFILE_COLOR = None  # Fixed 16-byte format (no type marker)


# ============================================================================
# PARSER
# ============================================================================

def parse_block_content(name: str, data: bytes, pos: int, is_last_block_in_file: bool):
    """Parse a single block's content starting at pos. Returns (block_info, new_pos)."""
    block = {'name': name}

    if name == 'ProfileColor':
        raw = data[pos:pos + 16]
        block['raw_content'] = raw
        block['color_rgb'] = (raw[6], raw[8], raw[10])
        return block, pos + 16

    elif name in ('DesktopProfile', 'AutoSwitch'):
        raw = data[pos:pos + 6]
        block['raw_content'] = raw
        block['content_type'] = struct.unpack_from(">H", data, pos)[0]
        block['value'] = struct.unpack_from(">I", data, pos + 2)[0]
        return block, pos + 6

    else:
        # Data block: [00 TYPE] [00 00 00] [data_len: BE16] [data] [trailing 00 00]
        content_type = struct.unpack_from(">H", data, pos)[0]
        data_len = struct.unpack_from(">H", data, pos + 5)[0]
        payload = data[pos + 7:pos + 7 + data_len]

        block['content_type'] = content_type
        block['data_len'] = data_len
        block['data'] = payload

        if is_last_block_in_file:
            block['raw_content'] = data[pos:pos + 7 + data_len]
            new_pos = pos + 7 + data_len
        else:
            block['raw_content'] = data[pos:pos + 7 + data_len + 2]
            new_pos = pos + 7 + data_len + 2

        # Decode specific block types
        if name == 'ProfileName':
            block['profile_name'] = payload.decode('utf-16-be', errors='replace')
        elif name == 'ProfileImage':
            block['image_path'] = payload.decode('utf-16-be', errors='replace')
        elif name == 'KoneXPAirMain' and len(payload) >= 21:
            block['dpi_stages'] = [
                struct.unpack_from("<H", payload, 11 + i * 2)[0] for i in range(5)
            ]
            block['polling_wired'] = payload[7]
            block['polling_wireless'] = payload[8]
        elif name == 'AutoSwitchApp' and len(payload) >= 4:
            num_apps = struct.unpack_from(">I", payload, 0)[0]
            apps = []
            apos = 4
            for _ in range(num_apps):
                plen = struct.unpack_from(">I", payload, apos)[0]
                apos += 4
                app_path = payload[apos:apos + plen].decode('utf-16-be', errors='replace')
                apps.append(app_path)
                apos += plen
            block['apps'] = apps
        elif name == 'KoneXPAirButtons' and len(payload) >= 127:
            entries = []
            for j in range(30):
                off = 7 + j * 4
                if off + 4 <= len(payload):
                    entries.append(tuple(payload[off:off + 4]))
            block['button_entries'] = entries

        return block, new_pos


def parse_profile_mgr(filepath: str) -> Dict[str, Any]:
    """Parse a SWARM II Profile Manager .dat file.

    Returns a dict with:
      magic, version, stored_flag, active_profile, profile_count, profiles[]
    Each profile has: block_count, blocks[]
    Each block has: name, raw_content, and type-specific decoded fields.
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    magic = struct.unpack_from(">I", data, 0)[0]
    version = struct.unpack_from(">H", data, 4)[0]
    stored_flag = struct.unpack_from(">H", data, 6)[0]
    active_profile = struct.unpack_from(">H", data, 8)[0]
    # pad at 10-11
    profile_count = struct.unpack_from(">H", data, 12)[0]

    result = {
        'magic': magic,
        'version': version,
        'stored_flag': stored_flag,
        'active_profile': active_profile,
        'profile_count': profile_count,
        'profiles': [],
        'file_size': len(data),
    }

    if profile_count == 0:
        result['parsed_end'] = len(data)
        return result

    pos = 16  # skip file header (including trailing padding)

    for pi in range(profile_count):
        block_count = struct.unpack_from(">H", data, pos)[0]
        pos += 4  # block_count(2) + padding(2)

        profile_blocks = []
        for bi in range(block_count):
            is_last_in_file = (bi == block_count - 1) and (pi == profile_count - 1)

            # Read block name
            name_len = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            name = data[pos:pos + name_len].decode('utf-16-be')
            pos += name_len
            pos += 2  # null terminator 00 00

            block, pos = parse_block_content(name, data, pos, is_last_in_file)
            profile_blocks.append(block)

        result['profiles'].append({
            'block_count': block_count,
            'blocks': profile_blocks,
        })

    result['parsed_end'] = pos
    return result


# ============================================================================
# WRITER
# ============================================================================

def _write_block_name(name: str) -> bytes:
    """Write block name header: [name_len: BE16] [name: UTF-16BE] [null: 00 00]"""
    encoded = name.encode('utf-16-be')
    return struct.pack(">H", len(encoded)) + encoded + b'\x00\x00'


def write_profile_mgr(result: Dict[str, Any]) -> bytes:
    """Write a Profile Manager .dat file from parsed structure.

    The result dict must have the same structure as returned by parse_profile_mgr().
    Each block must have 'name' and 'raw_content' fields.
    """
    out = b''

    # File header
    out += struct.pack(">I", result['magic'])
    out += struct.pack(">H", result['version'])
    out += struct.pack(">H", result['stored_flag'])
    out += struct.pack(">H", result['active_profile'])
    out += b'\x00\x00'  # padding at offset 10
    out += struct.pack(">H", result['profile_count'])

    if result['profile_count'] == 0:
        # No trailing padding when no profiles
        return out

    out += b'\x00\x00'  # padding at offset 14

    for pi, prof in enumerate(result['profiles']):
        # Profile sub-header
        out += struct.pack(">H", prof['block_count'])
        out += b'\x00\x00'  # padding

        for bi, block in enumerate(prof['blocks']):
            is_last_in_file = (bi == prof['block_count'] - 1) and (pi == result['profile_count'] - 1)

            # Block name
            out += _write_block_name(block['name'])

            # Block content
            out += block['raw_content']

    return out


def write_profile_mgr_to_file(result: Dict[str, Any], filepath: str):
    """Write a Profile Manager structure to a .dat file."""
    data = write_profile_mgr(result)
    with open(filepath, 'wb') as f:
        f.write(data)
    return len(data)


# ============================================================================
# PROFILE MANIPULATION HELPERS
# ============================================================================

def _encode_utf16be(text: str) -> bytes:
    return text.encode('utf-16-be')


def _make_simple_content(value: int) -> bytes:
    """Build raw_content for a simple value block (DesktopProfile, AutoSwitch)."""
    return b'\x00\x01' + struct.pack(">I", value)


def _make_data_content(type_byte: int, data: bytes, is_last_block_in_file: bool = False) -> bytes:
    """Build raw_content for a data block."""
    header = bytes([0x00, type_byte, 0x00, 0x00, 0x00])
    data_len = struct.pack(">H", len(data))
    result = header + data_len + data
    if not is_last_block_in_file:
        result += b'\x00\x00'
    return result


def _make_profile_color_content(r: int, g: int, b: int) -> bytes:
    """Build raw_content for ProfileColor block (16 bytes)."""
    return bytes([
        0x10, 0x03, 0x00, 0x01, 0xFF, 0xFF,
        r, r, g, g, b, b,
        0x00, 0x00, 0x00, 0x00
    ])


def make_default_buttons_data() -> bytes:
    """Build 129-byte KoneXPAirButtons data with default assignments."""
    data = b'\x00\x00\x00'  # Padding
    data += b'\x7D\x07\x7D'  # Identifier
    data += b'\x00'  # Profile flags = default
    # 30 button entries (default)
    defaults = [
        (0x00, 0x00, 0x01, 0x01), (0x00, 0x00, 0x02, 0x01), (0x00, 0x00, 0x03, 0x01),
        (0x00, 0x00, 0x09, 0x01), (0x00, 0x00, 0x0A, 0x01), (0x00, 0x00, 0x05, 0x01),
        (0x00, 0x00, 0x06, 0x01), (0x00, 0x00, 0x02, 0x02), (0x00, 0x00, 0x03, 0x02),
        (0x00, 0x14, 0x00, 0x06), (0x00, 0x08, 0x00, 0x06), (0x00, 0x00, 0x07, 0x01),
        (0x00, 0x00, 0x08, 0x01), (0x00, 0x00, 0x01, 0x0A), (0x00, 0x00, 0x01, 0x08),
        (0x00, 0x00, 0x01, 0x01), (0x00, 0x00, 0x02, 0x01), (0x00, 0x00, 0x04, 0x03),
        (0x00, 0x00, 0x07, 0x03), (0x00, 0x00, 0x08, 0x03), (0x00, 0x4B, 0x00, 0x06),
        (0x00, 0x4E, 0x00, 0x06), (0x00, 0x19, 0x01, 0x06), (0x00, 0x06, 0x01, 0x06),
        (0x00, 0x4C, 0x00, 0x06), (0x00, 0x49, 0x00, 0x06), (0x00, 0x00, 0x02, 0x03),
        (0x00, 0x00, 0x03, 0x03), (0x00, 0x00, 0x00, 0x00), (0x00, 0x00, 0x0B, 0x08),
    ]
    for entry in defaults:
        data += bytes(entry)
    data += b'\xB9\x02'  # Default checksum
    return data


def make_default_main_data(
    dpi_stages=None,
    color_rgb=(0xC5, 0x0B, 0xDC),
    polling_wired=0x00,
    polling_wireless=0x00,
) -> bytes:
    """Build 82-byte KoneXPAirMain data with default settings."""
    if dpi_stages is None:
        dpi_stages = [400, 800, 1200, 1600, 3200]

    data = b'\x00\x00\x00'  # Padding
    data += b'\x4E\x06\x4E'  # Identifier
    data += b'\x00'  # Profile flag = default
    data += bytes([polling_wired, polling_wireless])
    data += b'\x1F'  # DPI flags = default 5-stage
    data += b'\x01'  # Active DPI stage = 1
    for dpi in dpi_stages:
        data += struct.pack("<H", dpi)
    for _ in range(5):
        data += b'\x00\x00'  # Backup DPI = zeros for default
    data += b'\x00\x00'  # Padding
    data += b'\x03'  # Constant
    data += b'\x09'  # LED effect = AIMO
    data += b'\x06'  # LED sub
    data += b'\xFF'  # LED param
    data += b'\x05'  # DPI stage count
    data += b'\x00\x00'  # Padding
    # 7 LED zones (AIMO default)
    for i in range(7):
        data += bytes([i, 0xFF, 0xFF, 0xFF, 0xFF])
    # Profile summary color
    data += bytes([0x01, 0xFF])
    data += bytes(color_rgb)
    data += b'\x00\x00'  # Trailing
    return data


def make_empty_macros_data() -> bytes:
    """Build 31414-byte KoneXPAirMacros data (empty macros)."""
    header = bytes.fromhex("0000001e00000413081304000100000000000000000000000000000000000000")
    return header + b'\x00' * (31414 - len(header))


def create_minimal_profile(
    name: str = "New Profile",
    color_rgb: tuple = (0xC5, 0x0B, 0xDC),
    dpi_stages: list = None,
) -> Dict[str, Any]:
    """Create a minimal 6-block profile (no macros, no auto-switch).

    Blocks: DesktopProfile, KoneXPAirButtons, KoneXPAirMain,
            ProfileColor, ProfileImage, ProfileName

    This is the smallest valid profile configuration, matching what SWARM II
    creates for a basic profile without macros or auto-switch apps.
    """
    blocks = [
        {'name': 'DesktopProfile', 'raw_content': _make_simple_content(0)},
        {'name': 'KoneXPAirButtons', 'raw_content': _make_data_content(0x0C, make_default_buttons_data())},
        {'name': 'KoneXPAirMain', 'raw_content': _make_data_content(0x0C, make_default_main_data(dpi_stages, color_rgb))},
        {'name': 'ProfileColor', 'raw_content': _make_profile_color_content(*color_rgb)},
        {'name': 'ProfileImage', 'raw_content': _make_data_content(0x0A,
            _encode_utf16be(":/icons/resource/graphic/icons/Basics/profile_icons/profile_default_icon.png"))},
        {'name': 'ProfileName', 'raw_content': _make_data_content(0x0A, _encode_utf16be(name))},
    ]
    return {'block_count': len(blocks), 'blocks': blocks}


def create_full_profile(
    name: str = "New Profile",
    color_rgb: tuple = (0xC5, 0x0B, 0xDC),
    dpi_stages: list = None,
    auto_switch_apps: list = None,
) -> Dict[str, Any]:
    """Create a full profile with macros block and optional auto-switch.

    9 blocks without auto-switch, 10-11 blocks with auto-switch.
    """
    blocks = []

    if auto_switch_apps is not None:
        blocks.append({'name': 'AutoSwitch', 'raw_content': _make_simple_content(0x00010000)})
        if len(auto_switch_apps) > 0:
            app_data = struct.pack(">I", len(auto_switch_apps))
            for app_path in auto_switch_apps:
                path_bytes = _encode_utf16be(app_path)
                app_data += struct.pack(">I", len(path_bytes))
                app_data += path_bytes
            blocks.append({'name': 'AutoSwitchApp', 'raw_content': _make_data_content(0x0C, app_data)})

    blocks.extend([
        {'name': 'DesktopProfile', 'raw_content': _make_simple_content(0)},
        {'name': 'KoneXPAirButtons', 'raw_content': _make_data_content(0x0C, make_default_buttons_data())},
        {'name': 'KoneXPAirMacros', 'raw_content': _make_data_content(0x0C, make_empty_macros_data())},
        {'name': 'KoneXPAirMain', 'raw_content': _make_data_content(0x0C, make_default_main_data(dpi_stages, color_rgb))},
        {'name': 'ProfileColor', 'raw_content': _make_profile_color_content(*color_rgb)},
        {'name': 'ProfileImage', 'raw_content': _make_data_content(0x0A,
            _encode_utf16be(":/icons/resource/graphic/icons/Basics/profile_icons/profile_default_icon.png"))},
        {'name': 'ProfileName', 'raw_content': _make_data_content(0x0A, _encode_utf16be(name))},
        {'name': 'QuickLaunch', 'raw_content': _make_data_content(0x0C, b'\x00\x00\x00\x00')},
        {'name': 'TalkKeyInfor', 'raw_content': _make_data_content(0x0C, b'\x00\x00\x00\x00')},
    ])

    return {'block_count': len(blocks), 'blocks': blocks}


def fix_trailing_bytes(result: Dict[str, Any]):
    """Fix trailing 00 00 bytes for all blocks in the structure.

    The last block of the last profile must NOT have trailing 00 00.
    All other data blocks MUST have trailing 00 00.

    Call this after adding/removing/reordering profiles to ensure correctness.
    """
    for pi, prof in enumerate(result['profiles']):
        for bi, block in enumerate(prof['blocks']):
            is_last_in_file = (bi == prof['block_count'] - 1) and (pi == result['profile_count'] - 1)
            name = block['name']

            # Only data blocks (not ProfileColor or simple value blocks) have trailing bytes
            if name == 'ProfileColor' or name in ('DesktopProfile', 'AutoSwitch'):
                continue

            raw = block['raw_content']
            # Determine current trailing state
            # Data block format: [00 TYPE] [00 00 00] [data_len: BE16] [data] [maybe 00 00]
            content_type = struct.unpack_from(">H", raw, 0)[0]
            data_len = struct.unpack_from(">H", raw, 5)[0]
            expected_without_trailing = 7 + data_len
            expected_with_trailing = 7 + data_len + 2

            has_trailing = len(raw) == expected_with_trailing

            if is_last_in_file and has_trailing:
                # Remove trailing
                block['raw_content'] = raw[:expected_without_trailing]
            elif not is_last_in_file and not has_trailing:
                # Add trailing
                block['raw_content'] = raw + b'\x00\x00'


def add_profile(result: Dict[str, Any], profile: Dict[str, Any], index: int = -1):
    """Add a profile to the Profile Manager structure.

    Args:
        result: The parsed Profile Manager dict.
        profile: A profile dict (from create_minimal_profile, create_full_profile, etc.)
        index: Position to insert at (-1 = append to end).

    After calling this, call fix_trailing_bytes() to ensure correct trailing bytes.
    """
    if index == -1 or index >= result['profile_count']:
        result['profiles'].append(profile)
    else:
        result['profiles'].insert(index, profile)

    result['profile_count'] = len(result['profiles'])
    fix_trailing_bytes(result)


def remove_profile(result: Dict[str, Any], index: int):
    """Remove a profile from the Profile Manager structure.

    After calling this, call fix_trailing_bytes() to ensure correct trailing bytes.
    Also adjusts active_profile if needed.
    """
    if index < 0 or index >= result['profile_count']:
        raise IndexError(f"Profile index {index} out of range (0-{result['profile_count']-1})")

    result['profiles'].pop(index)
    result['profile_count'] = len(result['profiles'])

    # Adjust active profile index
    if result['active_profile'] != 0xFFFF:
        if result['active_profile'] == index:
            result['active_profile'] = 0  # Reset to first profile
        elif result['active_profile'] > index:
            result['active_profile'] -= 1

    fix_trailing_bytes(result)


def extract_profile(result: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Extract a single profile from the container (deep copy)."""
    import copy
    if index < 0 or index >= result['profile_count']:
        raise IndexError(f"Profile index {index} out of range (0-{result['profile_count']-1})")
    return copy.deepcopy(result['profiles'][index])


def get_profile_name(profile: Dict[str, Any]) -> str:
    """Get the profile name from a profile dict."""
    for block in profile['blocks']:
        if block['name'] == 'ProfileName' and 'profile_name' in block:
            return block['profile_name']
        elif block['name'] == 'ProfileName':
            # Decode from raw_content
            raw = block['raw_content']
            data_len = struct.unpack_from(">H", raw, 5)[0]
            return raw[7:7 + data_len].decode('utf-16-be', errors='replace')
    return "Unknown"


def create_empty_profile_mgr(
    magic: int = 0x0000005A,
    is_stored: bool = True,
) -> Dict[str, Any]:
    """Create an empty Profile Manager structure."""
    return {
        'magic': magic,
        'version': 0x0001,
        'stored_flag': 0xFFFF if is_stored else 0x0000,
        'active_profile': 0xFFFF if is_stored else 0x0000,
        'profile_count': 0,
        'profiles': [],
    }


def export_profile_as_single_dat(profile: Dict[str, Any], filepath: str):
    """Export a single profile from the container as a standalone .dat file.

    Uses the single-profile .dat format (magic, version1, version2, block_count, padding).
    """
    blocks = profile['blocks']
    block_count = len(blocks)

    out = struct.pack(">I", 0x0000005A)   # Magic
    out += struct.pack(">I", 0x00010000)   # Version1
    out += struct.pack(">I", 0x00010000)   # Version2
    out += struct.pack(">H", block_count)  # Block count
    out += b'\x00\x00'                     # Padding

    for bi, block in enumerate(blocks):
        is_last = (bi == block_count - 1)
        out += _write_block_name(block['name'])

        raw = block['raw_content']
        name = block['name']

        # Fix trailing bytes for single-profile format
        if name not in ('ProfileColor', 'DesktopProfile', 'AutoSwitch'):
            content_type = struct.unpack_from(">H", raw, 0)[0]
            data_len = struct.unpack_from(">H", raw, 5)[0]
            base_len = 7 + data_len

            if is_last:
                # Last block: no trailing
                out += raw[:base_len]
            else:
                # Non-last block: must have trailing
                if len(raw) == base_len:
                    out += raw + b'\x00\x00'
                else:
                    out += raw[:base_len + 2]
        else:
            out += raw

    with open(filepath, 'wb') as f:
        f.write(out)
    return len(out)


def import_single_dat_as_profile(filepath: str) -> Dict[str, Any]:
    """Import a single-profile .dat file and return it as a profile dict
    suitable for adding to a Profile Manager container.
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    # Single-profile header: magic(4) + v1(4) + v2(4) + block_count(2) + pad(2) = 16
    block_count = struct.unpack_from(">H", data, 12)[0]
    pos = 16

    blocks = []
    for bi in range(block_count):
        is_last = (bi == block_count - 1)

        name_len = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        name = data[pos:pos + name_len].decode('utf-16-be')
        pos += name_len
        pos += 2  # null

        block, pos = parse_block_content(name, data, pos, is_last)
        blocks.append(block)

    return {'block_count': block_count, 'blocks': blocks}


# ============================================================================
# DISPLAY / DEBUG
# ============================================================================

def print_profile_mgr(result: Dict[str, Any]):
    """Print a human-readable summary of a Profile Manager structure."""
    is_stored = result['stored_flag'] == 0xFFFF
    file_type = "Stored" if is_stored else "Onboard"

    print(f"Profile Manager ({file_type})")
    print(f"  Magic: 0x{result['magic']:08X}")
    print(f"  Version: 0x{result['version']:04X}")
    print(f"  Stored flag: 0x{result['stored_flag']:04X}")
    print(f"  Active profile: {result['active_profile']}"
          + (" (none)" if result['active_profile'] == 0xFFFF else ""))
    print(f"  Profile count: {result['profile_count']}")
    if 'file_size' in result:
        print(f"  File size: {result['file_size']} bytes")
    print()

    for pi, prof in enumerate(result['profiles']):
        name = get_profile_name(prof)
        active_marker = " [ACTIVE]" if pi == result['active_profile'] else ""
        print(f"  Profile {pi}: \"{name}\" ({prof['block_count']} blocks){active_marker}")

        block_names = [b['name'] for b in prof['blocks']]
        print(f"    Blocks: {', '.join(block_names)}")

        for block in prof['blocks']:
            if 'dpi_stages' in block:
                print(f"    DPI: {block['dpi_stages']}")
            if 'color_rgb' in block:
                r, g, b = block['color_rgb']
                print(f"    Color: ({r}, {g}, {b})")
            if 'apps' in block:
                for app in block['apps']:
                    print(f"    Auto-switch: {app}")
        print()


# ============================================================================
# TESTS
# ============================================================================

def _test_round_trip():
    """Test that parsing and writing produces identical files."""
    import tempfile

    test_files = [
        r'C:/Users/audio/AppData/Roaming/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Profile_Mgr.dat',
        r'C:/Users/audio/AppData/Roaming/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Stored_Profile_Mgr.dat',
    ]

    all_passed = True
    for filepath in test_files:
        if not os.path.exists(filepath):
            print(f"SKIP: {os.path.basename(filepath)} not found")
            continue

        label = os.path.basename(filepath)
        result = parse_profile_mgr(filepath)
        rebuilt = write_profile_mgr(result)

        with open(filepath, 'rb') as f:
            original = f.read()

        if rebuilt == original:
            print(f"PASS: {label} round-trip ({len(original)} bytes)")
        else:
            print(f"FAIL: {label} - original={len(original)} rebuilt={len(rebuilt)}")
            all_passed = False
            for i in range(min(len(original), len(rebuilt))):
                if original[i] != rebuilt[i]:
                    print(f"  First diff at byte {i} (0x{i:06X})")
                    break

    return all_passed


def _test_add_profile():
    """Test adding a new profile to a stored profile manager."""
    filepath = r'C:/Users/audio/AppData/Roaming/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Stored_Profile_Mgr.dat'
    if not os.path.exists(filepath):
        print("SKIP: stored file not found")
        return True

    result = parse_profile_mgr(filepath)
    original_count = result['profile_count']

    # Add a minimal profile
    new_profile = create_minimal_profile(
        name="Added By Script",
        color_rgb=(0xFF, 0x80, 0x00),
        dpi_stages=[800, 1600, 3200, 6400, 12800],
    )
    add_profile(result, new_profile)

    assert result['profile_count'] == original_count + 1, "Profile count should increase"

    # Write and re-parse
    rebuilt = write_profile_mgr(result)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        f.write(rebuilt)
        tmp_path = f.name

    try:
        reparsed = parse_profile_mgr(tmp_path)
        assert reparsed['profile_count'] == original_count + 1
        assert reparsed['parsed_end'] == reparsed['file_size']

        last_name = get_profile_name(reparsed['profiles'][-1])
        assert last_name == "Added By Script", f"Expected 'Added By Script', got '{last_name}'"
        print(f"PASS: add_profile (added profile, reparsed OK, {len(rebuilt)} bytes)")
        return True
    finally:
        os.unlink(tmp_path)


def _test_export_import_single():
    """Test exporting a profile and importing it back."""
    filepath = r'C:/Users/audio/AppData/Roaming/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Stored_Profile_Mgr.dat'
    if not os.path.exists(filepath):
        print("SKIP: stored file not found")
        return True

    result = parse_profile_mgr(filepath)
    profile = extract_profile(result, 0)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        tmp_path = f.name

    try:
        size = export_profile_as_single_dat(profile, tmp_path)
        print(f"  Exported profile 0 as single .dat: {size} bytes")

        reimported = import_single_dat_as_profile(tmp_path)
        assert reimported['block_count'] == profile['block_count']
        assert get_profile_name(reimported) == get_profile_name(profile)
        print(f"PASS: export/import single .dat round-trip")
        return True
    finally:
        os.unlink(tmp_path)


def _test_create_empty():
    """Test creating an empty profile manager and adding profiles."""
    mgr = create_empty_profile_mgr(magic=0x5A, is_stored=True)
    assert mgr['profile_count'] == 0

    data = write_profile_mgr(mgr)
    assert len(data) == 14, f"Empty manager should be 14 bytes, got {len(data)}"

    # Add two profiles
    add_profile(mgr, create_minimal_profile("Profile A", (255, 0, 0)))
    add_profile(mgr, create_full_profile("Profile B", (0, 255, 0)))

    data = write_profile_mgr(mgr)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        f.write(data)
        tmp_path = f.name

    try:
        reparsed = parse_profile_mgr(tmp_path)
        assert reparsed['profile_count'] == 2
        assert reparsed['parsed_end'] == reparsed['file_size']
        assert get_profile_name(reparsed['profiles'][0]) == "Profile A"
        assert get_profile_name(reparsed['profiles'][1]) == "Profile B"
        print(f"PASS: create empty + add 2 profiles ({len(data)} bytes)")
        return True
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    print("=" * 70)
    print("SWARM II Profile Manager Format - Analysis & Tests")
    print("=" * 70)
    print()

    # Display both files
    for filepath, label in [
        (r'C:/Users/audio/AppData/Roaming/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Profile_Mgr.dat', 'Onboard'),
        (r'C:/Users/audio/AppData/Roaming/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Stored_Profile_Mgr.dat', 'Stored'),
    ]:
        if os.path.exists(filepath):
            result = parse_profile_mgr(filepath)
            print_profile_mgr(result)

    # Run tests
    print("=" * 70)
    print("Running Tests")
    print("=" * 70)
    print()

    _test_round_trip()
    _test_add_profile()
    _test_export_import_single()
    _test_create_empty()
