"""Find what DLLs SWARM II has loaded — specifically HID-related ones."""
import frida

device = frida.get_local_device()
for proc in device.enumerate_processes():
    if 'turtle' not in proc.name.lower():
        continue
    print("=== %s (PID %d) ===" % (proc.name, proc.pid))
    try:
        session = frida.attach(proc.pid)
        script = session.create_script("""
            var mods = Process.enumerateModules();
            var names = [];
            for (var i = 0; i < mods.length; i++) {
                var n = mods[i].name.toLowerCase();
                if (n.indexOf('hid') >= 0 || n.indexOf('usb') >= 0 ||
                    n.indexOf('device') >= 0 || n.indexOf('setup') >= 0 ||
                    n.indexOf('turtle') >= 0 || n.indexOf('roccat') >= 0 ||
                    n.indexOf('swarm') >= 0 || n.indexOf('cfgmgr') >= 0) {
                    names.push(mods[i].name + ' @ ' + mods[i].base);
                }
            }
            send(names);
        """)
        result = []
        def on_msg(msg, data):
            if msg['type'] == 'send':
                result.extend(msg['payload'])
        script.on('message', on_msg)
        script.load()
        import time; time.sleep(0.5)
        for r in result:
            print("  %s" % r)
        script.unload()
        session.detach()
    except Exception as e:
        print("  Error: %s" % e)
    print()
