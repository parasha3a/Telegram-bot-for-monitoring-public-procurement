# Бот мониторинга госзакупок

## Установка на сервер Timeweb Cloud

1. Подключитесь к серверу по SSH:
```bash
ssh root@your_server_ip
```

2. Установите Python и необходимые пакеты:
```bash
apt update
apt install python3-pip python3-venv git
```

3. Создайте директорию для проекта и клонируйте репозиторий:
```bash
mkdir /opt/tender-bot
cd /opt/tender-bot
git clone https://github.com/your_repository_url .
```

4. Создайте виртуальное окружение и установите зависимости:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

5. Создайте файл с переменными окружения:
```bash
nano .env
```

Добавьте следующие строки:
```
TELEGRAM_TOKEN=your_bot_token
CHECK_INTERVAL=300
GOSPLAN_API_URL=https://v2test.gosplan.info/fz44
```

6. Создайте systemd сервис для автозапуска бота:
```bash
nano /etc/systemd/system/tender-bot.service
```

Добавьте следующее содержимое:
```ini
[Unit]
Description=Telegram Bot for Tender Monitoring
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tender-bot
Environment=PYTHONPATH=/opt/tender-bot
ExecStart=/opt/tender-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

7. Активируйте и запустите сервис:
```bash
systemctl daemon-reload
systemctl enable tender-bot
systemctl start tender-bot
```

8. Проверьте статус бота:
```bash
systemctl status tender-bot
journalctl -u tender-bot -f
```

## Обновление бота

Для обновления бота выполните:
```bash
cd /opt/tender-bot
git pull
systemctl restart tender-bot
```

## Мониторинг и логи

- Просмотр логов в реальном времени:
```bash
journalctl -u tender-bot -f
```

- Просмотр статуса сервиса:
```bash
systemctl status tender-bot
```

## Команды управления

- Остановить бота: `systemctl stop tender-bot`
- Запустить бота: `systemctl start tender-bot`
- Перезапустить бота: `systemctl restart tender-bot`
