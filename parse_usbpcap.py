"""
Parse USBPcap pcap files to find HID SET_REPORT commands to the Kone XP Air dongle.
USBPcap uses a custom link-layer header format.
"""
import struct
import sys

def parse_pcap(filename):
    with open(filename, 'rb') as f:
        # Global header (24 bytes)
        magic = struct.unpack('<I', f.read(4))[0]
        if magic != 0xa1b2c3d4:
            print(f"Not a pcap file (magic={magic:#x})")
            return []

        ver_major, ver_minor = struct.unpack('<HH', f.read(4))
        f.read(8)  # thiszone, sigfigs
        snaplen = struct.unpack('<I', f.read(4))[0]
        linktype = struct.unpack('<I', f.read(4))[0]
        print(f"PCAP: v{ver_major}.{ver_minor}, snaplen={snaplen}, linktype={linktype}")

        packets = []
        pkt_num = 0
        while True:
            hdr = f.read(16)
            if len(hdr) < 16:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack('<IIII', hdr)
            data = f.read(incl_len)
            if len(data) < incl_len:
                break
            pkt_num += 1
            packets.append({
                'num': pkt_num,
                'ts': ts_sec + ts_usec / 1e6,
                'data': data,
                'orig_len': orig_len
            })

        return packets

def parse_usbpcap_header(data):
    """Parse USBPcap packet header.
    See: https://desowin.org/usbpcap/captureformat.html
    """
    if len(data) < 27:
        return None

    # USBPcap header
    header_len = struct.unpack('<H', data[0:2])[0]
    irp_id = struct.unpack('<Q', data[2:10])[0]
    irp_status = struct.unpack('<i', data[10:14])[0]
    urb_function = struct.unpack('<H', data[14:16])[0]
    irp_info = data[16]  # 0=direction PDO->FDO (submit), 1=FDO->PDO (complete)
    bus_id = struct.unpack('<H', data[17:19])[0]
    device_addr = struct.unpack('<H', data[19:21])[0]
    endpoint = data[21]
    transfer_type = data[22]  # 0=ISO, 1=INT, 2=CTRL, 3=BULK
    data_length = struct.unpack('<I', data[23:27])[0]

    result = {
        'header_len': header_len,
        'irp_id': irp_id,
        'irp_status': irp_status,
        'urb_function': urb_function,
        'direction': 'complete' if irp_info & 1 else 'submit',
        'bus_id': bus_id,
        'device': device_addr,
        'endpoint': endpoint,
        'transfer_type': ['ISO', 'INT', 'CTRL', 'BULK'][transfer_type] if transfer_type < 4 else f'?{transfer_type}',
        'data_length': data_length,
    }

    # For control transfers, parse setup packet
    if transfer_type == 2 and header_len >= 27 + 8:
        stage = data[27]  # 0=setup, 1=data, 2=status
        result['stage'] = stage
        if stage == 0 and len(data) >= 36:  # Setup packet
            bmRequestType = data[28]
            bRequest = data[29]
            wValue = struct.unpack('<H', data[30:32])[0]
            wIndex = struct.unpack('<H', data[32:34])[0]
            wLength = struct.unpack('<H', data[34:36])[0]
            result['setup'] = {
                'bmRequestType': bmRequestType,
                'bRequest': bRequest,
                'wValue': wValue,
                'wIndex': wIndex,
                'wLength': wLength,
            }

    # Payload
    result['payload'] = data[header_len:]

    return result

def is_hid_set_report(pkt_info):
    """Check if this is a HID SET_REPORT"""
    if pkt_info.get('transfer_type') != 'CTRL':
        return False
    setup = pkt_info.get('setup')
    if not setup:
        return False
    # SET_REPORT: bmRequestType=0x21, bRequest=0x09
    return setup['bmRequestType'] == 0x21 and setup['bRequest'] == 0x09

def is_hid_get_report(pkt_info):
    """Check if this is a HID GET_REPORT"""
    if pkt_info.get('transfer_type') != 'CTRL':
        return False
    setup = pkt_info.get('setup')
    if not setup:
        return False
    # GET_REPORT: bmRequestType=0xA1, bRequest=0x01
    return setup['bmRequestType'] == 0xA1 and setup['bRequest'] == 0x01

def main():
    if len(sys.argv) < 2:
        print("Usage: parse_usbpcap.py <capture.pcap>")
        return

    filename = sys.argv[1]
    print(f"Parsing {filename}...\n")

    packets = parse_pcap(filename)
    print(f"Total packets: {len(packets)}\n")

    if not packets:
        return

    base_ts = packets[0]['ts']

    # Find unique devices
    devices = set()
    ctrl_packets = []
    int_out_packets = []

    for pkt in packets:
        info = parse_usbpcap_header(pkt['data'])
        if not info:
            continue

        info['ts'] = pkt['ts'] - base_ts
        info['num'] = pkt['num']
        devices.add(info['device'])

        if info['transfer_type'] == 'CTRL' and info['direction'] == 'submit':
            ctrl_packets.append(info)

        # Also track interrupt OUT (hid_write)
        if info['transfer_type'] == 'INT' and info['direction'] == 'submit':
            ep_dir = info['endpoint'] & 0x80
            if ep_dir == 0 and info['payload']:  # OUT endpoint
                int_out_packets.append(info)

    print(f"Unique USB devices: {sorted(devices)}")
    print(f"Control transfers (submit): {len(ctrl_packets)}")
    print(f"Interrupt OUT transfers: {len(int_out_packets)}")

    # Show all SET_REPORT and GET_REPORT
    print(f"\n=== HID SET_REPORT commands ===")
    set_count = 0
    for info in ctrl_packets:
        if is_hid_set_report(info):
            set_count += 1
            setup = info['setup']
            report_type = (setup['wValue'] >> 8) & 0xFF
            report_id = setup['wValue'] & 0xFF
            iface = setup['wIndex']
            type_name = {1: 'Input', 2: 'Output', 3: 'Feature'}.get(report_type, f'?{report_type}')

            print(f"\n  [{info['ts']:8.3f}s] Pkt#{info['num']} Device:{info['device']} "
                  f"SET_{type_name} ID=0x{report_id:02x} IF={iface} len={setup['wLength']}")
            if info['payload']:
                hex_str = ' '.join(f'{b:02x}' for b in info['payload'][:64])
                print(f"    Data: {hex_str}")
                if len(info['payload']) > 64:
                    print(f"    ... ({len(info['payload'])} bytes total)")

    print(f"\n  Total SET_REPORT: {set_count}")

    # Show GET_REPORT
    print(f"\n=== HID GET_REPORT commands ===")
    get_count = 0
    for info in ctrl_packets:
        if is_hid_get_report(info):
            get_count += 1
            setup = info['setup']
            report_type = (setup['wValue'] >> 8) & 0xFF
            report_id = setup['wValue'] & 0xFF
            iface = setup['wIndex']
            type_name = {1: 'Input', 2: 'Output', 3: 'Feature'}.get(report_type, f'?{report_type}')

            if get_count <= 50:  # Limit output
                print(f"  [{info['ts']:8.3f}s] Pkt#{info['num']} Device:{info['device']} "
                      f"GET_{type_name} ID=0x{report_id:02x} IF={iface} len={setup['wLength']}")

    print(f"\n  Total GET_REPORT: {get_count}")

    # Show interrupt OUT data (hid_write)
    if int_out_packets:
        print(f"\n=== Interrupt OUT (hid_write) ===")
        for info in int_out_packets[:50]:
            hex_str = ' '.join(f'{b:02x}' for b in info['payload'][:64])
            print(f"  [{info['ts']:8.3f}s] Device:{info['device']} EP=0x{info['endpoint']:02x} "
                  f"len={len(info['payload'])}")
            print(f"    Data: {hex_str}")

if __name__ == '__main__':
    main()
