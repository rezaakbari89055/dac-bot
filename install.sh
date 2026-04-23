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

echo -e "${YELLOW}[1/5] بررسی و نصب پیش‌نیازها...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip python3-venv wget curl qrencode

echo -e "${YELLOW}[2/5] بررسی و تنظیم دیتابیس SQL...${NC}"

# بررسی اینکه آیا اصلا MySQL یا MariaDB روی سرور نصب است یا خیر
if ! command -v mysql &> /dev/null; then
    echo -e "${YELLOW}دیتابیس SQL روی سرور یافت نشد (پنل x-ui از فایل SQLite استفاده میکند).${NC}"
    echo -e "${YELLOW}در حال نصب خودکار MariaDB برای ربات DAC...${NC}"
    apt-get install -y mariadb-server libmariadb-dev-compat libmariadb-dev-dev -y
    systemctl start mariadb
    systemctl enable mariadb
    MYSQL_ROOT_PASS="" # چون تازه نصب شده، رمز root خالی است
else
    echo -e "${YELLOW}یک دیتابیس SQL از قبل روی سرور وجود دارد.${NC}"
    systemctl start mysql 2>/dev/null || systemctl start mariadb 2>/dev/null
    
    # بررسی اینکه آیا این دیتابیس از قبل رمز دارد یا خیر
    if ! mysql -u root -e "USE mysql;" &> /dev/null; then
        echo -e "${RED}دیتابیس موجود دارای رمز root است.${NC}"
        echo -e "${YELLOW}توجه: هنگام تایپ رمز هیچ کاراکتری نمایش داده نمی‌شود.${NC}"
        read -s -p "لطفاً رمز root دیتابیس موجود را وارد کنید: " MYSQL_ROOT_PASS
        echo ""
        
        # تست کردن رمز وارد شده
        if ! mysql -u root -p"$MYSQL_ROOT_PASS" -e "SELECT 1;" &> /dev/null; then
            echo -e "${RED}خطا! رمز وارد شده اشتباه است. نصب متوقف شد.${NC}"
            exit 1
        fi
    else
        MYSQL_ROOT_PASS="" # رمز ندارد
    fi
fi

# ساخت دیتابیس اختصاصی برای ربات (با یا بدون رمز)
if [ -z "$MYSQL_ROOT_PASS" ]; then
    MYSQL_CMD="mysql -u root"
else
    MYSQL_CMD="mysql -u root -p$MYSQL_ROOT_PASS"
fi

DB_NAME="dac_db_$(openssl rand -hex 3)"
DB_USER="dac_user_$(openssl rand -hex 3)"
DB_PASS=$(openssl rand -hex 16)

 $MYSQL_CMD -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
 $MYSQL_CMD -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
 $MYSQL_CMD -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';"
 $MYSQL_CMD -e "FLUSH PRIVILEGES;"

echo -e "${GREEN}دیتابیس ربات DAC با موفقیت ایجاد شد (بدون تداخل با x-ui).${NC}"

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
