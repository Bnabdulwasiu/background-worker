#!/usr/bin/env bash
# HNG Stage 9 - Automated Ubuntu VPS Deployment Script
set -euo pipefail

# 1. Input Validation
if [ "$#" -ne 1 ]; then
    echo "Usage: sudo $0 <your-subdomain.duckdns.org>"
    exit 1
fi
DOMAIN="$1"

echo "=========================================="
echo " Starting Deployment for: $DOMAIN"
echo "=========================================="

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (using sudo)"
  exit 1
fi

# 2. Update and Install Dependencies
apt-get update && apt-get upgrade -y
apt-get install -y python3-pip python3-venv nginx postgresql postgresql-contrib git certbot python3-certbot-nginx nodejs npm

# 3. Setup PostgreSQL Database
echo "Configuring PostgreSQL Database..."
DB_USER="scheduler_user"
DB_NAME="scheduler_db"
DB_PASS=$(openssl rand -hex 16)

# Check if database already exists
if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;"
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    echo "Database and User created successfully."
else
    echo "Database $DB_NAME already exists, skipping database creation."
    # We will try to fetch the existing DB credentials or ask them to manually configure
    echo "Using existing database configuration."
fi

# 4. Setup directories
echo "Setting up application directories..."
mkdir -p /var/www/scheduler

# Determine base directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Sync folder to /var/www/scheduler (excluding venv, node_modules)
rsync -av --exclude 'venv' --exclude 'node_modules' --exclude '.git' "$BASE_DIR/" /var/www/scheduler/

# Adjust owner
chown -R ubuntu:ubuntu /var/www/scheduler
chmod -R 755 /var/www/scheduler

# 5. Build Backend Environment
echo "Setting up Python virtual environment..."
cd /var/www/scheduler/backend
sudo -u ubuntu python3 -m venv venv
sudo -u ubuntu /var/www/scheduler/backend/venv/bin/pip install --upgrade pip
sudo -u ubuntu /var/www/scheduler/backend/venv/bin/pip install -r requirements.txt

# Create .env
ENV_FILE="/var/www/scheduler/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env file..."
    cat <<EOF > "$ENV_FILE"
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
DLQ_THRESHOLD=10
STARVATION_BOOST_INTERVAL=60
MAX_RETRIES=3
WORKER_POLL_INTERVAL=2.0
SSE_POLL_INTERVAL=1.0
FAILURE_RATE=0.2
CORS_ORIGINS=["https://$DOMAIN"]
EOF
    chown ubuntu:ubuntu "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# Run database migrations
echo "Running alembic database migrations..."
sudo -u ubuntu /var/www/scheduler/backend/venv/bin/alembic upgrade head

# 6. Build Frontend Static Assets
echo "Building React frontend..."
cd /var/www/scheduler/frontend
sudo -u ubuntu npm install
sudo -u ubuntu npm run build

# 7. Configure Systemd Services
echo "Configuring systemd services..."
cp /var/www/scheduler/deployment/scheduler-api.service /etc/systemd/system/
cp /var/www/scheduler/deployment/scheduler-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable scheduler-api scheduler-worker
systemctl start scheduler-api scheduler-worker

# 8. Configure Nginx Configuration
echo "Configuring Nginx Reverse Proxy..."
sed "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" /var/www/scheduler/deployment/nginx.conf > /etc/nginx/sites-available/scheduler
ln -sf /etc/nginx/sites-available/scheduler /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

echo "=========================================="
echo " Deployment Successful!"
echo " Next Steps to Enable SSL / HTTPS:"
echo " sudo certbot --nginx -d $DOMAIN"
echo "=========================================="
