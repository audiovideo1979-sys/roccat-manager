"""
Raw USB Control Transfer test for ROCCAT Kone XP Air.

Based on the Kone Pro protocol (same generation):
- Uses HID SET_REPORT control transfers, NOT hidapi feature reports
- bmRequestType=0x21, bRequest=0x09, wValue=0x0300|report_id
- Report 0x04: profile select [0x04, idx, 0x80, 0x00]
- Report 0x06: settings (69 bytes, DPI as LE16*50, checksum)

The dongle (PID 0x5017) has interface 2 with usage page 0xFF03.
The mouse (PID 0x5019) has interfaces at 0,1,2.
"""
import usb.core
import usb.util
import usb.backend.libusb1
import time
import sys
import struct

# Try to find libusb
try:
    import libusb_package
    backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
except:
    backend = None

VENDOR = 0x10F5
DONGLE_PID = 0x5017
MOUSE_PID = 0x5019

# HID class request constants
HID_SET_REPORT = 0x09
HID_GET_REPORT = 0x01
HID_FEATURE_REPORT = 0x03

def hid_get_feature(dev, report_id, iface, length):
    """GET_REPORT control transfer for a feature report."""
    return dev.ctrl_transfer(
        0xA1,  # bmRequestType: class, interface, IN
        HID_GET_REPORT,
        (HID_FEATURE_REPORT << 8) | report_id,  # wValue
        iface,  # wIndex
        length  # wLength
    )

def hid_set_feature(dev, report_id, iface, data):
    """SET_REPORT control transfer for a feature report."""
    return dev.ctrl_transfer(
        0x21,  # bmRequestType: class, interface, OUT
        HID_SET_REPORT,
        (HID_FEATURE_REPORT << 8) | report_id,  # wValue
        iface,  # wIndex
        data  # data
    )

def hex_line(data, n=32):
    return " ".join("%02X" % b for b in data[:n])

def roccat_checksum(data):
    """Compute ROCCAT checksum (sum of all bytes except last 2)."""
    s = sum(data[:-2])
    return (s & 0xFF, (s >> 8) & 0xFF)

def main():
    print("=" * 60)
    print("ROCCAT Raw USB Control Transfer Test")
    print("=" * 60)
    print()

    # Find devices
    dongle = usb.core.find(idVendor=VENDOR, idProduct=DONGLE_PID, backend=backend)
    mouse = usb.core.find(idVendor=VENDOR, idProduct=MOUSE_PID, backend=backend)

    if not dongle:
        print("Dongle not found!")
    else:
        print("Found dongle: %s" % dongle)

    if not mouse:
        print("Mouse not found!")
    else:
        print("Found mouse: %s" % mouse)

    if not dongle and not mouse:
        print("\nNo devices found. On Windows, pyusb needs either:")
        print("  1. libusb-win32 or WinUSB driver installed on the device")
        print("  2. Or use zadig to replace the HID driver")
        print("\nThis won't work with the default Windows HID driver.")
        print("The HID driver claims the device exclusively.")
        print()
        print("Alternative: Use ctypes to call HidD_SetFeature directly")
        print("with the correct parameters.")
        return

    # Try each device and interface
    for dev, name in [(dongle, "DONGLE"), (mouse, "MOUSE")]:
        if not dev:
            continue

        print("\n--- %s ---" % name)
        print("Configs: %d" % dev.bNumConfigurations)

        for cfg in dev:
            for intf in cfg:
                iface_num = intf.bInterfaceNumber
                print("\n  Interface %d (class=%d, subclass=%d, protocol=%d)" % (
                    iface_num, intf.bInterfaceClass,
                    intf.bInterfaceSubClass, intf.bInterfaceProtocol))

                # Try to read report 0x06 (DPI/settings)
                try:
                    data = hid_get_feature(dev, 0x06, iface_num, 256)
                    print("    GET report 0x06: %s" % hex_line(data))
                except usb.core.USBError as e:
                    print("    GET report 0x06: %s" % e)

                # Try to read report 0x04 (status)
                try:
                    data = hid_get_feature(dev, 0x04, iface_num, 16)
                    print("    GET report 0x04: %s" % hex_line(data))
                except usb.core.USBError as e:
                    print("    GET report 0x04: %s" % e)

    print()
    print("If we got successful reads, the next step is to")
    print("write profile select (0x04) then settings (0x06).")

if __name__ == "__main__":
    main()
