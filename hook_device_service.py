"""
Hook Turtle Beach Device Service to intercept HID API calls.
This will show us exactly what data gets sent to the mouse when Swarm II changes DPI.
"""
import frida
import sys
import time

JS_HOOK = """
// Hook HidD_SetFeature and HidD_SetOutputReport in hid.dll
var hidDll = Module.findBaseAddress('hid.dll');
if (!hidDll) {
    send({type: 'error', msg: 'hid.dll not loaded'});
}

// HidD_SetFeature(HANDLE, PVOID ReportBuffer, ULONG ReportBufferLength)
var HidD_SetFeature = Module.findExportByName('hid.dll', 'HidD_SetFeature');
if (HidD_SetFeature) {
    Interceptor.attach(HidD_SetFeature, {
        onEnter: function(args) {
            var handle = args[0];
            var buffer = args[1];
            var length = args[2].toInt32();
            var data = [];
            for (var i = 0; i < Math.min(length, 64); i++) {
                data.push(buffer.add(i).readU8());
            }
            send({
                type: 'HidD_SetFeature',
                handle: handle.toString(),
                length: length,
                data: data
            });
        },
        onLeave: function(retval) {
            send({type: 'HidD_SetFeature_result', result: retval.toInt32()});
        }
    });
    send({type: 'info', msg: 'Hooked HidD_SetFeature'});
}

// HidD_SetOutputReport
var HidD_SetOutputReport = Module.findExportByName('hid.dll', 'HidD_SetOutputReport');
if (HidD_SetOutputReport) {
    Interceptor.attach(HidD_SetOutputReport, {
        onEnter: function(args) {
            var handle = args[0];
            var buffer = args[1];
            var length = args[2].toInt32();
            var data = [];
            for (var i = 0; i < Math.min(length, 64); i++) {
                data.push(buffer.add(i).readU8());
            }
            send({
                type: 'HidD_SetOutputReport',
                handle: handle.toString(),
                length: length,
                data: data
            });
        }
    });
    send({type: 'info', msg: 'Hooked HidD_SetOutputReport'});
}

// HidD_GetFeature
var HidD_GetFeature = Module.findExportByName('hid.dll', 'HidD_GetFeature');
if (HidD_GetFeature) {
    Interceptor.attach(HidD_GetFeature, {
        onEnter: function(args) {
            this.buffer = args[1];
            this.length = args[2].toInt32();
        },
        onLeave: function(retval) {
            if (retval.toInt32()) {
                var data = [];
                for (var i = 0; i < Math.min(this.length, 64); i++) {
                    data.push(this.buffer.add(i).readU8());
                }
                // Only log non-polling reads (skip report 0x06 with 4d polling)
                if (data.length > 3 && !(data[0] == 0x06 && data[1] == 0x01 && data[2] == 0x4d)) {
                    send({
                        type: 'HidD_GetFeature',
                        length: this.length,
                        data: data
                    });
                }
            }
        }
    });
    send({type: 'info', msg: 'Hooked HidD_GetFeature'});
}

// DeviceIoControl - catch raw IOCTLs
var DeviceIoControl = Module.findExportByName('kernel32.dll', 'DeviceIoControl');
if (DeviceIoControl) {
    Interceptor.attach(DeviceIoControl, {
        onEnter: function(args) {
            var ioctl = args[1].toInt32() >>> 0;
            // HID IOCTLs: 0x000B0000 range
            // IOCTL_HID_SET_FEATURE = 0x000B0191
            // IOCTL_HID_SET_OUTPUT_REPORT = 0x000B0195
            // IOCTL_HID_GET_FEATURE = 0x000B0192
            if ((ioctl & 0xFFFF0000) === 0x000B0000) {
                var inBuf = args[2];
                var inLen = args[3].toInt32();
                var data = [];
                for (var i = 0; i < Math.min(inLen, 64); i++) {
                    data.push(inBuf.add(i).readU8());
                }
                send({
                    type: 'DeviceIoControl',
                    ioctl: '0x' + ioctl.toString(16),
                    inLen: inLen,
                    data: data
                });
            }
        }
    });
    send({type: 'info', msg: 'Hooked DeviceIoControl'});
}

send({type: 'ready', msg: 'All hooks installed. Change DPI in Swarm II now!'});
"""

def on_message(message, data):
    if message['type'] == 'send':
        payload = message['payload']
        msg_type = payload.get('type', '')

        if msg_type in ('info', 'ready', 'error'):
            print(f"[{msg_type}] {payload['msg']}")
        elif msg_type == 'HidD_SetFeature':
            hex_data = ' '.join(f'{b:02x}' for b in payload['data'][:32])
            print(f"\n>>> HidD_SetFeature (handle={payload['handle']}, len={payload['length']})")
            print(f"    {hex_data}")
        elif msg_type == 'HidD_SetOutputReport':
            hex_data = ' '.join(f'{b:02x}' for b in payload['data'][:32])
            print(f"\n>>> HidD_SetOutputReport (len={payload['length']})")
            print(f"    {hex_data}")
        elif msg_type == 'HidD_GetFeature':
            hex_data = ' '.join(f'{b:02x}' for b in payload['data'][:32])
            print(f"<<< HidD_GetFeature: {hex_data}")
        elif msg_type == 'DeviceIoControl':
            hex_data = ' '.join(f'{b:02x}' for b in payload['data'][:32])
            print(f"\n*** DeviceIoControl IOCTL={payload['ioctl']} inLen={payload['inLen']}")
            print(f"    {hex_data}")
        elif msg_type == 'HidD_SetFeature_result':
            print(f"    result: {'OK' if payload['result'] else 'FAILED'}")
    elif message['type'] == 'error':
        print(f"[FRIDA ERROR] {message}")


def main():
    # Find Device Service process
    target = "Turtle Beach Device Service.exe"

    try:
        session = frida.attach(target)
        print(f"Attached to {target}")
    except frida.ProcessNotFoundError:
        print(f"{target} not running!")
        return

    script = session.create_script(JS_HOOK)
    script.on('message', on_message)
    script.load()

    print("\n=== Listening for HID calls ===")
    print("Change DPI in Swarm II now!")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        session.detach()
        print("\nDetached.")


if __name__ == '__main__':
    main()
