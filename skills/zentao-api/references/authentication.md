# Authentication

## Table of Contents
- [Login (Get Token)](#login-get-token)
- [Ping (Keep Alive)](#ping-keep-alive)
- [System Configuration](#system-configuration)
- [Token Usage Methods](#token-usage-methods)

---

## Login (Get Token)

**`POST /tokens`** — No auth required.

| Field | Type | Required | Description |
|---|---|---|---|
| account | string | Yes | Username |
| password | string | Yes | Password |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tokens" \
  -H "Content-Type: application/json" \
  -d '{"account":"admin","password":"password"}'
```

Response:
```json
{"token": "session_id_string"}
```

The `token` value is a PHP session ID. Store it for all subsequent requests.

---

## Ping (Keep Alive)

**`GET /ping`** — Requires auth. Refreshes the session.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/ping" \
  -H "Token: ${TOKEN}"
```

Response:
```json
{"token": "session_id_string", "tokenLife": 1440}
```

`tokenLife` is the session lifetime in minutes (server-configured, default 1440 = 24h).

---

## System Configuration

**`GET /configurations`** — No auth required.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/configurations"
```

Response includes:
```json
{
  "version": "18.0",
  "edition": "open",
  "charset": "UTF-8",
  "lang": "zh-cn",
  "requestType": "PATH_INFO",
  "timezone": "Asia/Shanghai",
  "features": {...}
}
```

---

## Token Usage Methods

Three ways to pass the token:

### 1. Token Header (Recommended)

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products" \
  -H "Token: ${TOKEN}"
```

### 2. Query Parameter

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products?zentaosid=${TOKEN}"
```

### 3. Cookie

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products" \
  -b "zentaosid=${TOKEN}"
```
