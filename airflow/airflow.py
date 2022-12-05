#!/usr/bin/python
from __future__ import annotations

import argparse
import json
import os
import pwd
import shlex
import subprocess
import sys

import boto3
import yaml
from botocore.exceptions import ClientError

WORKDIR = '/home/ec2-user/airflow'
DOCKER_COMPOSE_FILE = 'docker-compose.yaml'
ENV_FILE = '.env'


def _get_secret(secret_name, region_name):
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    return json.loads(get_secret_value_response['SecretString'])


def load_secrets():
    return _get_secret(
        secret_name='Airflow/Database',
        region_name='eu-west-1'
    )


def parse_docker_compose(filename):
    with open(filename, 'r') as file:
        docker_compose_default = yaml.load(file, Loader=yaml.Loader)
    return docker_compose_default


def mkdir(dir_path):
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)


def get_uid():
    return pwd.getpwnam('ec2-user').pw_uid


def setup_home(workdir_path):
    mkdir(workdir_path)
    os.chdir(workdir_path)


def mk_env_file(env):
    values = '\n'.join({key + '=' + value for key, value in env.items()})
    with open(ENV_FILE, 'w') as file:
        file.write(values)


def _exec(cmd):
    process = subprocess.Popen(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    print(stdout)
    print(stderr)
    return stdout, stderr


def download_files(files):
    for output_filename, link in files:
        _exec(cmd='wget --output-document=' + output_filename + ' ' + link)


def start(init_only=False):
    if init_only:
        print('Running only DB init')
    _exec(cmd='docker compose up airflow-init')
    if not init_only:
        print('Running docker compose with daemon option')
        _exec(cmd='docker compose up -d')


def replace_docker_compose_file(changes, filename):
    noalias_dumper = yaml.dumper.SafeDumper
    noalias_dumper.ignore_aliases = lambda self, data: True
    with open(filename, 'w') as file:
        file.write(
            yaml.dump(changes, default_flow_style=False, Dumper=noalias_dumper))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-v', '--version',
        type=str,
        default='2.4.3',
        help='Airflow version',
    )
    parser.add_argument(
        '-w', '--workdir',
        type=str,
        default=WORKDIR,
        help='Airflow workdir',
    )
    parser.add_argument(
        '--external-db',
        action='store_true',
        help='External DB',
    )
    parser.add_argument(
        '--with-plugins',
        action='store_true',
        help='Airflow plugins - currently not implemented',
    )
    parser.add_argument(
        '--with-example-dags',
        action='store_true',
        help='Airflow example dags',
    )
    parser.add_argument(
        '--requirements',
        type=str,
        help='Airflow other requirements to install',
    )
    parser.add_argument(
        '--init-only',
        action='store_true',
        help='Airflow run only the init db command, does not start airflow',
    )
    args = parser.parse_args()

    try:
        print('Setup Working Directory')
        setup_home(workdir_path=args.workdir)
        # create airflow folders
        print('Create Airflow folders')
        mkdir('./dags')
        mkdir('./logs')
        mkdir('./plugins')

        # set .env file
        print('Setup env file')
        env = dict()
        env['AIRFLOW_UID'] = str(get_uid())

        if args.requirements:
            print('Add additional requirements')
            env['_PIP_ADDITIONAL_REQUIREMENTS'] = args.requirements

        mk_env_file(env)
        print('download docker-compose default file')
        download_files(
            files=[
                (
                    DOCKER_COMPOSE_FILE,
                    'https://airflow.apache.org/docs/apache-airflow/' +
                    args.version + '/docker-compose.yaml'
                )
            ]
        )
        docker_compose_file = parse_docker_compose(DOCKER_COMPOSE_FILE)

        if args.with_example_dags:
            # disable example dags
            print('Disable example DAGs')
            docker_compose_file['x-airflow-common']['environment']['AIRFLOW__CORE__LOAD_EXAMPLES'] = False

        if args.external_db:
            print('External DB')
            print('Loading secrets...')
            secrets = load_secrets()
            # update env
            print('Update docker compose environment')
            db_conn = 'postgresql+psycopg2://' + \
                secrets['DB_USER'] + ':' + \
                secrets['DB_PASSWORD'] + '@' + secrets['DB_HOST']
            docker_compose_file['x-airflow-common']['environment']['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = db_conn
            docker_compose_file['x-airflow-common']['environment']['AIRFLOW__CORE__SQL_ALCHEMY_CONN'] = db_conn
            docker_compose_file['x-airflow-common']['environment']['AIRFLOW__CELERY__RESULT_BACKEND'] = 'db' + db_conn
            # remove depends on db
            print('Remove DB container from docker compose')
            docker_compose_file['services'].pop('postgres', None)
            docker_compose_file['x-airflow-common']['depends_on'].pop(
                'postgres')
            docker_compose_file.pop('volumes', None)

        print('Updating docker compose')
        replace_docker_compose_file(docker_compose_file, DOCKER_COMPOSE_FILE)

        print('Run init command')
        start(init_only=args.init_only)

        return 0
    except Exception as e:
        print(str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
