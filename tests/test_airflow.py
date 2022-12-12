from __future__ import annotations

import os

from airflow.airflow import mkdir
from airflow.airflow import parse_docker_compose
from airflow.airflow import replace_docker_compose_file

test_directories = [
    './test_dags',
    './test_logs',
    './test_plugins',
]


def _clean_dir_resources(dirs):
    for d in dirs:
        os.removedirs(d)


def _clean_file_resources(files):
    for f in files:
        os.remove(f)


def test_directories_creation():
    for td in test_directories:
        mkdir(td)
        assert os.path.isdir(td)
    _clean_dir_resources(test_directories)


def test_update_docker_compose():
    default_compose_file = 'tests/data/docker-compose.default.yaml'
    original_file_content = parse_docker_compose(default_compose_file)

    docker_compose_file = original_file_content

    docker_compose_file['x-airflow-common']['environment']['AIRFLOW__CORE__LOAD_EXAMPLES'] = 'false'
    docker_compose_file['x-airflow-common']['environment']['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = 'test'
    docker_compose_file['x-airflow-common']['environment']['AIRFLOW__CORE__SQL_ALCHEMY_CONN'] = 'test'
    docker_compose_file['x-airflow-common']['environment']['AIRFLOW__CELERY__RESULT_BACKEND'] = 'test'

    docker_compose_file['services'].pop('postgres', None)
    docker_compose_file['x-airflow-common']['depends_on'].pop('postgres')
    docker_compose_file.pop('volumes', None)

    services = docker_compose_file['services']
    for s in services:
        _env = services[s].get('environment', dict())
        if 'AIRFLOW__CORE__LOAD_EXAMPLES' in _env:
            docker_compose_file['services'][s]['environment']['AIRFLOW__CORE__LOAD_EXAMPLES'] = 'false'

    test_file_output = 'tests/data/test-docker-compose.yaml'
    replace_docker_compose_file(docker_compose_file, test_file_output)

    parsed = parse_docker_compose(test_file_output)

    assert parsed['x-airflow-common']['environment']['AIRFLOW__CORE__LOAD_EXAMPLES'] == 'false'
    assert parsed['x-airflow-common']['environment']['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] == 'test'
    assert parsed['x-airflow-common']['environment']['AIRFLOW__CORE__SQL_ALCHEMY_CONN'] == 'test'
    assert parsed['x-airflow-common']['environment']['AIRFLOW__CELERY__RESULT_BACKEND'] == 'test'
    assert 'postgres' not in parsed['services']
    assert 'postgres' not in parsed['x-airflow-common']['depends_on']
    assert 'volumes' not in parsed

    _clean_file_resources([test_file_output])
