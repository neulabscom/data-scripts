from __future__ import annotations

import os
import shutil
import pytest

from airflow.airflow import mkdir, remove_example_dags, replace_db, update_image
from airflow.airflow import parse_docker_compose

TESTING_DIR = [
    './test_dags',
    './test_logs',
    './test_plugins',
    './test_data'
]

TEST_FILE = './test_data/docker_compose_test.yaml'


@pytest.fixture(scope='session', autouse=True)
def cleanup(request):
    """Cleanup a testing directory once we are finished."""
    def remove_test_dir():
        for dir in TESTING_DIR:
            shutil.rmtree(dir)
    request.addfinalizer(remove_test_dir)


def test_directories_creation():
    for td in TESTING_DIR:
        mkdir(td)
        assert os.path.isdir(td)


def test_disable_example_dags():
    default_compose_file = 'tests/data/docker-compose.default.yaml'
    original_file_content = parse_docker_compose(default_compose_file)
    services = original_file_content['services']
    remove_example_dags(original_file_content, services, TEST_FILE)
    test_file = parse_docker_compose(TEST_FILE)
    for s in test_file['services']:
        _env = test_file['services'][s].get('environment', {})
        test_value = _env.get('AIRFLOW__CORE__LOAD_EXAMPLES', None)
        if test_value is not None:
            assert test_value == 'false'


def test_use_external_db():
    default_compose_file = 'tests/data/docker-compose.default.yaml'
    original_file_content = parse_docker_compose(default_compose_file)
    services = original_file_content['services']
    _secrets = {
        'DB_USER': 'user',
        'DB_PASSWORD': 'password',
        'DB_HOST': 'localhost'
    }
    db_conn = 'postgresql+psycopg2://' + \
        _secrets['DB_USER'] + ':' + \
        _secrets['DB_PASSWORD'] + '@' + _secrets['DB_HOST']
    replace_db(original_file_content, services, _secrets, TEST_FILE)
    test_file = parse_docker_compose(TEST_FILE)
    for s in test_file['services']:
        _env = test_file['services'][s].get('environment', {})
        if 'AIRFLOW__DATABASE__SQL_ALCHEMY_CONN' in _env:
            assert _env['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] == db_conn
        if 'AIRFLOW__CORE__SQL_ALCHEMY_CONN' in _env:
            assert _env['AIRFLOW__CORE__SQL_ALCHEMY_CONN'] == db_conn
        if 'AIRFLOW__CELERY__RESULT_BACKEND' in _env:
            assert _env['AIRFLOW__CELERY__RESULT_BACKEND'] == 'db' + db_conn
        assert 'postgres' not in test_file['services'][s].get('depends_on', {})


def test_usage_custom_docker_image():
    default_compose_file = 'tests/data/docker-compose.default.yaml'
    original_file_content = parse_docker_compose(default_compose_file)
    services = original_file_content['services']
    test_image = 'test_image:1.0.0'
    update_image(original_file_content, services, test_image, TEST_FILE)
    test_file = parse_docker_compose(TEST_FILE)
    for s in test_file['services']:
        assert test_file['services'][s]['image'] == test_image
