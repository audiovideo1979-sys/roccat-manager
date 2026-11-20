"""Where profiles live: the Google Drive folder both dual-boot sides share, found without ROCCAT_MANAGER_DATA,
and the one-time move of this PC's own profiles into it (no hardware)."""
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'ROCCAT_Manager')


@pytest.fixture
def server():
    spec = importlib.util.spec_from_file_location('roccat_server_dl', os.path.join(APP, 'server.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.app.config['TESTING'] = True
    return mod


@pytest.fixture
def drivefolders():
    if APP not in sys.path:
        sys.path.insert(0, APP)
    import drivefolders as mod
    return mod


def write_profiles(folder, names, extra=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'stored.json').write_text(json.dumps({'profiles': [{'id': n, 'name': n} for n in names]}))
    (folder / 'slots.json').write_text(json.dumps({'boot1': names[:5] + [None] * (5 - len(names[:5]))}))
    for fn, data in (extra or {}).items():
        (folder / fn).write_text(json.dumps(data))


def names_in(folder):
    return [p['name'] for p in json.loads((folder / 'stored.json').read_text())['profiles']]


# ── choosing the folder ───────────────────────────────────────────────────────
def test_env_var_wins_and_is_created(server, tmp_path):
    target = tmp_path / 'from-env'
    d, how = server.resolve_data_dir(env={'ROCCAT_MANAGER_DATA': str(target)}, candidates=[tmp_path],
                                     local=tmp_path / 'local')
    assert (d, how) == (target, 'env') and target.is_dir()


def test_existing_shared_folder_is_used_before_this_pc(server, tmp_path):
    missing, shared = tmp_path / 'not-here', tmp_path / 'ROCCAT Manager Data'
    shared.mkdir()
    d, how = server.resolve_data_dir(env={}, candidates=[missing, shared], local=tmp_path / 'local')
    assert (d, how) == (shared, 'shared')
    assert not missing.exists(), "a missing shared folder is never created"


def test_falls_back_to_this_pc_when_drive_is_not_there(server, tmp_path):
    d, how = server.resolve_data_dir(env={}, candidates=[tmp_path / 'nope'], local=tmp_path / 'local')
    assert (d, how) == (tmp_path / 'local', 'local') and d.is_dir()


def test_unusable_env_var_falls_through(server, tmp_path):
    blocker = tmp_path / 'a-file'
    blocker.write_text('x')
    d, how = server.resolve_data_dir(env={'ROCCAT_MANAGER_DATA': str(blocker / 'sub')}, candidates=[],
                                     local=tmp_path / 'local')
    assert how == 'local'


def test_exe_in_drive_finds_its_sibling_data_folder(server, tmp_path):
    exe = tmp_path / 'ROCCAT_Manager_Full' / 'ROCCAT Manager.exe'
    first = next(server.shared_data_candidates(exe_path=str(exe)))
    assert first == tmp_path / 'ROCCAT Manager Data'


def test_drivefolders_finds_my_drive_under_home(drivefolders, tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setattr(drivefolders, 'drive_roots', lambda: [])   # on the PC, don't find the real G:
    assert drivefolders.find('ROCCAT_Manager_Full') is None
    app = tmp_path / 'My Drive' / 'Claude Folder' / 'Projects' / 'Personal' / 'ROCCAT_Manager_Full'
    app.mkdir(parents=True)
    assert drivefolders.find('ROCCAT_Manager_Full') == app


# ── bringing this PC's profiles into the shared folder ─────────────────────────
@pytest.fixture
def seed(tmp_path):
    """Stand-in for the shipped defaults (the bundle's profiles folder)."""
    d = tmp_path / 'seed'
    write_profiles(d, ['Main Test', 'Grounded', 'WWM'])
    return d


def copy_of(folder, src):
    folder.mkdir(parents=True, exist_ok=True)
    for f in src.glob('*.json'):
        (folder / f.name).write_text(f.read_text())


def test_copies_this_pcs_profiles_into_an_empty_shared_folder(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming', 'Work'], {'mouse_config.json': {'transport': 'direct'}})
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    assert names_in(shared) == ['Gaming', 'Work']
    assert json.loads((shared / 'mouse_config.json').read_text())['transport'] == 'direct'
    assert names_in(local) == ['Gaming', 'Work'], "the local copy stays as a backup"
    assert (local / server.MOVED_NOTE).exists()


def test_a_pc_with_only_the_defaults_brings_nothing(server, tmp_path, seed):
    # review bug 1: the work side once ran an older build, so %APPDATA% holds the seeded defaults. They must not
    # land in the shared folder, where they would later block the personal side's real profiles.
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    copy_of(local, seed)
    assert server.migrate_local_profiles(shared, local, seed) is None
    assert not shared.exists()
    assert (local / server.MOVED_NOTE).exists(), "this PC is marked as connected"


def test_a_profile_switch_on_the_other_side_first_does_not_block_the_copy(server, tmp_path, seed):
    # review bug 2: the work side runs first on the defaults and switches profiles, which writes slots.json
    # (active_slot). The personal side's real profiles must still come in afterwards.
    shared = tmp_path / 'drive' / 'profiles'
    server.DATA_HOW, server.SEED_DIR, server.PROFILES_DIR = 'shared', seed, shared
    server.STORED_FILE, server.SLOTS_FILE = shared / 'stored.json', shared / 'slots.json'
    assert [p['name'] for p in server.load_stored()] == ['Main Test', 'Grounded', 'WWM']   # read from the bundle
    server.save_active_slot(2)
    assert not shared.exists(), "no profiles folder is started in Drive just for the active slot"
    local = tmp_path / 'appdata' / 'profiles'
    write_profiles(local, ['Gaming'])
    assert server.migrate_local_profiles(shared, local, seed, stamp='T') == 'copied'
    assert names_in(shared) == ['Gaming']


def test_an_edit_of_the_defaults_on_the_other_side_first_does_not_shut_out_real_profiles(server, tmp_path, seed):
    # second review: the work side deletes one built-in example before the personal side's first run
    shared = tmp_path / 'drive' / 'profiles'
    point_at(server, shared, 'shared', seed)
    server.save_stored(server.load_stored()[1:])
    server.save_stored(server.load_stored())                    # the mark survives later saves
    assert json.loads((shared / 'stored.json').read_text())[server.FROM_DEFAULTS] is True
    local = tmp_path / 'appdata' / 'profiles'
    write_profiles(local, ['Gaming'])
    assert server.migrate_local_profiles(shared, local, seed, stamp='T') == 'copied'
    assert names_in(shared) == ['Gaming']
    assert names_in(shared / 'replaced-T') == ['Grounded', 'WWM'], "the other side's edit is kept"
    server.save_stored(server.load_stored())                    # real profiles are never marked
    assert server.FROM_DEFAULTS not in json.loads((shared / 'stored.json').read_text())


def test_slot_assignments_count_as_this_pcs_own(server, tmp_path, seed):
    shared = tmp_path / 'drive' / 'profiles'
    for name, active, reorder, expected in (('a', 3, False, None), ('b', 3, True, 'copied')):
        local = tmp_path / name / 'profiles'
        copy_of(local, seed)
        slots = json.loads((local / 'slots.json').read_text())
        slots['active_slot'] = active                     # a remembered active slot is not an edit
        if reorder:
            slots['boot1'] = list(reversed(slots['boot1']))
        (local / 'slots.json').write_text(json.dumps(slots))
        assert server.migrate_local_profiles(shared, local, seed) == expected, name


def test_a_slot_change_on_this_pc_after_the_move_is_reported(server, tmp_path, seed):
    # third review: the old pinned app reassigns a slot (slots.json only) after the move
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming', 'Work'])
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    slots = json.loads((local / 'slots.json').read_text())
    slots['active_slot'] = 4                                    # a plain profile switch: not an edit
    (local / 'slots.json').write_text(json.dumps(slots))
    assert server.migrate_local_profiles(shared, local, seed) is None
    slots['boot1'][2] = 'Work'                                  # a real slot assignment
    (local / 'slots.json').write_text(json.dumps(slots))
    assert server.migrate_local_profiles(shared, local, seed) == 'not-merged'
    assert json.loads((shared / 'slots.json').read_text())['boot1'][2] is None


def test_profiles_displaced_by_an_examples_copy_are_brought_back(server, tmp_path, seed):
    # third review: this PC copied its set in, then Google Drive kept the other side's copy that was started
    # from the examples (an edit made there before the upload arrived)
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    (shared / 'stored.json').write_text(json.dumps({'profiles': [{'id': 'wwm', 'name': 'WWM'}],
                                                     server.FROM_DEFAULTS: True}))
    assert server.migrate_local_profiles(shared, local, seed, stamp='T') == 'copied'
    assert names_in(shared) == ['Gaming'] and names_in(shared / 'replaced-T') == ['WWM']


def test_no_second_copy_while_drive_has_not_shown_the_shared_file_yet(server, tmp_path, seed):
    # fourth review: after this PC's set was brought over, the shared stored.json is briefly not there
    # (Drive still catching up): copying the old local set in again would fork the profiles
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Old'])
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    (shared / 'stored.json').unlink()
    assert server.migrate_local_profiles(shared, local, seed) is None
    assert not (shared / 'stored.json').exists()


def test_a_note_without_a_fingerprint_gets_one(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming', 'Work'])
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    (local / server.MOVED_NOTE).write_text('moved\n')         # as written before the fingerprint existed
    assert server.migrate_local_profiles(shared, local, seed) is None
    assert 'state: ' in (local / server.MOVED_NOTE).read_text()
    slots = json.loads((local / 'slots.json').read_text())
    slots['boot1'][2] = 'Work'
    (local / 'slots.json').write_text(json.dumps(slots))
    assert server.migrate_local_profiles(shared, local, seed) == 'not-merged'


def test_a_note_in_another_text_encoding_does_not_stop_the_app(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    point_at(server, shared, 'shared', seed)
    assert server.prepare_profiles(local_profiles=local) == 'copied'
    state = server._note_state(local / server.MOVED_NOTE)
    (local / server.MOVED_NOTE).write_bytes(('C:\\Users\\Jos\xe9\\My Drive\n\nstate: %s\n' % state).encode('cp1252'))
    assert server.prepare_profiles(local_profiles=local) is None


def test_a_page_still_on_the_examples_cannot_overwrite_profiles_that_arrived(server, tmp_path, seed):
    # third review: the app opened before Google Drive delivered this side's profiles (the page shows the
    # examples, which share ids with the real set); Drive delivers; the next edit must not overwrite them
    shared = tmp_path / 'drive' / 'profiles'
    point_at(server, shared, 'shared', seed)
    client = server.app.test_client()
    page = client.get('/api/stored').get_json()
    assert page['source'] == 'none'                             # the bundled examples, nothing saved yet
    write_profiles(shared, ['Main Test'])                       # Google Drive delivers the real set
    stale = {'X-Profiles-Source': page['source']}
    r = client.put('/api/stored/Main Test', json={'name': 'Main Test', 'dpi': 800}, headers=stale)
    assert r.status_code == 409 and r.get_json()['reload'] is True
    assert client.delete('/api/stored/Main Test', headers=stale).status_code == 409
    assert names_in(shared) == ['Main Test'] and 'dpi' not in json.loads((shared / 'stored.json').read_text())['profiles'][0]
    assert client.post('/api/release-modifiers', headers=stale).status_code != 409, "the keyboard fix always works"
    fresh = client.get('/api/stored').get_json()                # after the reload
    assert fresh['source'] == 'saved'
    r = client.put('/api/stored/Main Test', json={'name': 'Main Test', 'dpi': 800},
                   headers={'X-Profiles-Source': fresh['source']})
    assert r.status_code == 200


def test_the_examples_page_can_save_while_nothing_arrived(server, tmp_path, seed):
    shared = tmp_path / 'drive' / 'profiles'
    point_at(server, shared, 'shared', seed)
    client = server.app.test_client()
    source = client.get('/api/stored').get_json()['source']
    for pid in ('WWM', 'Grounded'):
        r = client.delete('/api/stored/' + pid, headers={'X-Profiles-Source': source})
        assert r.status_code == 200
        source = r.headers['X-Profiles-Source']                 # the page follows its own first save
    assert source == 'examples' and names_in(shared) == ['Main Test']


def test_an_examples_set_arriving_from_the_other_side_is_not_overwritten_either(server, tmp_path, seed):
    # fourth review: the other side saved a set started from the examples; this page still shows the bundle
    shared = tmp_path / 'drive' / 'profiles'
    point_at(server, shared, 'shared', seed)
    client = server.app.test_client()
    source = client.get('/api/stored').get_json()['source']
    shared.mkdir(parents=True)
    (shared / 'stored.json').write_text(json.dumps({'profiles': [{'id': 'Main Test', 'name': 'Main Test',
                                                                   'color': '#00ff00'}], server.FROM_DEFAULTS: True}))
    r = client.put('/api/stored/Main Test', json={'name': 'Main Test', 'color': '#7F77DD'},
                   headers={'X-Profiles-Source': source})
    assert r.status_code == 409
    assert json.loads((shared / 'stored.json').read_text())['profiles'][0]['color'] == '#00ff00'


def test_an_unreadable_shared_file_is_reported(server, tmp_path, seed):
    shared = tmp_path / 'drive' / 'profiles'
    point_at(server, shared, 'shared', seed)
    shared.mkdir(parents=True)
    (shared / 'stored.json').write_text('{"profiles": [')        # truncated / not downloaded
    r = server.app.test_client().get('/api/data-location').get_json()
    assert r['has_profiles'] is True and r['readable'] is False


def test_a_session_while_drive_was_off_never_replaces_the_shared_profiles(server, tmp_path, seed):
    # both boots built their set from the examples (marked from_defaults); later one boot runs with Google
    # Drive off, falls back to this PC's folder, and something is edited there
    shared, local = tmp_path / 'drive' / 'profiles', tmp_path / 'appdata' / 'profiles'
    point_at(server, shared, 'shared', seed)
    assert server.prepare_profiles(local_profiles=local) is None      # connected: nothing of its own to bring
    server.save_stored(server.load_stored() + [{'id': 'months', 'name': 'Months of work'}])
    write_profiles(local, ['Edited while Drive was off'])
    note_time = (local / server.MOVED_NOTE).stat().st_mtime
    os.utime(local / 'stored.json', (note_time + 60, note_time + 60))
    assert server.prepare_profiles(local_profiles=local) == 'not-merged'
    assert 'Months of work' in [p['name'] for p in server.load_stored()]


def test_defaults_already_in_the_shared_folder_are_replaced_and_kept(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    copy_of(shared, seed)                      # e.g. seeded there by the 2026-09 build through ROCCAT_MANAGER_DATA
    assert server.migrate_local_profiles(shared, local, seed, stamp='T') == 'copied'
    assert names_in(shared) == ['Gaming']
    assert names_in(shared / 'replaced-T') == ['Main Test', 'Grounded', 'WWM']


def test_real_shared_profiles_win_and_the_skip_is_reported(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Old local'])
    write_profiles(shared, ['Edited on the other side'])
    assert server.migrate_local_profiles(shared, local, seed) == 'not-merged'
    assert names_in(shared) == ['Edited on the other side']
    assert not (local / server.MOVED_NOTE).exists()


def test_the_same_profiles_on_both_sides_is_not_reported(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    write_profiles(shared, ['Gaming'])          # copied by hand with the old xcopy instructions
    assert server.migrate_local_profiles(shared, local, seed) is None
    write_profiles(shared, ['Gaming', 'Edited later'])
    assert server.migrate_local_profiles(shared, local, seed) is None, "later edits are not a skipped merge"


def test_profiles_are_brought_over_only_once(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    write_profiles(shared, ['Gaming', 'Added on the work side'])
    assert server.migrate_local_profiles(shared, local, seed) is None
    assert names_in(shared) == ['Gaming', 'Added on the work side']


def test_edits_on_this_pc_after_the_move_are_reported(server, tmp_path, seed):
    # e.g. the old exe still pinned to the taskbar, or a session while Google Drive was off
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    write_profiles(local, ['Gaming', 'Made in the old app'])
    note_time = (local / server.MOVED_NOTE).stat().st_mtime
    os.utime(local / 'stored.json', (note_time + 60, note_time + 60))
    assert server.migrate_local_profiles(shared, local, seed) == 'not-merged'
    assert names_in(shared) == ['Gaming']


def test_shared_settings_stay_when_this_pc_has_none(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    shared.mkdir(parents=True)
    (shared / 'mouse_config.json').write_text(json.dumps({'transport': 'frida'}))
    assert server.migrate_local_profiles(shared, local, seed) == 'copied'
    assert json.loads((shared / 'mouse_config.json').read_text())['transport'] == 'frida'


def test_stored_json_is_copied_last(server, tmp_path, seed, monkeypatch):
    # stored.json is what makes the shared folder count as real profiles, so a copy cut short is redone
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'], {'mouse_config.json': {'transport': 'direct'}, 'zz.json': {}})
    order, real_copy2 = [], server.shutil.copy2
    monkeypatch.setattr(server.shutil, 'copy2', lambda a, b: (order.append(os.path.basename(b)), real_copy2(a, b)))
    server.migrate_local_profiles(shared, local, seed)
    assert order[-1] == 'stored.json' and len(order) == 4


def test_an_unreadable_local_file_is_reported_not_copied(server, tmp_path, seed):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    local.mkdir(parents=True)
    (local / 'stored.json').write_text('{ not json')
    assert server.migrate_local_profiles(shared, local, seed) == 'not-merged'
    assert not (shared / 'stored.json').exists()


def test_nothing_to_move_without_local_profiles(server, tmp_path, seed):
    shared = tmp_path / 'drive' / 'profiles'
    assert server.migrate_local_profiles(shared, tmp_path / 'appdata' / 'profiles', seed) is None
    assert not shared.exists()


def test_same_folder_is_not_copied_onto_itself(server, tmp_path, seed):
    folder = tmp_path / 'profiles'
    write_profiles(folder, ['Gaming'])
    assert server.migrate_local_profiles(folder, folder, seed) is None
    assert names_in(folder) == ['Gaming']


# ── startup and the defaults ──────────────────────────────────────────────────────
def point_at(server, prof, how, seed):
    server.DATA_HOW, server.SEED_DIR, server.PROFILES_DIR = how, seed, prof
    server.STORED_FILE, server.SLOTS_FILE = prof / 'stored.json', prof / 'slots.json'
    server.MOUSE_CONFIG_FILE = prof / 'mouse_config.json'


def test_startup_never_writes_the_defaults_into_the_shared_folder(server, tmp_path, seed):
    prof = tmp_path / 'drive' / 'profiles'
    point_at(server, prof, 'shared', seed)
    assert server.prepare_profiles(local_profiles=tmp_path / 'appdata' / 'profiles') is None
    assert not (prof / 'stored.json').exists() and not (prof / 'slots.json').exists()
    assert [p['name'] for p in server.load_stored()] == ['Main Test', 'Grounded', 'WWM']
    server.save_stored(server.load_stored()[:1])                 # the first real save writes the file
    assert names_in(prof) == ['Main Test']


def test_a_failed_copy_is_reported(server, tmp_path, seed, monkeypatch):
    prof, local = tmp_path / 'drive' / 'profiles', tmp_path / 'appdata' / 'profiles'
    write_profiles(local, ['Gaming'])
    point_at(server, prof, 'shared', seed)

    def full_disk(a, b):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(server.shutil, 'copy2', full_disk)
    assert server.prepare_profiles(local_profiles=local) == 'copy-failed'
    monkeypatch.undo()
    assert server.prepare_profiles(local_profiles=local) == 'copied', "the next launch tries again"


def test_startup_brings_this_pcs_profiles_in(server, tmp_path, seed):
    prof, local = tmp_path / 'drive' / 'profiles', tmp_path / 'appdata' / 'profiles'
    write_profiles(local, ['Gaming'])
    point_at(server, prof, 'env', seed)
    assert server.prepare_profiles(local_profiles=local) == 'copied'
    assert [p['name'] for p in server.load_stored()] == ['Gaming']


def test_startup_seeds_a_this_pc_only_folder(server, tmp_path, seed):
    prof = tmp_path / 'appdata' / 'profiles'
    point_at(server, prof, 'local', seed)
    assert server.prepare_profiles() is None
    assert names_in(prof) == ['Main Test', 'Grounded', 'WWM']


def test_data_location_endpoint(server, tmp_path):
    server.DATA_HOW, server.PROFILES_DIR, server.MIGRATION = 'shared', tmp_path / 'p', 'not-merged'
    server.STORED_FILE = tmp_path / 'p' / 'stored.json'
    r = server.app.test_client().get('/api/data-location').get_json()
    assert r['success'] and r['path'] == str(tmp_path / 'p') and r['how'] == 'shared' and r['shared'] is True
    assert r['migration'] == 'not-merged' and r['local_path'].endswith('profiles')
    assert r['source'] == 'none' and r['readable'] is True
    assert r['has_profiles'] is False
    write_profiles(tmp_path / 'p', ['Gaming'])
    assert server.app.test_client().get('/api/data-location').get_json()['has_profiles'] is True


def test_a_pc_that_never_shared_just_says_saved_on_this_pc(server, tmp_path, monkeypatch):
    # a friend's PC (no Google Drive folder) is not warned about Drive; a PC that used to share is
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    server.DATA_HOW, server.PROFILES_DIR = 'local', tmp_path / 'appdata' / 'ROCCAT Manager' / 'profiles'
    server.STORED_FILE = server.PROFILES_DIR / 'stored.json'
    client = server.app.test_client()
    assert client.get('/api/data-location').get_json()['was_shared'] is False
    server.PROFILES_DIR.mkdir(parents=True)
    (server.PROFILES_DIR / server.MOVED_NOTE).write_text('state: x\n')
    assert client.get('/api/data-location').get_json()['was_shared'] is True
