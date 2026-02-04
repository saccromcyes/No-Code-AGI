#!/bin/sh
set -e

API_BASE_URL=${API_BASE_URL:-http://localhost:8000}

sed -i "s|__API_BASE_URL__|${API_BASE_URL}|g" /usr/share/nginx/html/config.js

exec "$@"
