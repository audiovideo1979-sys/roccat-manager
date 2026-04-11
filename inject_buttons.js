// Inject button data into Swarm II using its own persistent HID handle
var kone = Process.getModuleByName('KONE_XP_AIR.dll');
var exports = kone.enumerateExports();
var sendAddr = null, getAddr = null;

for (var i = 0; i < exports.length; i++) {
    if (exports[i].name === 'hid_send_feature_report') sendAddr = exports[i].address;
    if (exports[i].name === 'hid_get_feature_report') getAddr = exports[i].address;
}

var nativeSend = new NativeFunction(sendAddr, 'int', ['pointer', 'pointer', 'int']);
var nativeGet = new NativeFunction(getAddr, 'int', ['pointer', 'pointer', 'int']);

// Capture Swarm's persistent handle
var persistentHandle = null;

Interceptor.attach(sendAddr, {
    onEnter: function(args) {
        var d0 = args[1].readU8();
        if (d0 === 0x06) {
            var d2 = args[1].add(2).readU8();
            if (d2 !== 0x4d) {
                persistentHandle = args[0];
            }
        }
    }
});

// Button data template (from Frida capture of actual Swarm write)
// With Delete (0x4C) on thumb_button_1 instead of Q (0x14)
var buttonPages = [
    [0x00, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x03, 0x01, 0x00, 0x00, 0x09, 0x01, 0x00, 0x00, 0x0a, 0x01, 0x00, 0x00, 0x05, 0x01],
    [0x00, 0x00, 0x06, 0x01, 0x00, 0x00, 0x02, 0x02, 0x00, 0x00, 0x03, 0x02, 0x00, 0x4c, 0x00, 0x06, 0x00, 0x08, 0x00, 0x06, 0x00, 0x00, 0x07, 0x01, 0x00],
    [0x00, 0x08, 0x01, 0x00, 0x00, 0x01, 0x0a, 0x00, 0x00, 0x01, 0x08, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x04, 0x03, 0x00, 0x00],
    [0x07, 0x03, 0x00, 0x00, 0x08, 0x03, 0x00, 0x4b, 0x00, 0x06, 0x00, 0x4e, 0x00, 0x06, 0x00, 0x19, 0x01, 0x06, 0x00, 0x06, 0x01, 0x06, 0x00, 0x4c, 0x00],
    [0x06, 0x00, 0x49, 0x00, 0x06, 0x00, 0x00, 0x02, 0x03, 0x00, 0x00, 0x03, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0b, 0x08, 0x00, 0x00, 0x00, 0x00],
];

function pad30(arr) {
    var buf = Memory.alloc(30);
    for (var i = 0; i < 30; i++) buf.add(i).writeU8(0);
    for (var i = 0; i < arr.length && i < 30; i++) buf.add(i).writeU8(arr[i]);
    return buf;
}

function sendCmd(handle, data) {
    var buf = pad30(data);
    return nativeSend(handle, buf, 30);
}

function handshake(handle) {
    sendCmd(handle, [0x06, 0x01, 0x44, 0x07]);
    Thread.sleep(0.1);
    var rbuf = Memory.alloc(30);
    rbuf.writeU8(0x06);
    nativeGet(handle, rbuf, 30);
    Thread.sleep(0.05);
}

setTimeout(function() {
    if (!persistentHandle) {
        send('ERROR: No handle captured');
        return;
    }

    send('Writing buttons with handle: ' + persistentHandle);

    // Write all 5 pages
    for (var pg = 0; pg < 5; pg++) {
        sendCmd(persistentHandle, [0x06, 0x01, 0x47, 0x06, 0x02, pg, 0x00]);
        Thread.sleep(0.05);
        handshake(persistentHandle);

        var pageCmd = [0x06, 0x01, 0x47, 0x06, 0x19].concat(buttonPages[pg]);
        var n = sendCmd(persistentHandle, pageCmd);
        Thread.sleep(0.05);
        handshake(persistentHandle);
        send('  Page ' + pg + ': ' + n);
    }

    send('Button write complete! Test button 12!');
}, 3000);
