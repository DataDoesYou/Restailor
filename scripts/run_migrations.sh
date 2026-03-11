#!/bin/bash
set -e

echo "Starting database migrations..."
echo "Installing Doppler CLI..."
curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh | bash

echo "Running migrations with Doppler..."
doppler run -- poetry run alembic upgrade head

echo "Migrations completed successfully!"
