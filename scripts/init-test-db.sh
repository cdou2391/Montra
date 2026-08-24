#!/bin/bash
# Creates the dedicated test database alongside the development database.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE montra_test OWNER $POSTGRES_USER;
EOSQL
