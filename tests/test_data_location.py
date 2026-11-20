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


# ── moving this PC's profiles into the shared folder ────────────────────────────
def test_moves_local_profiles_into_an_empty_shared_folder(server, tmp_path):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming', 'Work'], {'mouse_config.json': {'transport': 'direct'}})
    assert server.migrate_local_profiles(shared, local) is True
    assert names_in(shared) == ['Gaming', 'Work']
    assert json.loads((shared / 'mouse_config.json').read_text())['transport'] == 'direct'
    assert names_in(local) == ['Gaming', 'Work'], "the local copy stays as a backup"


def test_replaces_defaults_the_other_side_seeded_and_keeps_them(server, tmp_path):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Gaming'])
    write_profiles(shared, ['Default 01'])
    (shared / server.SEEDED_MARKER).write_text('defaults')
    assert server.migrate_local_profiles(shared, local, stamp='T') is True
    assert names_in(shared) == ['Gaming']
    assert names_in(shared / 'defaults-backup-T') == ['Default 01']
    assert not (shared / server.SEEDED_MARKER).exists()


def test_never_overwrites_real_shared_profiles(server, tmp_path):
    local, shared = tmp_path / 'appdata' / 'profiles', tmp_path / 'drive' / 'profiles'
    write_profiles(local, ['Old local'])
    write_profiles(shared, ['Edited on the other side'])
    assert server.migrate_local_profiles(shared, local) is False
    assert names_in(shared) == ['Edited on the other side']


def test_nothing_to_move_without_local_profiles(server, tmp_path):
    shared = tmp_path / 'drive' / 'profiles'
    assert server.migrate_local_profiles(shared, tmp_path / 'appdata' / 'profiles') is False
    assert not shared.exists()


def test_same_folder_is_not_copied_onto_itself(server, tmp_path):
    folder = tmp_path / 'profiles'
    write_profiles(folder, ['Gaming'])
    assert server.migrate_local_profiles(folder, folder) is False
    assert names_in(folder) == ['Gaming']


# ── the "only defaults so far" marker ────────────────────────────────────────────
def test_seeding_a_shared_folder_marks_it_and_a_real_save_clears_it(server, tmp_path):
    prof = tmp_path / 'drive' / 'profiles'
    server.DATA_HOW = 'shared'
    server.PROFILES_DIR = prof
    server.STORED_FILE, server.SLOTS_FILE = prof / 'stored.json', prof / 'slots.json'
    server.MOUSE_CONFIG_FILE = prof / 'mouse_config.json'
    server.seed_profiles()
    assert (prof / 'stored.json').exists() and (prof / server.SEEDED_MARKER).exists()
    server.save_mouse_config({'transport': 'direct'})          # settings alone are not profile data
    assert (prof / server.SEEDED_MARKER).exists()
    server.save_stored(server.load_stored())
    assert not (prof / server.SEEDED_MARKER).exists()


def test_seeding_this_pc_only_folder_is_not_marked(server, tmp_path):
    prof = tmp_path / 'appdata' / 'profiles'
    server.DATA_HOW = 'local'
    server.PROFILES_DIR = prof
    server.seed_profiles()
    assert (prof / 'stored.json').exists() and not (prof / server.SEEDED_MARKER).exists()


def test_data_location_endpoint(server, tmp_path):
    server.DATA_HOW, server.PROFILES_DIR, server.MIGRATED = 'shared', tmp_path / 'p', True
    r = server.app.test_client().get('/api/data-location').get_json()
    assert r == {'success': True, 'path': str(tmp_path / 'p'), 'how': 'shared', 'shared': True, 'migrated': True}
