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


def test_a_profile_switch_on_the_other_side_first_does_not_block_the_copy(server, tmp_path, seed):
    # review bug 2: the work side runs first on the defaults and switches profiles, which writes slots.json
    # (active_slot). The personal side's real profiles must still come in afterwards.
    shared = tmp_path / 'drive' / 'profiles'
    server.DATA_HOW, server.SEED_DIR, server.PROFILES_DIR = 'shared', seed, shared
    server.STORED_FILE, server.SLOTS_FILE = shared / 'stored.json', shared / 'slots.json'
    assert [p['name'] for p in server.load_stored()] == ['Main Test', 'Grounded', 'WWM']   # read from the bundle
    server.save_active_slot(2)
    assert (shared / 'slots.json').exists() and not (shared / 'stored.json').exists()
    local = tmp_path / 'appdata' / 'profiles'
    write_profiles(local, ['Gaming'])
    assert server.migrate_local_profiles(shared, local, seed, stamp='T') == 'copied'
    assert names_in(shared) == ['Gaming']
    assert json.loads((shared / 'replaced-T' / 'slots.json').read_text())['active_slot'] == 2


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
    r = server.app.test_client().get('/api/data-location').get_json()
    assert r['success'] and r['path'] == str(tmp_path / 'p') and r['how'] == 'shared' and r['shared'] is True
    assert r['migration'] == 'not-merged' and r['local_path'].endswith('profiles')
