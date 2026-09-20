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
    // Show ONLY the profile-write / switch commands so the DPI sequence is short and unambiguous:
    //   0x45 profile-select, 0x46 profile block (page selects, writes, reads, commit), 0x47 buttons,
    //   0x49 commit, 0x4e activate.  Hidden: 0x44 status polling, 0x4d lighting, 06 00 receiver pings,
    //   and all GET responses (read REQUESTS still show as 06 01 46 07 sends).
    var KEEP = [0x45, 0x46, 0x47, 0x49, 0x4e];
    Interceptor.attach(sendAddr, {
        onEnter: function (args) {
            var b1 = args[1].add(1).readU8(), b2 = args[1].add(2).readU8();
            if (b1 !== 0x01 || KEEP.indexOf(b2) < 0) return;
            var len = args[2].toInt32();
            send({ dir: 'SEND', len: len, data: hex(args[1], len) });
        }
    });
    send({ line: 'hooked KONE_XP_AIR.dll — change the DPI in Swarm II now and click apply' });
}
