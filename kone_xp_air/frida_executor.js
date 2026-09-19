// Runs an op list through Swarm II's own hidapi handle to the Kone XP Air receiver.
// Loaded by kone_xp_air.transport.FridaTransport; %%PARAMS%% is replaced with JSON:
//   { ops: [{k:'send', d:[..30 bytes..], l:'label'} | {k:'get'} | {k:'sleep', s:0.05} | {k:'mark', l:'..'}],
//     wait_handle_s: 8, prefer_non_lighting: true, diag: false }
// Result message: { done: true, ok: bool, results: [{i, rc, r?}], handle, handles, diag, log, error? }
'use strict';
var PARAMS = %%PARAMS%%;
var LOG = [];
function log(m) { LOG.push(String(m)); }
function hex(ptr, n) {
    var s = [];
    for (var i = 0; i < n; i++) s.push(('0' + ptr.add(i).readU8().toString(16)).slice(-2));
    return s.join(' ');
}
function findExport(mod, name) {
    var ex = mod.enumerateExports();
    for (var i = 0; i < ex.length; i++) if (ex[i].name === name) return ex[i].address;
    return null;
}
function getModule(name) {
    var m = Process.findModuleByName(name);
    if (!m) { try { Module.load(name); } catch (e) { log('Module.load(' + name + ') failed: ' + e); } m = Process.findModuleByName(name); }
    return m;
}

var kone = Process.findModuleByName('KONE_XP_AIR.dll');
if (!kone) {
    send({ done: true, ok: false, error: 'KONE_XP_AIR.dll is not loaded in this process (is the mouse connected in Swarm II?)', log: LOG });
} else {
    main(kone);
}

function main(kone) {
    var sendAddr = findExport(kone, 'hid_send_feature_report');
    var getAddr = findExport(kone, 'hid_get_feature_report');
    var openPathAddr = findExport(kone, 'hid_open_path');
    if (!sendAddr || !getAddr) {
        send({ done: true, ok: false, error: 'hid_send_feature_report / hid_get_feature_report not exported by KONE_XP_AIR.dll', log: LOG });
        return;
    }
    var nativeSend = new NativeFunction(sendAddr, 'int', ['pointer', 'pointer', 'size_t']);
    var nativeGet = new NativeFunction(getAddr, 'int', ['pointer', 'pointer', 'size_t']);

    // Every hid_device* Swarm uses for report 0x06, with the command bytes seen on it.
    var handles = {};
    var running = false;   // true once run() starts issuing OUR writes, so they don't pollute the census
    Interceptor.attach(sendAddr, {
        onEnter: function (args) {
            if (running) return;
            try {
                var buf = args[1];
                if (buf.isNull() || buf.readU8() !== 0x06) return;
                var key = args[0].toString();
                var h = handles[key];
                if (!h) h = handles[key] = { ptr: args[0], n: 0, cmds: {}, first: hex(buf, 10) };
                h.n++;
                var c = buf.add(2).readU8();
                h.cmds[c] = (h.cmds[c] || 0) + 1;
                h.last = hex(buf, 10);
            } catch (e) { }
        }
    });
    if (openPathAddr) {
        Interceptor.attach(openPathAddr, {
            onEnter: function (args) { try { log('hid_open_path(' + args[0].readCString() + ')'); } catch (e) { } }
        });
    }

    function nonLighting(h) { var n = 0; for (var c in h.cmds) if (parseInt(c) !== 0x4d) n += h.cmds[c]; return n; }
    function summarize() {
        var out = [];
        for (var k in handles) {
            var h = handles[k], cmds = {};
            for (var c in h.cmds) cmds['0x' + parseInt(c).toString(16)] = h.cmds[c];
            out.push({ handle: k, sends: h.n, cmds: cmds, first: h.first, last: h.last });
        }
        return out;
    }
    function pick(expired) {
        var any = null;
        for (var k in handles) {
            var h = handles[k];
            if (!PARAMS.prefer_non_lighting || nonLighting(h) > 0) return h;
            if (!any) any = h;
        }
        return expired ? any : null;
    }

    var deadline = Date.now() + (PARAMS.wait_handle_s || 8) * 1000;
    var timer = setInterval(function () {
        var expired = Date.now() > deadline;
        var h = pick(expired);
        if (h) { clearInterval(timer); run(h); return; }
        if (expired) {
            clearInterval(timer);
            send({ done: true, ok: false, error: 'no hid handle for report 0x06 seen in ' + (PARAMS.wait_handle_s || 8) + 's - is Swarm II connected to the mouse?', handles: summarize(), log: LOG });
        }
    }, 100);

    function run(h) {
        var handle = h.ptr;
        var diag = null;
        if (PARAMS.diag) { try { diag = diagnose(handle); } catch (e) { diag = { error: String(e) }; } }
        running = true;   // from here our own sends must not be counted against Swarm's handle
        var buf = Memory.alloc(64);
        var results = [];
        var ops = PARAMS.ops || [];
        for (var i = 0; i < ops.length; i++) {
            var op = ops[i];
            try {
                if (op.k === 'send') {
                    for (var j = 0; j < 30; j++) buf.add(j).writeU8(j < op.d.length ? op.d[j] : 0);
                    var src = nativeSend(handle, buf, 30);
                    for (var a = 0; a < 2 && src < 0; a++) { Thread.sleep(0.02); src = nativeSend(handle, buf, 30); }
                    results.push({ i: i, rc: src });
                    if (src < 0 && PARAMS.abort_on_error) {   // do not send the commit after a failed page write
                        results.push({ i: i, note: 'aborted after failed send' });
                        break;
                    }
                } else if (op.k === 'get') {
                    for (var j = 0; j < 30; j++) buf.add(j).writeU8(j === 0 ? 0x06 : 0);
                    var rc = nativeGet(handle, buf, 30);
                    results.push({ i: i, rc: rc, r: hex(buf, 30) });
                } else if (op.k === 'sleep') {
                    Thread.sleep(op.s);
                    results.push({ i: i });
                } else {
                    results.push({ i: i });
                }
            } catch (e) {
                results.push({ i: i, rc: -1, err: String(e) });
                if (PARAMS.abort_on_error) break;
            }
        }
        send({ done: true, ok: true, results: results, handle: handle.toString(), handles: summarize(), diag: diag, log: LOG });
    }

    // Identify what Swarm's handle actually points at: VID/PID, usage page/usage, report lengths, kernel object name.
    function diagnose(hidDev) {
        var out = {};
        try {
        // hidapi (windows/hid.c): struct hid_device_ { HANDLE device_handle; BOOL blocking; USHORT output_report_length; ... }
        var hFile = hidDev.readPointer();
        out.device_handle = hFile.toString();
        var hid = getModule('hid.dll');
        if (hid) {
            var GetAttributes = findExport(hid, 'HidD_GetAttributes');
            var GetPreparsed = findExport(hid, 'HidD_GetPreparsedData');
            var FreePreparsed = findExport(hid, 'HidD_FreePreparsedData');
            var GetCaps = findExport(hid, 'HidP_GetCaps');
            var GetProduct = findExport(hid, 'HidD_GetProductString');
            if (GetAttributes) {
                var fn = new NativeFunction(GetAttributes, 'uint8', ['pointer', 'pointer']);
                var attr = Memory.alloc(16); attr.writeU32(12);
                if (fn(hFile, attr)) {
                    out.vid = '0x' + attr.add(4).readU16().toString(16);
                    out.pid = '0x' + attr.add(6).readU16().toString(16);
                    out.version = '0x' + attr.add(8).readU16().toString(16);
                } else out.attributes_error = 'HidD_GetAttributes failed';
            }
            if (GetPreparsed && GetCaps) {
                var getP = new NativeFunction(GetPreparsed, 'uint8', ['pointer', 'pointer']);
                var caps = new NativeFunction(GetCaps, 'uint32', ['pointer', 'pointer']);
                var pp = Memory.alloc(8);
                if (getP(hFile, pp)) {
                    var pd = pp.readPointer();
                    var c = Memory.alloc(128);
                    var st = caps(pd, c);
                    out.hidp_getcaps_status = '0x' + st.toString(16);
                    out.usage = '0x' + c.readU16().toString(16);
                    out.usage_page = '0x' + c.add(2).readU16().toString(16);
                    out.input_report_len = c.add(4).readU16();
                    out.output_report_len = c.add(6).readU16();
                    out.feature_report_len = c.add(8).readU16();
                    if (FreePreparsed) new NativeFunction(FreePreparsed, 'uint8', ['pointer'])(pd);
                } else out.preparsed_error = 'HidD_GetPreparsedData failed';
            }
            if (GetProduct) {
                var gp = new NativeFunction(GetProduct, 'uint8', ['pointer', 'pointer', 'uint32']);
                var pb = Memory.alloc(256);
                if (gp(hFile, pb, 256)) out.product = pb.readUtf16String();
            }
        } else out.hid_dll = 'hid.dll not available';
        var ntdll = Process.findModuleByName('ntdll.dll');
        if (ntdll) {
            var NtQueryObject = findExport(ntdll, 'NtQueryObject');
            if (NtQueryObject) {
                var q = new NativeFunction(NtQueryObject, 'uint32', ['pointer', 'uint32', 'pointer', 'uint32', 'pointer']);
                var nb = Memory.alloc(2048), ret = Memory.alloc(8);
                var s = q(hFile, 1, nb, 2048, ret);   // ObjectNameInformation
                if (s === 0) { var len = nb.readU16(); var p = nb.add(Process.pointerSize === 8 ? 8 : 4).readPointer(); out.object_name = p.readUtf16String(len / 2); }
                else out.ntqueryobject_status = '0x' + s.toString(16);
            }
        }
        } catch (e) { out.diagnose_error = String(e); }
        return out;
    }
}
