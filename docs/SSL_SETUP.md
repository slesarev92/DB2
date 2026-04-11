# SSL Setup — Let's Encrypt for db2.medoed.work

Production сервер: `45.144.221.215` (nginx + Let's Encrypt).
Домен: `db2.medoed.work` (A-record → 45.144.221.215, регистратор: medoed.work).

## Архитектура

- **nginx** (port 80 + 443) — reverse proxy с SSL termination
- **Let's Encrypt** — бесплатные TLS-сертификаты (90-дневные, авто-renewal)
- **certbot** — отдельный one-shot контейнер в `docker-compose.prod.yml`
  (profile: `tools`, не запускается с обычным `up`)
- **Volumes:**
  - `letsencrypt` — `/etc/letsencrypt` (сертификаты, ключи, accounts)
  - `certbot-webroot` — `/var/www/certbot` (ACME challenge tokens)

## nginx configs

В репо два nginx-конфига:

- **`infra/nginx/nginx.conf`** — production HTTPS (используется после
  получения cert). HTTP `:80` → ACME challenge + redirect на HTTPS.
  HTTPS `:443` → SSL termination + proxy на backend/frontend.
- **`infra/nginx/nginx.bootstrap.conf`** — bootstrap HTTP-only.
  Используется ОДИН раз для первого получения cert (когда `nginx.conf`
  ссылается на ещё несуществующие SSL файлы и nginx с ним не запустится).

## Первая настройка (one-time)

Выполняется после первого деплоя SSL-конфигов с локалки.

```bash
# 0. Локально: коммит + push (уже сделано если читаешь это)

# 1. На сервере: pull последних конфигов
ssh -i ~/.ssh/db2_deploy root@45.144.221.215
cd /opt/dbpassport
git pull origin main

# 2. Обновить .env: переключить порты на 80/443 + новые URL
cd infra
sed -i 's/^HTTP_PORT=.*/HTTP_PORT=80/' .env
echo "HTTPS_PORT=443" >> .env
sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=https://db2.medoed.work|' .env
sed -i 's|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://db2.medoed.work|' .env

# 3. Подменить nginx.conf на bootstrap (HTTP only) — full SSL ещё не работает
cd nginx
mv nginx.conf nginx.full.conf
cp nginx.bootstrap.conf nginx.conf

# 4. Recreate nginx с новыми портами + bootstrap config
cd /opt/dbpassport/infra
docker compose -f docker-compose.prod.yml up -d --force-recreate nginx
sleep 3

# 5. Проверить что HTTP работает на порту 80
curl http://db2.medoed.work/health
# → {"status":"ok"}

# 6. Получить первый сертификат через webroot
docker compose -f docker-compose.prod.yml run --rm certbot \
    certonly --webroot -w /var/www/certbot \
    -d db2.medoed.work \
    --email mskslesarev@gmail.com \
    --agree-tos --no-eff-email --non-interactive

# Должно появиться:
# Successfully received certificate.
# Certificate is saved at: /etc/letsencrypt/live/db2.medoed.work/fullchain.pem
# Key is saved at:         /etc/letsencrypt/live/db2.medoed.work/privkey.pem

# 7. Переключить nginx.conf обратно на full SSL
cd /opt/dbpassport/infra/nginx
mv nginx.full.conf nginx.conf

# 8. Reload nginx (теперь сертификаты существуют, full SSL config заработает)
cd /opt/dbpassport/infra
docker compose -f docker-compose.prod.yml restart nginx

# 9. Проверить HTTPS
curl https://db2.medoed.work/health
# → {"status":"ok"}

# 10. Пересобрать frontend с новым NEXT_PUBLIC_API_URL (baked в build)
cd /opt/dbpassport
docker build -f frontend/Dockerfile.prod \
    --build-arg NEXT_PUBLIC_API_URL=https://db2.medoed.work \
    --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
    -t dbpassport-frontend:latest frontend/

# 11. Restart всех сервисов чтобы подхватить новый CORS + frontend image
cd infra
docker compose -f docker-compose.prod.yml up -d --force-recreate \
    backend celery-worker frontend
sleep 5
docker compose -f docker-compose.prod.yml restart nginx

# 12. Финальная проверка
curl https://db2.medoed.work/health
docker compose -f docker-compose.prod.yml ps
```

После этого `https://db2.medoed.work` работает с зелёным замком в браузере.

## Renewal (раз в 60 дней, до истечения 90)

Webroot challenge: nginx уже слушает `:80` и обслуживает
`/.well-known/acme-challenge/` (см. полный nginx.conf, server block для :80).
Никакого downtime не нужно.

```bash
ssh -i ~/.ssh/db2_deploy root@45.144.221.215
cd /opt/dbpassport/infra

# Проверить срок действия текущего сертификата
docker compose -f docker-compose.prod.yml run --rm certbot certificates

# Renew (certbot сам решит нужно ли — не renews если >30 дней до истечения)
docker compose -f docker-compose.prod.yml run --rm certbot renew

# Reload nginx чтобы подхватить новый сертификат (если был обновлён)
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Автоматизация renewal через cron (рекомендуется)

```bash
# На сервере
crontab -e
# Добавить:
0 3 * * * cd /opt/dbpassport/infra && docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

Cron запускается каждую ночь в 3:00, certbot обновит cert если осталось <30 дней.

## Troubleshooting

### `nginx: [emerg] cannot load certificate ... no such file`
Cертификаты ещё не получены, а nginx запущен с `nginx.conf` (full SSL).
Решение: подменить на `nginx.bootstrap.conf` (см. шаги 3-4 выше),
получить cert, вернуть `nginx.conf`.

### `certbot: ... Challenge failed for domain db2.medoed.work`
- Проверь что `:80` открыт извне: `curl http://db2.medoed.work/` с другой машины
- Проверь DNS: `dig db2.medoed.work` → должен вернуть `45.144.221.215`
- Проверь что nginx обслуживает `/.well-known/acme-challenge/`:
  `curl http://db2.medoed.work/.well-known/acme-challenge/test` → 404 (не 502/403)
- Файрволл: `iptables -L | grep 80` или `ufw status`

### `502 Bad Gateway` после переключения на full SSL
Backend healthy? `docker compose -f docker-compose.prod.yml ps`
Frontend на новом NEXT_PUBLIC_API_URL? `docker compose ... logs frontend`

### Браузер показывает "Connection not secure"
- Проверь актуальность сертификата: `docker compose ... run --rm certbot certificates`
- Проверь что nginx использует правильный путь к cert (см. nginx.conf:43-44)
- Проверь TLS handshake: `openssl s_client -connect db2.medoed.work:443 -servername db2.medoed.work`

### CORS errors в браузере
Backend `CORS_ORIGINS` env var должен включать `https://db2.medoed.work`.
Проверь: `docker compose ... exec backend env | grep CORS`
