"""
Raw USB probe for Kone XP Air dongle.
Uses pyusb for direct control transfers to try protocol commands
that hidapi might not support (like SET_REPORT to specific endpoints).
"""
import usb.core
import usb.util
import sys
import time

# Set libusb backend
try:
    import libusb_package
    import usb.backend.libusb1
    backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
except ImportError:
    backend = None

VID = 0x10F5
DONGLE_PID = 0x5017

# HID class requests
HID_GET_REPORT = 0x01
HID_SET_REPORT = 0x09
HID_REPORT_TYPE_INPUT = 0x01
HID_REPORT_TYPE_OUTPUT = 0x02
HID_REPORT_TYPE_FEATURE = 0x03

def get_report(dev, report_type, report_id, interface, length=256):
    """USB HID GET_REPORT control transfer"""
    try:
        data = dev.ctrl_transfer(
            0xA1,  # bmRequestType: Device-to-host, Class, Interface
            HID_GET_REPORT,
            (report_type << 8) | report_id,  # wValue
            interface,  # wIndex
            length  # wLength
        )
        return list(data)
    except Exception as e:
        return None

def set_report(dev, report_type, report_id, interface, data):
    """USB HID SET_REPORT control transfer"""
    try:
        result = dev.ctrl_transfer(
            0x21,  # bmRequestType: Host-to-device, Class, Interface
            HID_SET_REPORT,
            (report_type << 8) | report_id,  # wValue
            interface,  # wIndex
            data
        )
        return result
    except Exception as e:
        print(f"  SET_REPORT error: {e}")
        return None

def hex_dump(data, prefix=""):
    if data:
        print(f"{prefix}{' '.join(f'{b:02x}' for b in data)}")

def main():
    print("=== Raw USB Probe for Kone XP Air Dongle ===\n")

    # Find device
    dev = usb.core.find(idVendor=VID, idProduct=DONGLE_PID, backend=backend)
    if dev is None:
        print("Device not found! (May need libusb backend)")
        print("Trying to list all USB devices...")
        for d in usb.core.find(find_all=True):
            if d.idVendor == VID:
                print(f"  Found VID={d.idVendor:04x} PID={d.idProduct:04x}")
        return

    print(f"Found device: VID={dev.idVendor:04x} PID={dev.idProduct:04x}")
    print(f"  Manufacturer: {dev.manufacturer}")
    print(f"  Product: {dev.product}")
    print(f"  Configs: {dev.bNumConfigurations}")

    # Show configuration
    cfg = dev.get_active_configuration()
    print(f"\n  Active config: {cfg.bConfigurationValue}")
    for intf in cfg:
        print(f"  Interface {intf.bInterfaceNumber} alt={intf.bAlternateSetting} "
              f"class={intf.bInterfaceClass} subclass={intf.bInterfaceSubClass} "
              f"protocol={intf.bInterfaceProtocol} endpoints={intf.bNumEndpoints}")
        for ep in intf:
            direction = "IN" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
            print(f"    EP 0x{ep.bEndpointAddress:02x} ({direction}) type={ep.bmAttributes & 3} "
                  f"maxpacket={ep.wMaxPacketSize}")

    # Probe each interface with GET_REPORT
    for iface_num in [0, 1, 2]:
        print(f"\n--- Interface {iface_num} ---")

        # Try to detach kernel driver
        try:
            if dev.is_kernel_driver_active(iface_num):
                dev.detach_kernel_driver(iface_num)
                print(f"  Detached kernel driver from IF{iface_num}")
        except Exception:
            pass

        # Try GET_REPORT for feature reports
        print(f"  Feature reports:")
        for rid in range(16):
            data = get_report(dev, HID_REPORT_TYPE_FEATURE, rid, iface_num)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                print(f"    Report 0x{rid:02x} ({len(data)} bytes):")
                hex_dump(data, "      ")

        # Try GET_REPORT for input reports
        print(f"  Input reports:")
        for rid in range(16):
            data = get_report(dev, HID_REPORT_TYPE_INPUT, rid, iface_num)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                print(f"    Report 0x{rid:02x} ({len(data)} bytes):")
                hex_dump(data, "      ")

        # Try GET_REPORT for output reports
        print(f"  Output reports:")
        for rid in range(16):
            data = get_report(dev, HID_REPORT_TYPE_OUTPUT, rid, iface_num)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                print(f"    Report 0x{rid:02x} ({len(data)} bytes):")
                hex_dump(data, "      ")

    # Now try some known ROCCAT protocol commands via SET_REPORT on IF2
    print(f"\n\n=== Trying Protocol Commands on IF2 ===")

    # Try check_dongle_connect: report 0x09 (device info) on IF2
    print("\n  Trying GET device info (report 0x09, feature)...")
    data = get_report(dev, HID_REPORT_TYPE_FEATURE, 0x09, 2, 64)
    if data:
        hex_dump(data, "    ")

    # Try report 0x0f (often used for mode switching in ROCCAT)
    print("\n  Trying mode switch reports...")
    for rid in [0x0f, 0x10, 0x12, 0x13, 0x14, 0x15]:
        data = get_report(dev, HID_REPORT_TYPE_FEATURE, rid, 2, 64)
        if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
            print(f"    Report 0x{rid:02x}:")
            hex_dump(data, "      ")

    # Try SET_REPORT with init command on IF2
    print("\n  Trying SET_REPORT init commands on IF2...")

    # Eruption style: report 0x04 init
    for i in range(1):
        for j in [0x80, 0x90]:
            cmd = [0x04, i, j, 0x00]
            result = set_report(dev, HID_REPORT_TYPE_FEATURE, 0x04, 2, cmd)
            print(f"    SET feature 0x04 [{i}, 0x{j:02x}]: result={result}")
            time.sleep(0.02)
            # Check status
            status = get_report(dev, HID_REPORT_TYPE_FEATURE, 0x01, 2, 4)
            if status:
                hex_dump(status, "      Status: ")

    # Try SET_REPORT on IF0 (mouse interface)
    print("\n  Trying SET_REPORT on IF0...")
    for i in range(1):
        for j in [0x80, 0x90]:
            cmd = [0x04, i, j, 0x00]
            result = set_report(dev, HID_REPORT_TYPE_FEATURE, 0x04, 0, cmd)
            print(f"    SET feature 0x04 [{i}, 0x{j:02x}]: result={result}")
            time.sleep(0.02)

    # Try output report on IF2 (hid_write style)
    print("\n  Trying SET output reports on IF2...")
    cmd = [0x90, 0x0a] + [0x00] * 62  # Battery query
    result = set_report(dev, HID_REPORT_TYPE_OUTPUT, 0x90, 2, cmd)
    print(f"    SET output 0x90 (battery): result={result}")
    if result:
        time.sleep(0.05)
        resp = get_report(dev, HID_REPORT_TYPE_INPUT, 0x90, 2, 64)
        if resp:
            hex_dump(resp, "      Response: ")

    print("\n=== Probe Complete ===")

if __name__ == '__main__':
    main()
