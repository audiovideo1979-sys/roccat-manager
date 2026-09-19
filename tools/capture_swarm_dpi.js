// capture_swarm_dpi.js — log every HID feature report Swarm II sends/reads through KONE_XP_AIR.dll.
// Attach to Swarm's process, then change the DPI in Swarm and click apply; every 0x06 frame Swarm
// writes prints as SEND, every profile read as GET. This is what we need to reproduce the DPI write.
var kone = Process.getModuleByName('KONE_XP_AIR.dll');
var sendAddr = null, getAddr = null;
kone.enumerateExports().forEach(function (e) {
    if (e.name === 'hid_send_feature_report') sendAddr = e.address;
    if (e.name === 'hid_get_feature_report') getAddr = e.address;
});

function hex(ptr, n) {
    if (n > 30) n = 30;                 // feature reports are 30 bytes on this device
    var out = [];
    for (var i = 0; i < n; i++) {
        var b = ptr.add(i).readU8().toString(16);
        out.push(b.length < 2 ? '0' + b : b);
    }
    return out.join(' ');
}

if (!sendAddr) {
    send({ line: 'ERROR: hid_send_feature_report not found in KONE_XP_AIR.dll' });
} else {
    // int hid_send_feature_report(hid_device *dev, const unsigned char *data, size_t length)
    Interceptor.attach(sendAddr, {
        onEnter: function (args) {
            var len = args[2].toInt32();
            send({ dir: 'SEND', len: len, data: hex(args[1], len) });
        }
    });
    if (getAddr) Interceptor.attach(getAddr, {
        onEnter: function (args) { this.buf = args[1]; this.len = args[2].toInt32(); },
        onLeave: function () { send({ dir: 'GET ', len: this.len, data: hex(this.buf, this.len) }); }
    });
    send({ line: 'hooked KONE_XP_AIR.dll — change the DPI in Swarm II now and click apply' });
}
