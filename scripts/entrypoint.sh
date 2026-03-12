#!/bin/sh
set -e

echo "Running alembic migrations..."
alembic upgrade head

if [ "${DEV_MODE}" = "true" ]; then
  echo "DEV_MODE: seeding dev_user session..."
  python -c "
import asyncio
from core.db.crud import save_yandex_token, save_soundcloud_token, save_spotify_token

async def seed():
    await save_yandex_token('dev_user', 'fake')
    await save_soundcloud_token('dev_user', 'fake')
    await save_spotify_token('dev_user', 'fake', refresh_token='fake')
    print('dev_user seeded')

asyncio.run(seed())
"
fi

echo "Starting API server..."
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
