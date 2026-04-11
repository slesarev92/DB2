# SSL Setup — Let's Encrypt for db2.medoed.work

Production URL: **`https://db2.medoed.work`**
Server: `45.144.221.215`
Domain registrar: medoed.work, A-record `db2 → 45.144.221.215`

## Архитектура: host nginx + docker nginx (двухуровневый proxy)

На сервере **уже работает другое приложение** (`/opt/frpanel/dist`), которое
занимает порт `:80` через **системный nginx** (вне docker). Чтобы не
ломать его, мы используем host-level SSL termination:

```
Internet
   ↓
[host nginx :80 + :443 (SSL)]   ←  Let's Encrypt cert (managed via host certbot)
   ├── server_name db2.medoed.work → proxy_pass http://localhost:8080
   └── server_name 45.144.221.215  → frpanel (existing)
   ↓
[docker nginx :8080 → :80 inside]  ←  HTTP only внутри docker network
   ↓
[backend:8000] / [frontend:3000]
```

**Преимущества:**
- ✅ Не ломает существующее приложение frpanel
- ✅ Стандартный паттерн (Linux nginx + certbot --nginx плагин)
- ✅ Auto-renewal через systemd timer от пакета `certbot`
- ✅ Docker side остаётся простым (HTTP only, без SSL volumes)

## Первая настройка (one-time)

### Шаг 1. Установить certbot на хост

```bash
ssh -i ~/.ssh/db2_deploy root@45.144.221.215
apt update
apt install -y certbot python3-certbot-nginx
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
ln -s /etc/nginx/sites-available/db2.medoed.work /etc/nginx/sites-enabled/

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
    --agree-tos --no-eff-email --redirect
```

Должно вывести:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/db2.medoed.work/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/db2.medoed.work/privkey.pem
...
Successfully deployed certificate for db2.medoed.work to /etc/nginx/sites-enabled/db2.medoed.work
Your existing certificate has been successfully renewed, and the new certificate has been installed.
```

### Шаг 4. Проверить HTTPS работает

```bash
curl -I https://db2.medoed.work/health
# HTTP/2 200
```

### Шаг 5. Обновить .env (CORS + frontend URL)

```bash
cd /opt/dbpassport/infra
sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=https://db2.medoed.work|' .env
sed -i 's|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://db2.medoed.work|' .env
grep -E '^(CORS|NEXT_PUBLIC)' .env
```

### Шаг 6. Пересобрать frontend (NEXT_PUBLIC_* baked в build-time)

```bash
cd /opt/dbpassport
docker build -f frontend/Dockerfile.prod \
    --build-arg NEXT_PUBLIC_API_URL=https://db2.medoed.work \
    --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
    -t dbpassport-frontend:latest frontend/
```

### Шаг 7. Restart всех сервисов чтобы подхватить новый CORS + frontend image

```bash
cd /opt/dbpassport/infra
docker compose -f docker-compose.prod.yml up -d --force-recreate \
    backend celery-worker frontend
sleep 5
docker compose -f docker-compose.prod.yml restart nginx
```

### Шаг 8. Финальная проверка

```bash
# Через host nginx (HTTPS)
curl -I https://db2.medoed.work/health
curl -I https://db2.medoed.work/

# Через docker nginx напрямую (HTTP, для дебага)
curl -I http://127.0.0.1:8080/health

# Все контейнеры healthy?
docker compose -f docker-compose.prod.yml ps
```

После этого `https://db2.medoed.work` работает с зелёным замком.

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
- Проверь DNS: `dig db2.medoed.work` → должен вернуть `45.144.221.215`
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
в собранном frontend образе. Также проверь что нет hardcoded `http://`
URLов в коде frontend.
