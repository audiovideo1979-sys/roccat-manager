"""Hook NtDeviceIoControlFile — catches ALL device I/O at the syscall level."""
import frida, sys, time

JS = """
var nt = Module.findExportByName('ntdll.dll', 'NtDeviceIoControlFile');
send('NtDeviceIoControlFile at: ' + nt);

if (nt) {
    Interceptor.attach(nt, {
        onEnter: function(args) {
            var ioctl = args[5].toInt32() >>> 0;
            var inLen = args[7].toInt32();
            // HID IOCTLs: 0xB00xx range
            // IOCTL_HID_SET_FEATURE = 0xB0191
            // IOCTL_HID_GET_FEATURE = 0xB0192
            // IOCTL_HID_SET_OUTPUT_REPORT = 0xB0195
            // IOCTL_HID_GET_INPUT_REPORT = 0xB0202
            var code = ioctl.toString(16).toUpperCase();
            if (code.indexOf('B0') === 0 && inLen > 0 && inLen <= 512) {
                var arr = [];
                var buf = args[6];
                for (var i = 0; i < inLen && i < 80; i++) {
                    var b = buf.add(i).readU8().toString(16);
                    if (b.length < 2) b = '0' + b;
                    arr.push(b);
                }
                send('IOCTL=0x' + code + ' len=' + inLen + ' data=' + arr.join(' '));
            }
        }
    });
    send('HOOKED - change DPI now!');
} else {
    send('FAILED to find NtDeviceIoControlFile');
}
"""

# Also try hooking NtWriteFile for interrupt OUT writes
JS2 = """
var nw = Module.findExportByName('ntdll.dll', 'NtWriteFile');
send('NtWriteFile at: ' + nw);

if (nw) {
    Interceptor.attach(nw, {
        onEnter: function(args) {
            var len = args[7].toInt32();
            if (len > 0 && len <= 256) {
                var buf = args[5];
                var first = buf.readU8();
                // HID reports start with report ID (0x00-0x10 typically)
                if (first <= 0x10) {
                    var arr = [];
                    for (var i = 0; i < len && i < 80; i++) {
                        var b = buf.add(i).readU8().toString(16);
                        if (b.length < 2) b = '0' + b;
                        arr.push(b);
                    }
                    send('NTWRITE len=' + len + ' data=' + arr.join(' '));
                }
            }
        }
    });
    send('Hooked NtWriteFile');
}
"""

def on_msg(msg, data):
    if msg['type'] == 'send':
        payload = msg['payload']
        if 'IOCTL' in str(payload) or 'NTWRITE' in str(payload):
            print(">>> %s" % payload)
        else:
            print("[%s]" % payload)
    elif msg['type'] == 'error':
        print("[ERR] %s" % msg.get('description', ''))

device = frida.get_local_device()
targets = []
for p in device.enumerate_processes():
    if 'turtle' in p.name.lower():
        targets.append(p)

for t in targets:
    print("Attaching to %s (PID %d)..." % (t.name, t.pid))
    try:
        session = frida.attach(t.pid)
        # Combine both hooks
        script = session.create_script(JS + "\n" + JS2)
        script.on('message', on_msg)
        script.load()
        print("  OK!")
    except Exception as e:
        print("  Failed: %s" % e)

print("\nLISTENING — change DPI in SWARM II and save!")
print("Ctrl+C to stop.\n")

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
print("Done.")
