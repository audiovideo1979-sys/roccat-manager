"""
Direct Windows HID API calls via ctypes.
Targets the dongle's interfaces which have interrupt OUT endpoints.

The key insight: SWARM II likely uses WriteFile on the dongle's
interrupt OUT endpoint, NOT HidD_SetFeature. hidapi's write()
may be targeting the wrong HID collection.
"""
import ctypes
from ctypes import wintypes
import time
import struct

# Windows API
kernel32 = ctypes.windll.kernel32
hid = ctypes.windll.hid
setupapi = ctypes.windll.setupapi

# Constants
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000

# HID GUID
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]

class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]

def get_hid_guid():
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    return guid

def enumerate_hid_devices():
    """Find all ROCCAT HID device paths with their capabilities."""
    guid = get_hid_guid()
    dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )

    devices = []
    idx = 0
    while True:
        iface_data = SP_DEVICE_INTERFACE_DATA()
        iface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

        if not setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, ctypes.byref(guid), idx, ctypes.byref(iface_data)
        ):
            break
        idx += 1

        # Get required size
        req_size = wintypes.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, ctypes.byref(iface_data), None, 0, ctypes.byref(req_size), None
        )

        # Get detail
        detail_size = req_size.value
        detail_buf = ctypes.create_string_buffer(detail_size)
        # Set cbSize to size of fixed part (4 + pointer alignment)
        ctypes.memmove(detail_buf, struct.pack("I", 8), 4)  # 8 for 64-bit

        if not setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, ctypes.byref(iface_data),
            detail_buf, detail_size, None, None
        ):
            continue

        # Extract path (starts at offset 4, is a wide string)
        path = ctypes.wstring_at(ctypes.addressof(detail_buf) + 4)

        if "10f5" not in path.lower() and "1e7d" not in path.lower():
            continue

        # Open and get attributes
        handle = kernel32.CreateFileW(
            path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )

        if handle == -1:
            # Try read-only
            handle = kernel32.CreateFileW(
                path, GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None
            )
            if handle == -1:
                continue

        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        hid.HidD_GetAttributes(handle, ctypes.byref(attrs))

        # Get capabilities
        preparsed = ctypes.c_void_p()
        hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed))
        caps = HIDP_CAPS()
        ctypes.windll.hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
        hid.HidD_FreePreparsedData(preparsed)

        kernel32.CloseHandle(handle)

        devices.append({
            "path": path,
            "vid": attrs.VendorID,
            "pid": attrs.ProductID,
            "usage_page": caps.UsagePage,
            "usage": caps.Usage,
            "output_len": caps.OutputReportByteLength,
            "feature_len": caps.FeatureReportByteLength,
            "input_len": caps.InputReportByteLength,
        })

    setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return devices

def try_write(path, label, report_data, method="output"):
    """Open device and try to write."""
    handle = kernel32.CreateFileW(
        path, GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        print("  Cannot open %s" % label)
        return False

    buf = (ctypes.c_byte * len(report_data))(*report_data)
    result = False

    if method == "output":
        result = hid.HidD_SetOutputReport(handle, buf, len(report_data))
        print("  HidD_SetOutputReport on %s: %s" % (label, "OK" if result else "FAIL"))
    elif method == "feature":
        result = hid.HidD_SetFeature(handle, buf, len(report_data))
        print("  HidD_SetFeature on %s: %s" % (label, "OK" if result else "FAIL"))
    elif method == "writefile":
        written = wintypes.DWORD()
        result = kernel32.WriteFile(handle, buf, len(report_data),
                                    ctypes.byref(written), None)
        print("  WriteFile on %s: %s (wrote %d)" % (label, "OK" if result else "FAIL", written.value))

    kernel32.CloseHandle(handle)
    return result

def main():
    print("=" * 60)
    print("Windows HID Direct API Test")
    print("=" * 60)
    print()

    devices = enumerate_hid_devices()
    print("ROCCAT devices found:")
    for d in devices:
        name = "DONGLE" if d["pid"] == 0x5017 else "MOUSE"
        print("  %s PID=%04X UP=%04X:%04X out=%d feat=%d in=%d" % (
            name, d["pid"], d["usage_page"], d["usage"],
            d["output_len"], d["feature_len"], d["input_len"]
        ))
    print()

    # Focus on devices with output report capability
    writable = [d for d in devices if d["output_len"] > 0]
    print("Devices with output reports (%d):" % len(writable))
    for d in writable:
        name = "DONGLE" if d["pid"] == 0x5017 else "MOUSE"
        print("  %s UP=%04X out_len=%d" % (name, d["usage_page"], d["output_len"]))
    print()

    # Build Kone-Pro-style DPI command
    # Report 0x04: select profile 0 for settings mode
    cmd_select = [0x04, 0x00, 0x80, 0x00]
    # Pad to output report size
    cmd_select_padded = cmd_select + [0x00] * (64 - len(cmd_select))

    # Report 0x06: DPI settings (Kone Pro format, 69 bytes)
    # We'll try a minimal version first
    target_dpi = 450
    dpi_le16 = target_dpi // 50  # 9
    cmd_dpi = [0x06]  # report ID
    cmd_dpi += [0x00] * 5  # padding to offset 6
    cmd_dpi += [0x00]  # active DPI switch = 0
    cmd_dpi += list(struct.pack("<H", dpi_le16))  # DPI stage 0
    cmd_dpi += list(struct.pack("<H", dpi_le16))  # DPI stage 1
    cmd_dpi += list(struct.pack("<H", dpi_le16))  # DPI stage 2
    cmd_dpi += list(struct.pack("<H", dpi_le16))  # DPI stage 3
    cmd_dpi += list(struct.pack("<H", dpi_le16))  # DPI stage 4
    cmd_dpi += [0x00] * (67 - len(cmd_dpi))  # pad to 67
    # Checksum
    s = sum(cmd_dpi)
    cmd_dpi += [s & 0xFF, (s >> 8) & 0xFF]  # 69 bytes total

    print("Testing writes on all writable devices...")
    print()

    for d in writable:
        name = "DONGLE" if d["pid"] == 0x5017 else "MOUSE"
        label = "%s UP=%04X" % (name, d["usage_page"])
        out_len = d["output_len"]

        print("--- %s (output_len=%d) ---" % (label, out_len))

        # Pad commands to expected output report length
        sel = cmd_select[:out_len] + [0] * max(0, out_len - len(cmd_select))
        dpi = cmd_dpi[:out_len] + [0] * max(0, out_len - len(cmd_dpi))

        # Try all three methods
        for method in ["output", "feature", "writefile"]:
            print("  [%s] Profile select (0x04):" % method)
            try_write(d["path"], label, sel, method)
            time.sleep(0.1)

            print("  [%s] DPI write (0x06):" % method)
            try_write(d["path"], label, dpi, method)
            time.sleep(0.1)
        print()

    print("Move your mouse — does the DPI feel different (450 = very slow)?")

if __name__ == "__main__":
    main()
