# Airflow docker compose script

This script is intended to be used to run Apache Airflow with the docker-compose version in a AWS EC2 virtual machine.

The script is compatible to be executed with python v2.7+

The script is able to run a bare version of airflow with no dags. To add your DAGs you need to integrate this script with your data.

The options available are:

* Use a different DB than the postgres provided in the docker-compose file
* only init the db without starting the tool
* run without example DAGs
* run with a different version instead of the default one

## How to

Run the script with the desired flags.

In case of a custom DB you need to store the credentials inside AWS secrets manager
! right now only a custom implementation of Postgres is implemented !
