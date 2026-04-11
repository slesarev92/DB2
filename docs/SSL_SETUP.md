# SSL Setup — Let's Encrypt for db2.medoed.work

Production URL: **`https://db2.medoed.work`**
Server: `85.239.63.206` (Ubuntu 24.04, 2 CPU, 2GB RAM + 2GB swap)
Domain registrar: medoed.work, A-record `db2 → 85.239.63.206`

## Архитектура: host nginx + docker nginx (двухуровневый proxy)

```
Internet
   ↓
[host nginx :80 + :443 (SSL)]   ←  Let's Encrypt cert (managed via host certbot)
   ↓
[docker nginx :8080 → :80 inside]  ←  HTTP only внутри docker network
   ↓
[backend:8000] / [frontend:3000]
```

**Преимущества:**
- ✅ Стандартный паттерн (Linux nginx + certbot --nginx плагин)
- ✅ Auto-renewal через systemd timer от пакета `certbot`
- ✅ Docker side остаётся простым (HTTP only, без SSL volumes)
- ✅ Можно добавить дополнительные vhost'ы на сервере без затрагивания docker stack

## Первая настройка (one-time)

Уже сделано на текущем prod сервере. Эта инструкция нужна:
- Если переезжаем на новый сервер
- Если SSL/nginx config испортился

### Шаг 1. Установить certbot + nginx на хост

```bash
ssh -i ~/.ssh/db2_deploy root@85.239.63.206
apt update
apt install -y nginx certbot python3-certbot-nginx
certbot --version  # должна быть 2.x
```

### Шаг 2. Создать host nginx vhost для db2.medoed.work

```bash
cat > /etc/nginx/sites-available/db2.medoed.work <<'EOF'
# Reverse proxy на docker nginx (port 8080)
# SSL: certbot --nginx добавит ssl_certificate директивы автоматически

server {
    listen 80;
    server_name db2.medoed.work;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }
}
EOF

# Активировать
ln -sf /etc/nginx/sites-available/db2.medoed.work /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Проверить config
nginx -t

# Reload
systemctl reload nginx
```

### Шаг 3. Получить сертификат через certbot --nginx

Certbot:
- Поднимет временный server для ACME challenge на `:80`
- Получит cert от Let's Encrypt
- **Автоматически перепишет** `/etc/nginx/sites-available/db2.medoed.work`
  добавив `listen 443 ssl;`, `ssl_certificate ...;`, `ssl_certificate_key ...;`
  и server block с redirect HTTP → HTTPS

```bash
certbot --nginx -d db2.medoed.work \
    --email mskslesarev@gmail.com \
    --agree-tos --no-eff-email --redirect --non-interactive
```

Должно вывести:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/db2.medoed.work/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/db2.medoed.work/privkey.pem
...
Successfully deployed certificate for db2.medoed.work to /etc/nginx/sites-enabled/db2.medoed.work
Congratulations! You have successfully enabled HTTPS on https://db2.medoed.work
```

### Шаг 4. Проверить HTTPS работает

```bash
curl -s https://db2.medoed.work/health
# {"status":"ok"}
```

## Renewal

Пакет `certbot` от Debian/Ubuntu **автоматически** ставит systemd timer
`certbot.timer`, который запускается дважды в день и обновляет cert
если осталось <30 дней до истечения.

```bash
# Проверить что timer активен
systemctl status certbot.timer
# active (waiting)

# Список сертификатов и срок действия
certbot certificates

# Manual renew (для теста, обычно не нужно)
certbot renew --dry-run
```

После renewal certbot сам перезагружает host nginx — никаких ручных
действий не требуется.

## Troubleshooting

### `nginx: [emerg] cannot load certificate`
Cert ещё не получен. Запусти certbot (Шаг 3).

### `certbot: ... Challenge failed for domain db2.medoed.work`
- Проверь что `:80` открыт извне: `curl http://db2.medoed.work/` с другой машины
- Проверь DNS: `dig db2.medoed.work` → должен вернуть `85.239.63.206`
- Проверь firewall: `ufw status` или `iptables -L | grep -E '80|443'`

### `502 Bad Gateway` после получения SSL
- Docker nginx не запущен или упал: `docker compose -f docker-compose.prod.yml ps`
- Docker nginx не на 8080: `ss -tlnp | grep 8080`
- Restart: `cd /opt/dbpassport/infra && docker compose -f docker-compose.prod.yml restart nginx`

### CORS errors в браузере на проде
Backend `CORS_ORIGINS` env должен включать `https://db2.medoed.work`.
```bash
docker compose -f docker-compose.prod.yml exec backend env | grep CORS
```
Если старое значение — `up -d --force-recreate backend` (env читается при старте).

### Frontend всё ещё ломится на старый URL
`NEXT_PUBLIC_API_URL` baked в build-time. Нужен **rebuild image**:
```bash
docker build -f frontend/Dockerfile.prod \
    --build-arg NEXT_PUBLIC_API_URL=https://db2.medoed.work \
    --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
    -t dbpassport-frontend:latest frontend/
docker compose -f docker-compose.prod.yml up -d --force-recreate frontend
```

### "Mixed content" warning в браузере
Браузер блокирует HTTP запросы со страницы загруженной через HTTPS.
Проверь что `NEXT_PUBLIC_API_URL=https://db2.medoed.work` (не http://)
в собранном frontend образе.
