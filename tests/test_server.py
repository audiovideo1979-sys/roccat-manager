"""Flask endpoints on top of the recording transport (no hardware)."""
import importlib.util
import io
import json
import os
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_SRC = os.path.join(ROOT, 'ROCCAT_Manager', 'profiles')


@pytest.fixture
def server(tmp_path):
    spec = importlib.util.spec_from_file_location('roccat_server', os.path.join(ROOT, 'ROCCAT_Manager', 'server.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    prof = tmp_path / 'profiles'
    prof.mkdir()
    for fn in ('stored.json', 'slots.json'):
        shutil.copy(os.path.join(PROFILES_SRC, fn), prof / fn)
    mod.PROFILES_DIR = prof
    mod.STORED_FILE = prof / 'stored.json'
    mod.SLOTS_FILE = prof / 'slots.json'
    mod.MOUSE_CONFIG_FILE = prof / 'mouse_config.json'
    mod.save_mouse_config({'transport': 'recording'})
    mod.app.config['TESTING'] = True
    return mod


@pytest.fixture
def client(server):
    return server.app.test_client()


def test_status_and_config(client):
    r = client.get('/api/mouse/status').get_json()
    assert r['success'] and r['config']['transport'] == 'recording'
    r = client.put('/api/mouse/config', json={'transport': 'bogus'})
    assert r.status_code == 400
    r = client.put('/api/mouse/config', json={'transport': 'direct', 'activate_b5': 'slot', 'kill_swarm': True, 'preamble': True}).get_json()
    assert r['config']['transport'] == 'direct' and r['config']['activate_b5'] == 'slot'
    assert r['config']['kill_swarm'] is True and r['config']['preamble'] is True
    r = client.get('/api/actions').get_json()
    assert 'Play/Pause' in r['actions'] and 'PageUp' in r['keys']


def test_push_slot_uses_the_assigned_profile(client, server):
    slots = server.load_slots()['boot1']
    filled = [i for i, pid in enumerate(slots) if pid]
    assert filled, 'fixture slots.json has no assignments'
    slot1 = filled[0] + 1
    r = client.post('/api/push-slot', json={'boot_id': 'boot1', 'slot': slot1}).get_json()
    assert r['success'], r
    assert r['active_slot'] == slot1 - 1
    assert r['pushed'][0]['slot'] == slot1 - 1 and r['pushed'][0]['buttons'] is True
    assert r['unsupported'] == []
    log = client.get('/api/mouse/log').get_json()['log']
    assert any('buttons write page' in line for line in log)
    empty = [i for i, pid in enumerate(slots) if not pid]
    if empty:
        r = client.post('/api/push-slot', json={'boot_id': 'boot1', 'slot': empty[0] + 1})
        assert r.status_code == 400


def test_import_to_mouse_profile_and_all(client, server):
    slots = server.load_slots()['boot1']
    pid = next(p for p in slots if p)
    r = client.post('/api/import-to-mouse', json={'boot_id': 'boot1', 'profile_id': pid}).get_json()
    assert r['success'] and len(r['pushed']) >= 1
    r = client.post('/api/import-to-mouse', json={'boot_id': 'boot1'}).get_json()
    assert r['success'] and len(r['pushed']) == len([p for p in slots if p])
    assert r['active_slot'] == next(i for i, p in enumerate(slots) if p)
    r = client.post('/api/import-to-mouse', json={'boot_id': 'boot2'})
    assert r.status_code == 400
    r = client.post('/api/import-to-mouse', json={'boot_id': 'boot1', 'profile_id': 'nope'})
    assert r.status_code == 400


def test_switch_profile(client):
    r = client.post('/api/switch-profile/3').get_json()
    assert r['success'] and r['active_slot'] == 3
    assert client.post('/api/switch-profile/5').status_code == 400


def test_import_dat_creates_profiles_from_swarm_export(client, server):
    with open(os.path.join(PROFILES_SRC, 'Main Test.dat'), 'rb') as f:
        data = {'file': (io.BytesIO(f.read()), 'Main Test.dat'), 'name': 'Main Test from dat'}
    r = client.post('/api/import-dat', data=data, content_type='multipart/form-data').get_json()
    assert r['success'] and r['created'] == ['Main Test from dat'] and r['checksums_ok'] == [True]
    prof = next(p for p in server.load_stored() if p['name'] == 'Main Test from dat')
    assert prof['dpi'] == 950 and prof['keybinds']['dpi_up'] == 'Hotkey G'
    assert prof['easy_shift']['scroll_up'] == 'Volume Up'
    # second import with the same name updates instead of duplicating
    with open(os.path.join(PROFILES_SRC, 'Main Test.dat'), 'rb') as f:
        data = {'file': (io.BytesIO(f.read()), 'Main Test.dat'), 'name': 'Main Test from dat'}
    r = client.post('/api/import-dat', data=data, content_type='multipart/form-data').get_json()
    assert r['updated'] == ['Main Test from dat']


def test_lock_rejects_overlapping_jobs(client, server):
    assert server.MOUSE_LOCK.acquire()
    try:
        r = client.post('/api/switch-profile/0').get_json()
        assert not r['success'] and 'still running' in r['error']
    finally:
        server.MOUSE_LOCK.release()


def test_release_modifiers_endpoint(client):
    r = client.post('/api/release-modifiers').get_json()
    assert r['success'] is True   # off-Windows the helper no-ops but reports ok
    assert 'released' in r


def test_switch_and_push_release_stuck_modifiers(server, client, monkeypatch):
    calls = {'n': 0}
    monkeypatch.setattr(server, 'release_modifiers', lambda: calls.__setitem__('n', calls['n'] + 1) or {'ok': True, 'released': 0})
    r = client.post('/api/switch-profile/2').get_json()
    assert r['success']
    assert calls['n'] == 1, 'switch must release modifiers afterwards'
    slots = server.load_slots()['boot1']
    slot1 = next(i for i, pid in enumerate(slots) if pid) + 1
    client.post('/api/push-slot', json={'boot_id': 'boot1', 'slot': slot1})
    assert calls['n'] == 2, 'push must release modifiers afterwards'


def test_release_endpoint_does_not_take_the_mouse_lock(server, client):
    # the OS keyboard action must work even while a mouse op holds the lock
    assert server.MOUSE_LOCK.acquire()
    try:
        r = client.post('/api/release-modifiers').get_json()
        assert r['success'] is True
    finally:
        server.MOUSE_LOCK.release()


def test_active_slot_persists_so_a_fresh_launch_shows_it(server, client):
    # a fresh install has no remembered active slot -> the UI shows nothing highlighted
    r = client.get('/api/slots/boot1').get_json()
    assert r['active_slot'] is None
    # switching remembers it, and a later GET (i.e. a fresh app launch) reports it
    assert client.post('/api/switch-profile/2').get_json()['success']
    assert client.get('/api/slots/boot1').get_json()['active_slot'] == 2
    assert server.load_active_slot() == 2                       # persisted to disk
    # the mouse's active slot is one physical thing, independent of the boot map shown
    assert client.get('/api/slots/boot2').get_json()['active_slot'] == 2
    # a push moves it to the pushed slot
    slots = server.load_slots()['boot1']
    slot1 = next(i for i, pid in enumerate(slots) if pid) + 1
    client.post('/api/push-slot', json={'boot_id': 'boot1', 'slot': slot1})
    assert server.load_active_slot() == slot1 - 1


def test_read_pages_does_not_clobber_the_remembered_active_slot(server, client):
    assert client.post('/api/switch-profile/4').get_json()['success']
    assert server.load_active_slot() == 4
    # a diagnostic read returns no active_slot and must leave the remembered one alone
    r = client.post('/api/mouse/read-pages', json={'cmd': 'profile', 'flag': 1}).get_json()
    assert r['success']
    assert server.load_active_slot() == 4
