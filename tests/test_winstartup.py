"""Loading this PC's main profile when Windows starts (no Windows, no mouse: a stand-in registry)."""
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'ROCCAT_Manager')
if APP not in sys.path:
    sys.path.insert(0, APP)
import winstartup as ws  # noqa: E402


class FakeReg:
    """Just enough of winreg for the Run key."""
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = 'HKCU', 1, 2, 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __init__(self, reg, path, create):
            if not create and path not in reg.values:
                raise FileNotFoundError(path)
            reg.values.setdefault(path, {})
            self.reg, self.path = reg, path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, reserved, access):
        return self._Key(self, path, create=False)

    def CreateKeyEx(self, root, path, reserved, access):
        return self._Key(self, path, create=True)

    def QueryValueEx(self, key, name):
        if name not in self.values[key.path]:
            raise FileNotFoundError(name)
        return self.values[key.path][name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[key.path][name] = value

    def DeleteValue(self, key, name):
        if name not in self.values[key.path]:
            raise FileNotFoundError(name)
        del self.values[key.path][name]


@pytest.fixture
def reg():
    return FakeReg()


def make_exe(path, content=b'MZ app v1', mtime=1_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))
    return path


# ── the login entry and the local copy ────────────────────────────────────────
def test_enable_copies_the_app_locally_and_adds_the_login_entry(reg, tmp_path):
    drive_exe = make_exe(tmp_path / 'G' / 'ROCCAT_Manager_Full' / 'ROCCAT Manager.exe')
    local = tmp_path / 'LocalAppData' / 'ROCCAT Manager' / 'app' / 'ROCCAT Manager.exe'
    settings = tmp_path / 'AppData' / 'ROCCAT Manager' / 'this_pc.json'
    ws.enable({'boot_id': 'boot2', 'slot': 1}, drive_exe, reg, settings, local)
    assert local.read_bytes() == drive_exe.read_bytes()
    assert ws.run_entry(reg) == '"%s" --startup' % local, "Windows starts the local copy, not the one in Drive"
    assert ws.load_settings(settings) == {'startup': {'boot_id': 'boot2', 'slot': 1, 'shared': False}}
    ws.disable(reg, settings)
    assert ws.run_entry(reg) is None and ws.load_settings(settings) == {}
    ws.disable(reg, settings)                                  # turning it off twice is fine


def test_a_bad_choice_is_refused(reg, tmp_path):
    for bad in ({'boot_id': 'boot3', 'slot': 1}, {'boot_id': 'boot1', 'slot': 6}, {'boot_id': 'boot1', 'slot': '1'}, None):
        with pytest.raises(ValueError):
            ws.enable(bad, make_exe(tmp_path / 'a.exe'), reg, tmp_path / 's.json', tmp_path / 'l.exe')
    assert ws.run_entry(reg) is None


def test_the_local_copy_follows_a_newer_app_and_never_goes_back(reg, tmp_path):
    local = tmp_path / 'local' / 'ROCCAT Manager.exe'
    v1 = make_exe(tmp_path / 'v1' / 'ROCCAT Manager.exe', b'MZ v1', 1_000_000)
    ws.enable({'boot_id': 'boot1', 'slot': 1}, v1, reg, tmp_path / 's.json', local)
    assert ws.refresh_installed_copy(v1, reg, local) is False, "same version: nothing to copy"
    v2 = make_exe(tmp_path / 'v2' / 'ROCCAT Manager.exe', b'MZ v2 bigger', 2_000_000)
    assert ws.refresh_installed_copy(v2, reg, local) is True and local.read_bytes() == b'MZ v2 bigger'
    assert ws.refresh_installed_copy(v1, reg, local) is False and local.read_bytes() == b'MZ v2 bigger'
    assert ws.refresh_installed_copy(local, reg, local) is False, "running the local copy itself"


def test_no_local_copy_is_made_while_startup_is_off(reg, tmp_path):
    local = tmp_path / 'local' / 'ROCCAT Manager.exe'
    assert ws.refresh_installed_copy(make_exe(tmp_path / 'x.exe'), reg, local) is False
    assert not local.exists()


def test_a_copy_that_cannot_be_replaced_right_now_is_not_an_error(reg, tmp_path, monkeypatch):
    local = tmp_path / 'local' / 'ROCCAT Manager.exe'
    ws.enable({'boot_id': 'boot1', 'slot': 1}, make_exe(tmp_path / 'v1.exe', b'v1', 1_000_000), reg, tmp_path / 's.json', local)

    def busy(a, b):
        raise PermissionError(32, 'The process cannot access the file because it is being used')
    monkeypatch.setattr(ws.os, 'replace', busy)
    assert ws.refresh_installed_copy(make_exe(tmp_path / 'v2.exe', b'v2!', 2_000_000), reg, local) is False


# ── at login ──────────────────────────────────────────────────────────────────
def env_for(tmp_path, shares):
    env = {'APPDATA': str(tmp_path / 'AppData'), 'LOCALAPPDATA': str(tmp_path / 'LocalAppData')}
    if shares:
        note = ws.local_root(env) / 'profiles' / ws.MOVED_NOTE
        note.parent.mkdir(parents=True)
        note.write_text('state: x\n')
    return env


def choose(env, boot_id='boot1', slot=1):
    ws.save_settings({'startup': {'boot_id': boot_id, 'slot': slot}}, ws.settings_file(env))


def test_login_with_nothing_chosen_does_nothing(tmp_path):
    env = env_for(tmp_path, shares=True)
    calls = []
    out = ws.run_at_login(lambda c: calls.append(c) or {'success': True}, lambda n: None,
                          log=lambda m: None, settings_path=ws.settings_file(env), env=env)
    assert out == 'nothing-chosen' and calls == []


def test_login_waits_for_google_drive_then_loads(tmp_path):
    env = env_for(tmp_path, shares=True)
    choose(env, 'boot2', 3)
    drive = tmp_path / 'G' / 'ROCCAT Manager Data'
    checks, calls = [], []

    def wait(ready):                       # Google Drive mounts on the third look
        for i in range(5):
            checks.append(i)
            if i == 2:
                (drive / 'profiles').mkdir(parents=True)
                (drive / 'profiles' / 'stored.json').write_text('{"profiles": []}')
                (drive / 'profiles' / 'slots.json').write_text('{"boot1": [null, null, null, null, null]}')
            if ready():
                return True
        return False
    out = ws.run_at_login(lambda c: calls.append((c['boot_id'], c['slot'])) or {'success': True},
                          lambda name: drive if drive.exists() else None,
                          log=lambda m: None, settings_path=ws.settings_file(env), env=env, wait=wait)
    assert out == 'loaded' and calls == [('boot2', 3)] and len(checks) == 3


def test_login_loads_nothing_if_google_drive_never_shows_up(tmp_path):
    env = env_for(tmp_path, shares=True)
    choose(env)
    calls, logged = [], []
    out = ws.run_at_login(lambda c: calls.append(c), lambda name: None, log=logged.append,
                          settings_path=ws.settings_file(env), env=env, wait=lambda ready: ready())
    assert out == 'no-drive' and calls == [] and 'did not appear' in logged[0]


def test_a_pc_that_does_not_share_loads_straight_away(tmp_path):
    env = env_for(tmp_path, shares=False)
    choose(env)
    calls = []
    out = ws.run_at_login(lambda c: calls.append((c['boot_id'], c['slot'])) or {'success': False}, lambda n: None,
                          log=lambda m: None, settings_path=ws.settings_file(env), env=env,
                          wait=lambda ready: pytest.fail('should not wait for Google Drive'))
    assert out == 'failed' and calls == [('boot1', 1)]


def test_login_waits_for_drive_when_the_choice_came_from_drive_even_without_a_note(tmp_path):
    env = env_for(tmp_path, shares=False)
    ws.save_settings({'startup': {'boot_id': 'boot1', 'slot': 1, 'shared': True}}, ws.settings_file(env))
    waited, calls = [], []
    out = ws.run_at_login(lambda c: calls.append(c), lambda n: None, log=lambda m: None,
                          settings_path=ws.settings_file(env), env=env, wait=lambda ready: waited.append(1) or ready())
    assert out == 'no-drive' and waited == [1] and calls == []


def test_drive_files_that_cannot_be_read_yet_keep_the_login_waiting(tmp_path):
    drive = tmp_path / 'ROCCAT Manager Data'
    (drive / 'profiles').mkdir(parents=True)
    find = lambda name: drive
    (drive / 'profiles' / 'stored.json').write_text('{"profiles": [')      # listed, not downloaded yet
    assert ws.shared_profiles_ready(find, env={}) is False
    (drive / 'profiles' / 'stored.json').write_text('{"profiles": []}')
    (drive / 'profiles' / 'slots.json').write_text('')
    assert ws.shared_profiles_ready(find, env={}) is False
    (drive / 'profiles' / 'slots.json').write_text('{}')
    assert ws.shared_profiles_ready(find, env={}) is True


def test_a_crash_while_loading_is_logged_not_shown(tmp_path):
    env = env_for(tmp_path, shares=False)
    choose(env)
    logged = []

    def boom(choice):
        raise ValueError('Expecting value: line 1 column 1')
    out = ws.run_at_login(boom, lambda n: None, log=logged.append, settings_path=ws.settings_file(env), env=env)
    assert out == 'failed' and 'ValueError' in logged[0]


def test_task_manager_switching_it_off_is_noticed_and_choosing_again_turns_it_back_on(reg, tmp_path):
    exe, local, settings = make_exe(tmp_path / 'a.exe'), tmp_path / 'l' / 'ROCCAT Manager.exe', tmp_path / 's.json'
    ws.enable({'boot_id': 'boot1', 'slot': 1}, exe, reg, settings, local)
    assert ws.turned_off_in_windows(reg) is False
    reg.values[ws.APPROVED_KEY] = {ws.RUN_VALUE: b'\x03\x00\x00\x00' + bytes(8)}    # what Task Manager writes
    assert ws.turned_off_in_windows(reg) is True and ws.run_entry(reg) is not None
    ws.enable({'boot_id': 'boot1', 'slot': 1}, exe, reg, settings, local)
    assert ws.turned_off_in_windows(reg) is False
    reg.values[ws.APPROVED_KEY][ws.RUN_VALUE] = b'\x02' + bytes(11)                  # switched on again there
    assert ws.turned_off_in_windows(reg) is False


def test_wait_for_gives_up_after_the_timeout():
    t = [0.0]
    ok = ws.wait_for(lambda: False, timeout=10, interval=3, sleep=lambda s: t.__setitem__(0, t[0] + s),
                     clock=lambda: t[0])
    assert ok is False and 10 <= t[0] <= 13


def test_the_note_name_matches_the_server():
    spec = importlib.util.spec_from_file_location('roccat_server_ws', os.path.join(APP, 'server.py'))
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    assert ws.MOVED_NOTE == srv.MOVED_NOTE and ws.SHARED_DATA_NAME == srv.SHARED_DATA_NAME


# ── the server side: what is written to the mouse at login, and the setting ───────
@pytest.fixture
def server(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('roccat_server_ws2', os.path.join(APP, 'server.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    prof = tmp_path / 'drive' / 'profiles'
    prof.mkdir(parents=True)
    profiles = [{'id': 'gaming', 'name': 'Gaming', 'dpi': 1400, 'keybinds': {}, 'easy_shift': {}},
                {'id': 'cad', 'name': 'AutoCAD', 'dpi': 800, 'keybinds': {}, 'easy_shift': {}}]
    (prof / 'stored.json').write_text(json.dumps({'profiles': profiles}))
    (prof / 'slots.json').write_text(json.dumps({'boot1': ['gaming', None, None, None, None],
                                                 'boot2': ['cad', None, None, None, None]}))
    mod.DATA_HOW, mod.PROFILES_DIR = 'shared', prof
    mod.STORED_FILE, mod.SLOTS_FILE = prof / 'stored.json', prof / 'slots.json'
    mod.MOUSE_CONFIG_FILE = tmp_path / 'cfg' / 'mouse_config.json'
    mod.save_mouse_config({'transport': 'recording'})
    monkeypatch.setenv('APPDATA', str(tmp_path / 'AppData'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'LocalAppData'))
    mod.app.config['TESTING'] = True
    return mod


def test_login_writes_this_sides_main_profile_and_switches_to_it(server):
    before = server.SLOTS_FILE.read_text()
    r = server.load_startup_profile('boot2', 1, shared=True, sleep=lambda s: None)
    assert r['success'] and r['message'] == 'Pushed AutoCAD to slot 1' and r['attempts'] == 1
    assert r['switched_to'] == 0
    # review: the login run only reads - Drive may not have fetched the other side's changes yet
    assert server.SLOTS_FILE.read_text() == before and server.load_active_slot() is None


def test_push_to_mouse_still_remembers_the_active_slot(server):
    r = server.app.test_client().post('/api/push-slot', json={'boot_id': 'boot1', 'slot': 1}).get_json()
    assert r['success'] and r['active_slot'] == 0 and server.load_active_slot() == 0
    assert server.app.test_client().post('/api/push-slot', json={'boot_id': 'boot1', 'slot': 3}).status_code == 400


def test_a_choice_made_from_drive_never_falls_back_to_this_pcs_old_profiles(server):
    # review: a side whose own profiles were "not merged" has no note, so nothing else says it shares
    server.DATA_HOW = 'local'                                   # Google Drive not found at login
    jobs = []
    server.run_mouse_job = lambda fn: jobs.append(fn) or {'success': True}
    r = server.load_startup_profile('boot1', 1, shared=True, sleep=lambda s: None)
    assert r['success'] is False and 'not found' in r['skipped'] and jobs == []


def test_a_file_that_cannot_be_read_yet_is_retried_not_an_error_window(server):
    server.SLOTS_FILE.write_text('')                            # Drive still downloading it
    naps = []

    def drive_catches_up(s):
        naps.append(s)
        server.SLOTS_FILE.write_text(json.dumps({'boot1': ['gaming', None, None, None, None]}))
    r = server.load_startup_profile('boot1', 1, sleep=drive_catches_up)
    assert r['success'] and r['attempts'] == 2 and naps == [10]


def test_login_never_writes_the_built_in_examples(server, tmp_path):
    for f in ('stored.json', 'slots.json'):
        (server.PROFILES_DIR / f).unlink()                    # Google Drive hasn't delivered them yet
    jobs = []
    server.run_mouse_job = lambda fn: jobs.append(fn) or {'success': True}
    r = server.load_startup_profile('boot1', 1, sleep=lambda s: None)
    assert r['success'] is False and 'no profiles' in r['skipped'] and jobs == []


def test_login_tries_again_while_the_mouse_is_waking_up(server):
    answers = iter([{'success': False, 'error': 'receiver not found'}, {'success': True, 'message': 'ok'}])
    server.run_mouse_job = lambda fn: next(answers)
    naps = []
    r = server.load_startup_profile('boot1', 1, pause=10, sleep=naps.append)
    assert r['success'] and r['attempts'] == 2 and naps == [10]


def test_login_does_not_retry_an_empty_slot(server):
    naps = []
    r = server.load_startup_profile('boot1', 4, sleep=naps.append)
    assert r['success'] is False and 'no profile assigned' in r['error'] and naps == []


def test_the_startup_setting_is_only_offered_in_the_windows_app(server):
    client = server.app.test_client()
    assert client.get('/api/this-pc').get_json()['supported'] is False      # tests run from source
    r = client.put('/api/this-pc', json={'startup': {'boot_id': 'boot1', 'slot': 1}})
    assert r.status_code == 400


def test_choosing_and_clearing_the_startup_profile(server, tmp_path):
    server.STARTUP_SUPPORTED, server._STARTUP_REG = True, FakeReg()
    exe = make_exe(tmp_path / 'G' / 'ROCCAT Manager.exe')
    server._app_exe = lambda: str(exe)
    client = server.app.test_client()
    stale = {'X-Profiles-Source': 'none'}                      # not profile data: a stale page may change it
    r = client.put('/api/this-pc', json={'startup': {'boot_id': 'boot2', 'slot': 1}}, headers=stale).get_json()
    assert r['enabled'] is True and r['startup'] == {'boot_id': 'boot2', 'slot': 1, 'shared': True}
    assert r['turned_off_in_windows'] is False
    server._STARTUP_REG.values[ws.APPROVED_KEY] = {ws.RUN_VALUE: b'\x03' + bytes(11)}
    assert client.get('/api/this-pc').get_json()['turned_off_in_windows'] is True
    assert ws.installed_exe().exists()
    assert client.put('/api/this-pc', json={'startup': {'boot_id': 'boot2', 'slot': 9}}).status_code == 400
    r = client.put('/api/this-pc', json={'startup': None}).get_json()
    assert r['enabled'] is False and r['startup'] is None
    assert not (server.PROFILES_DIR / ws.SETTINGS_NAME).exists(), "the choice is per PC, never in Drive"
