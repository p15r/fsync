import ftplib

import pytest

import fsync
import tests


small_sample_dataset = {
    f'{tests.target_root_dir}': [
        # first call to mlsd
        ('some_script.sh', {'type': 'file', 'size': 136}),
        ('some_dir', {'type': 'dir', 'size': 4096}),
    ],
    f'{tests.target_root_dir}/some_dir': [
        # second call to mlsd
        ('file1.bin', {'type': 'file', 'size': 3623374}),
        ('file2.bin', {'type': 'file', 'size': 2773582}),
        ('file3.bin', {'type': 'file', 'size': 3072718}),
        ('file4.bin', {'type': 'file', 'size': 4513102}),
        ('file5.bin', {'type': 'file', 'size': 57601005}),
    ]
}


@pytest.fixture
def get_config_empty():
    return fsync.Config(
            source_directory=f'{tests.source_root_dir}/sample_dataset_emtpy/',
            target_ip_address='192.168.1.2',
            target_directory=f'{tests.target_root_dir}'
    )


@pytest.fixture
def get_config_small():
    return fsync.Config(
            source_directory=(
                f'{tests.source_root_dir}/{tests.small_sample}/'
            ),
            target_ip_address='192.168.1.2',
            target_directory=f'{tests.target_root_dir}'
    )


@pytest.fixture
def get_ftp_session(monkeypatch):
    def mock_mlsd(path):
        return []

    ftp_session = ftplib.FTP()   # nosec
    monkeypatch.setattr(ftp_session, 'mlsd', mock_mlsd)
    return ftp_session


from unittest.mock import patch
@pytest.fixture
def get_ftp_session_small(monkeypatch):
    """
    `_list_remote()` is a recursive function that gets called multiple
    times, hence `side_effect` is required to return different results of
    `mlsd()` function.
    """
    from unittest.mock import MagicMock

    ftp_session = ftplib.FTP()   # nosec

    def mock_ftp_mlsd(path):
        for item in small_sample_dataset[path]:
            yield item

    mock = MagicMock(side_effect=mock_ftp_mlsd)

    monkeypatch.setattr(ftp_session, 'mlsd', mock)

    return ftp_session
