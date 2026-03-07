# RU Server — Dante SOCKS5 Security Setup (MM-25)

RU сервер используется как SOCKS5 прокси для обхода HTTP 451 (Яндекс Музыка с EU IP).

## Проблема

Порт 1080 (Dante) открыт для всего интернета без аутентификации — любой может использовать прокси.

## Решение

1. **ufw** — закрыть порт 1080 для всех, разрешить только EU серверу (и локальной машине разработчика)
2. **Dante** — включить обязательную аутентификацию по логину/паролю

---

## Шаги

### 1. Узнать IP EU сервера

```bash
# На EU сервере:
curl ifconfig.me
```

### 2. Настроить firewall (ufw)

```bash
# На RU сервере как root:
chmod +x setup-firewall.sh
./setup-firewall.sh <EU_SERVER_IP>

# Опционально — разрешить локальную машину разработчика:
./setup-firewall.sh <EU_SERVER_IP> <DEV_IP>
```

Результат: только SSH (22) и порт 1080 с разрешённых IP.

### 3. Создать пользователя для прокси

```bash
chmod +x add-proxy-user.sh
./add-proxy-user.sh proxyuser <strong_password>
```

### 4. Обновить конфиг Dante

```bash
# Сделать бэкап текущего конфига
cp /etc/danted.conf /etc/danted.conf.bak

# Установить новый
cp danted.conf /etc/danted.conf

# Перезапустить
systemctl restart danted
systemctl status danted
```

### 5. Обновить YM_PROXY_URL на EU сервере

В `.env` на EU сервере:
```env
YM_PROXY_URL=socks5://proxyuser:<password>@<RU_SERVER_IP>:1080
```

```bash
# Перезапустить worker на EU сервере:
docker compose restart worker
```

### 6. Проверить

```bash
# С EU сервера — должно работать:
curl --socks5 proxyuser:<password>@<RU_SERVER_IP>:1080 https://api.music.yandex.net/

# С любого другого IP — должно быть закрыто (connection refused / timeout):
curl --max-time 5 --socks5 <RU_SERVER_IP>:1080 https://example.com
```

---

## Проверка что порты закрыты

```bash
# На RU сервере:
ufw status verbose

# Ожидаемый вывод:
# 22/tcp    ALLOW IN    Anywhere
# 1080/tcp  ALLOW IN    <EU_SERVER_IP>
# 1080/tcp  ALLOW IN    <DEV_IP>      (если указан)
```

---

## Если что-то пошло не так

```bash
# Восстановить конфиг Dante:
cp /etc/danted.conf.bak /etc/danted.conf
systemctl restart danted

# Сбросить ufw:
ufw --force reset
ufw allow 22/tcp
ufw --force enable
```
