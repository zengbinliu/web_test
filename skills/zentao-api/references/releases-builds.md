# Releases & Builds

## Table of Contents
- [Releases](#releases)
- [Builds](#builds)

---

## Releases

### List Releases

**`GET /releases`** or **`GET /products/:id/releases`**

| Param | Type | Description |
|---|---|---|
| product | int | Product ID |
| branch | int | Branch ID |
| status | string | Release status |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/releases?status=normal" \
  -H "Token: ${TOKEN}"
```

### Get Release

**`GET /releases/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/releases/1" \
  -H "Token: ${TOKEN}"
```

### Update Release

**`PUT /releases/:id`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | No | Release name |
| build | int | No | Build ID |
| status | string | No | Status |
| desc | string | No | Description |

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/releases/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "v1.0.1", "desc": "Hotfix release"}'
```

### Delete Release

**`DELETE /releases/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/releases/1" \
  -H "Token: ${TOKEN}"
```

---

## Builds

### List Builds

**`GET /builds`** or **`GET /projects/:id/builds`** or **`GET /executions/:id/builds`**

| Param | Type | Description |
|---|---|---|
| project | int | Project ID |
| type | string | Build type |
| param | string | Extra filter |
| order | string | Sort field |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects/1/builds" \
  -H "Token: ${TOKEN}"
```

### Create Build

**`POST /builds`**

| Field | Type | Required | Description |
|---|---|---|---|
| execution | int | Yes | Execution/sprint ID |
| product | int | Yes | Product ID |
| name | string | Yes | Build name |
| builder | string | Yes | Builder username |
| date | date | Yes | Build date |
| branch | int | No | Branch ID |
| scmPath | string | No | SCM path/URL |
| filePath | string | No | File storage path |
| desc | string | No | Description |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/builds" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "execution": 1,
    "product": 1,
    "name": "build-20250115",
    "builder": "admin",
    "date": "2025-01-15",
    "desc": "Sprint 1 build"
  }'
```

### Get Build

**`GET /builds/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/builds/1" \
  -H "Token: ${TOKEN}"
```

### Update Build

**`PUT /builds/:id`**

Fields: `execution`, `product`, `branch`, `name`, `builder`, `date`, `scmPath`, `filePath`, `desc`.

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/builds/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "build-20250115-hotfix", "desc": "Hotfix build"}'
```

### Delete Build

**`DELETE /builds/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/builds/1" \
  -H "Token: ${TOKEN}"
```
