#!/usr/bin/python
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
    print('Loading secrets...')
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


def start():
    print('Running docker compose with daemon option')
    _exec(cmd='docker compose up -d')


def replace_docker_compose_file(changes, filename):
    print('Updating docker compose')
    noalias_dumper = yaml.dumper.SafeDumper
    noalias_dumper.ignore_aliases = lambda self, data: True
    with open(filename, 'w') as file:
        file.write(
            yaml.dump(changes, Dumper=noalias_dumper))


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
        '--init',
        action='store_true',
        help='Airflow run only the init db command, does not start airflow',
    )
    parser.add_argument(
        '--download-source',
        action='store_true',
        help='Download source and edit it',
    )
    parser.add_argument(
        '--image',
        type=str,
        help='Set a custom Airflow Docker image'
    )

    args = parser.parse_args()

    try:
        if args.download_source:
            print('Setup Working Directory')
            setup_home(workdir_path=args.workdir)
            # create airflow folders
            print('Create Airflow folders if not exist')
            mkdir('./dags')
            mkdir('./logs')
            mkdir('./plugins')

            print('download docker-compose default file')
            download_files(
                files=[
                    (
                        DOCKER_COMPOSE_FILE,
                        'https://airflow.apache.org/docs/apache-airflow/'
                        + args.version + '/docker-compose.yaml'
                    )
                ]
            )

            # set .env file
            print('Setup env file')
            env = dict()
            env['AIRFLOW_UID'] = str(get_uid())
            mk_env_file(env)

        if not args.with_example_dags:
            docker_compose_file = parse_docker_compose(DOCKER_COMPOSE_FILE)
            # disable example dags
            print('Disable example DAGs')
            services = docker_compose_file['services']
            remove_example_dags(docker_compose_file,
                                services, DOCKER_COMPOSE_FILE)

        if args.external_db:
            docker_compose_file = parse_docker_compose(DOCKER_COMPOSE_FILE)
            print('External DB')
            secrets = load_secrets()
            services = docker_compose_file['services']
            replace_db(docker_compose_file, services,
                       secrets, DOCKER_COMPOSE_FILE)

        if args.image is not None:
            docker_compose_file = parse_docker_compose(DOCKER_COMPOSE_FILE)
            _image = args.image
            services = docker_compose_file['services']
            update_image(docker_compose_file, services,
                         _image, DOCKER_COMPOSE_FILE)

        if args.init:
            print('Running only DB init')
            _exec(cmd='docker compose up airflow-init')
            return 0

        else:
            print('Run init command')
            start()
            return 0

    except Exception as e:
        print(str(e))
        return 1


def update_image(docker_compose_file, services, _image, output_file):
    print('Updating docker image')
    for s in services:
        services[s]['image'] = _image
    replace_docker_compose_file(
        docker_compose_file,
        output_file
    )


def remove_example_dags(docker_compose_file, services, output_file):
    for s in services:
        _env = services[s].get('environment', dict())
        if 'AIRFLOW__CORE__LOAD_EXAMPLES' in _env:
            docker_compose_file['services'][s]['environment']['AIRFLOW__CORE__LOAD_EXAMPLES'] = 'false'
    replace_docker_compose_file(
        docker_compose_file,
        output_file
    )


def replace_db(docker_compose_file, services, secrets, output_file):
    print('Replace DB container with other db')
    db_conn = 'postgresql+psycopg2://' + \
        secrets['DB_USER'] + ':' + \
        secrets['DB_PASSWORD'] + '@' + secrets['DB_HOST']
    for s in services:
        _env = services[s].get('environment', dict())
        if 'AIRFLOW__DATABASE__SQL_ALCHEMY_CONN' in _env:
            docker_compose_file['services'][s]['environment']['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = db_conn
        if 'AIRFLOW__CORE__SQL_ALCHEMY_CONN' in _env:
            docker_compose_file['services'][s]['environment']['AIRFLOW__CORE__SQL_ALCHEMY_CONN'] = db_conn
        if 'AIRFLOW__CELERY__RESULT_BACKEND' in _env:
            docker_compose_file['services'][s]['environment']['AIRFLOW__CELERY__RESULT_BACKEND'] = 'db' + db_conn
        _depends_on = services[s].get('depends_on', dict())
        _depends_on.pop('postgres', None)

        # remove depends on db
    print('Remove DB container from docker compose')
    docker_compose_file['services'].pop('postgres', None)
    docker_compose_file.pop('volumes', None)
    replace_docker_compose_file(
        docker_compose_file,
        output_file
    )


if __name__ == '__main__':
    sys.exit(main())
