#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=====================================================${NC}"
echo -e "${GREEN} نصب خودکار ربات فروش VPN (DAC)${NC}"
echo -e "${GREEN}=====================================================${NC}"

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}لطفاً اسکریپت را به عنوان root اجرا کنید${NC}"
  exit 1
fi

echo -e "${YELLOW}[1/5] نصب پیش‌نیازهای سیستم...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip python3-venv wget curl qrencode

echo -e "${YELLOW}[2/5] تنظیم دیتابیس (بدون آسیب به x-ui)...${NC}"

# بررسی اینکه آیا اصلا دیتابیسی روی سرور نصب است یا خیر
if ! command -v mysql &> /dev/null; then
    echo -e "${YELLOW}دیتابیسی روی سرور یافت نشد، در حال نصب MariaDB...${NC}"
    apt-get install -y mariadb-server libmariadb-dev-compat libmariadb-dev-dev -y
fi

# استارت کردن دیتابیس (پشتیبانی از هر دو نام mysql و mariadb)
systemctl start mariadb 2>/dev/null || systemctl start mysql 2>/dev/null

DB_NAME="dac_db_$(openssl rand -hex 3)"
DB_USER="dac_user_$(openssl rand -hex 3)"
DB_PASS=$(openssl rand -hex 16)

MYSQL_CMD="mysql -u root"

# بررسی اینکه آیا دیتابیس رمز root دارد یا خیر
if ! mysql -u root -e "USE mysql;" &> /dev/null; then
    echo -e "${YELLOW}دیتابیس دارای رمز root است.${NC}"
    echo -e "${RED}توجه: هنگام تایپ رمز، هیچ کاراکتری روی صفحه نمایش داده نمی‌شود (برای امنیت).${NC}"
    echo -e "${RED}لطفاً رمز را دقیقاً تایپ کنید و در نهایت دکمه Enter را بزنید.${NC}"
    read -s MYSQL_ROOT_PASS
    echo "" # خط خالی برای زیبایی
    MYSQL_CMD="mysql -u root -p$MYSQL_ROOT_PASS"
fi

# تست اتصال به دیتابیس
if ! $MYSQL_CMD -e "SELECT 1;" &> /dev/null; then
    echo -e "${RED}خطا! رمز دیتابیس اشتباه است یا سرویس دیتابیس خراب است.${NC}"
    exit 1
fi

# ساخت دیتابیس و یوزر اختصاصی برای ربات DAC
 $MYSQL_CMD -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
 $MYSQL_CMD -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
 $MYSQL_CMD -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';"
 $MYSQL_CMD -e "FLUSH PRIVILEGES;"

echo -e "${GREEN}دیتابیس با موفقیت و بدون تداخل با پنل قبلی ایجاد شد.${NC}"

echo -e "${YELLOW}[3/5] دریافت اطلاعات ربات...${NC}"
read -p "توکن ربات تلگرام را وارد کنید: " BOT_TOKEN
read -p "آیدی عددی ادمین تلگرام را وارد کنید: " ADMIN_ID
read -p "آیا میخواهید از پروکسی استفاده کنید؟ (y/n): " USE_PROXY
PROXY_URL=""

if [ "$USE_PROXY" = "y" ]; then
    echo -e "${YELLOW}لطفا آدرس پروکسی لوکال x-ui (مثلا socks5://127.0.0.1:1080) را وارد کنید:${NC}"
    read -p "آدرس پروکسی: " PROXY_URL
fi

echo -e "${YELLOW}[4/5] استقرار فایل‌های DAC...${NC}"
mkdir -p /opt/dac-bot
cd /opt/dac-bot

if [ ! -f "main.py" ]; then
    echo -e "${RED}خطا: فایل‌های پایتون در /opt/dac-bot یافت نشد!${NC}"
    exit 1
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cat <<EOF > .env
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS
PROXY_URL=$PROXY_URL
EOF

python -c "from database import Base, engine; Base.metadata.create_all(engine)"
echo -e "${GREEN}جداول دیتابیس ساخته شدند.${NC}"

echo -e "${YELLOW}[5/5] راه‌اندازی سرویس DAC...${NC}"
cat <<EOF > /etc/systemd/system/dac-bot.service
[Unit]
Description=DAC VPN Selling Bot
After=network.target mysql.service mariadb.service

[Service]
User=root
WorkingDirectory=/opt/dac-bot
Environment="PATH=/opt/dac-bot/venv/bin"
ExecStart=/opt/dac-bot/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable dac-bot
systemctl start dac-bot

sleep 3

if systemctl is-active --quiet dac-bot; then
    echo -e "${GREEN}=====================================================${NC}"
    echo -e "${GREEN} 🎉 ربات DAC با موفقیت نصب و روشن شد! 🎉${NC}"
    echo -e "${GREEN}=====================================================${NC}"
else
    echo -e "${RED}خطایی در اجرای ربات رخ داد. لاگ‌ها را با دستور زیر بررسی کنید:${NC}"
    echo "journalctl -u dac-bot -n 30 --no-pager"
fi
