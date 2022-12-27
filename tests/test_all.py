import builtins
import io
from pathlib import Path

import fsync
import tests


def test__list_remote_empty(get_config_empty, get_ftp_session):
    # empty target
    ret = fsync._list_remote(
        get_config_empty,
        get_ftp_session
    )

    assert ret == {}


def test__list_remote_small(get_config_small, get_ftp_session_small):
    # small target
    expected = tests.test_harness.target_small_sample_dataset

    ret = fsync._list_remote(
        get_config_small,
        get_ftp_session_small
    )

    assert ret == expected


def test__to_list_empty(get_config_empty):
    # empty target
    target_paths = {}

    ret = fsync._to_list(get_config_empty, target_paths)

    assert ret == []


def test__to_list_small(get_config_small):
    # small target
    target_paths = tests.test_harness.target_small_sample_dataset
    expected = tests.test_harness.target_small_sample_dataset_converted

    ret = fsync._to_list(get_config_small, target_paths)

    assert ret == expected


def test__calculate_delta_empty_empty():
    # empty source
    # empty target

    source_paths = []
    target_paths = []
    expected_add = []
    expected_remove = []

    add, remove = fsync._calculate_delta(
        source_paths,
        target_paths
    )

    assert add == expected_add
    assert remove == expected_remove


def test__calculate_delta_small_empty():
    # small source
    # empty target

    source_paths = tests.test_harness.target_small_sample_dataset_converted
    target_paths = []
    expected_add = tests.test_harness.calculate_delta_add_small_sample_dataset
    expected_remove = []

    add, remove = fsync._calculate_delta(
        source_paths,
        target_paths
    )

    assert add == expected_add
    assert remove == expected_remove


def test__calculate_delta_small_small():
    # small source
    # small target

    source_paths = tests.test_harness.target_small_sample_dataset_converted
    target_paths = tests.test_harness.target_small_sample_dataset_converted

    expected_add = []
    expected_remove = []

    add, remove = fsync._calculate_delta(
        source_paths,
        target_paths
    )

    assert add == expected_add
    assert remove == expected_remove


def test__calculate_delta_empty_small(monkeypatch):
    # empty source
    # small target

    source_paths = []
    target_paths = tests.test_harness.target_small_sample_dataset_converted
    expected_add = []
    expected_remove = tests.test_harness.\
        calculate_delta_remove_small_sample_dataset

    # monkeypatch the `input()` function, so that it returns "Any Key".
    # This simulates the user entering "Any Key" on the command line.
    monkeypatch.setattr('builtins.input', lambda _: 'Any Key')

    add, remove = fsync._calculate_delta(
        source_paths,
        target_paths
    )

    assert add == expected_add
    assert remove == expected_remove


def test__calculate_delta_medium_small(monkeypatch):
    # medium source
    # small target

    source_paths = tests.test_harness.source_medium_sample_dataset
    target_paths = tests.test_harness.target_small_sample_dataset_converted
    expected_add = tests.test_harness.calculate_delta_expected_add_dataset
    expected_remove = tests.test_harness.\
        calculate_delta_expected_remove_dataset

    # monkeypatch the `input()` function, so that it returns "Any Key".
    # This simulates the user entering "Any Key" on the command line.
    monkeypatch.setattr('builtins.input', lambda _: 'Any Key')

    add, remove = fsync._calculate_delta(
        source_paths,
        target_paths
    )

    assert add == expected_add
    assert remove == expected_remove


def test__sync_delete_empty_small(
        monkeypatch,
        get_config_empty,
        get_ftp_session
):
    # empty source
    # small target

    remove = tests.test_harness.calculate_delta_remove_small_sample_dataset

    monkeypatch.setattr(get_ftp_session, 'delete', lambda _: True)
    monkeypatch.setattr(get_ftp_session, 'rmd', lambda _: True)

    ret = fsync._sync_delete(
        get_config_empty,
        get_ftp_session,
        remove
    )

    assert ret is True


def test__sync_add_small_dataset(
        monkeypatch,
        get_config_small,
        get_ftp_session
):
    # small source
    # empty target

    add = tests.test_harness.sync_add_small_dataset
    expected_bytes_transferred = 699993.0

    def mock_path_stat(*args):
        class StatObj(object):
            st_size = 99999
            st_mode = 33060  # chmod 0444

        return StatObj()

    monkeypatch.setattr(Path, 'stat', mock_path_stat)
    monkeypatch.setattr(get_ftp_session, 'mkd', lambda _: True)
    monkeypatch.setattr(get_ftp_session, 'storbinary', lambda p1, p2: True)

    def mock_open(name, mode):
        if name.startswith(f'{tests.source_root_dir}/{tests.small_sample}'):
            return io.BytesIO(b'testdata')
        else:
            return open(name, mode)

    monkeypatch.setattr(builtins, 'open', mock_open)

    ret = fsync._sync_add(
            get_config_small,
            get_ftp_session,
            get_config_small.source_directory,
            add
    )

    assert expected_bytes_transferred == ret
