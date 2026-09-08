#!/usr/bin/env bash
# Render build: one service serves the API, the demo storefront and the dashboard.
set -o errexit

pip install -r requirements.txt

cd frontend
npm ci
npm run build
cd ..

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed_demo
