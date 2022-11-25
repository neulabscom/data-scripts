#!/usr/bin/python
import argparse
import sys
import yaml
import subprocess
import shlex
import os
import boto3
import json
from botocore.exceptions import ClientError

WORKDIR='/home/ec2-user/airbyte'

DOCKER_COMPOSE_FILE_DEFAULT='docker-compose.default.yaml'
ENV_FILE_DEFAULT='env.default'

DOCKER_COMPOSE_FILE='docker-compose.yaml'
ENV_FILE='.env'

def get_secret(secret_name, region_name):
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


def parse_docker_compose():
    with open(DOCKER_COMPOSE_FILE_DEFAULT, 'r') as file:
        docker_compose_default = yaml.load(file)

    if 'db' in docker_compose_default['services'].keys():
        del(docker_compose_default['services']['db'])

    if 'db' in docker_compose_default['volumes'].keys():
        del(docker_compose_default['volumes']['db'])

    with open(DOCKER_COMPOSE_FILE, 'w') as file:
        file.write(yaml.dump(docker_compose_default))

def parse_env_file():
    env = {}
    db_secrets = get_secret(
        secret_name = 'Airbyte/Database',
        region_name = 'eu-west-1'
    )

    airbyte_secrets = get_secret(
        secret_name = 'Airbyte/BasicAuth',
        region_name = 'eu-west-1'
    )

    with open(ENV_FILE_DEFAULT, 'r') as file:
        for line in file.read().split('\n'):
            if line == '':
                continue

            if line.startswith('#'):
                continue

            if '=' not in line:
                continue

            key, value = line.split('=')
            env[key] = value

    env['BASIC_AUTH_USERNAME']=str(airbyte_secrets['username'])
    env['BASIC_AUTH_PASSWORD']=str(airbyte_secrets['password'])

    env['DATABASE_USER']=str(db_secrets['username'])
    env['DATABASE_PASSWORD']=str(db_secrets['password'])
    env['DATABASE_HOST']=str(db_secrets['host'])
    env['DATABASE_PORT']=str(db_secrets['port'])
    env['DATABASE_DB']=str(db_secrets['dbname'])
    env['DATABASE_URL']='jdbc:postgresql://' + env['DATABASE_HOST'] + ':' + env['DATABASE_PORT'] + '/' + env['DATABASE_DB']

    values = '\n'.join({key + '=' + value  for key, value in env.items()})
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


def download_files(version, docker_compose_filename, env_filename):
    _exec(cmd='wget --output-document='+ docker_compose_filename + ' https://raw.githubusercontent.com/airbytehq/airbyte/' + version + '/docker-compose.yaml')
    _exec(cmd='wget --output-document=' + env_filename + ' https://raw.githubusercontent.com/airbytehq/airbyte/' + version + '/.env')

def setup_home(workdir_path):
    if not os.path.isdir(workdir_path):
        os.makedirs(workdir_path)
    os.chdir(workdir_path)

def start():
    _exec(cmd='docker-compose down')
    _exec(cmd='docker image prune -a -f')
    _exec(cmd='docker container prune -f')
    _exec(cmd='docker-compose up -d')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-v', '--version',
        type=str,
        default='master',
        help='Airbyte version',
    )
    parser.add_argument(
        '-w', '--workdir',
        type=str,
        default=WORKDIR,
        help='Airbyte workdir',
    )
    parser.add_argument(
        '--with-secrets',
        action='store_true',
        default=False,
        help='Airbyte start',
    )
    args = parser.parse_args()

    try:
        setup_home(workdir_path=args.workdir)

        if args.with_secrets:
            download_files(
                version=args.version, 
                docker_compose_filename=DOCKER_COMPOSE_FILE_DEFAULT, 
                env_filename=ENV_FILE_DEFAULT
            )
            parse_docker_compose()
            parse_env_file()
        else:
            download_files(
                version=args.version, 
                docker_compose_filename=DOCKER_COMPOSE_FILE, 
                env_filename=ENV_FILE
            )

        start()

        return 0
    except Exception as e:
        print(str(e))
        return 1

if __name__ == '__main__':
    sys.exit(main())