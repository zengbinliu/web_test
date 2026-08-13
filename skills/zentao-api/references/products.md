# Products

## Table of Contents
- [List Products](#list-products)
- [Create Product](#create-product)
- [Get Product](#get-product)
- [Update Product](#update-product)
- [Delete Product](#delete-product)
- [Search Products](#search-products)
- [Product Plans](#product-plans)
- [Product Projects](#product-projects)

---

## List Products

**`GET /products`**

| Param | Type | Description |
|---|---|---|
| program | int | Filter by program ID |
| project | int | Filter by project ID |
| status | string | Filter: `normal`, `closed`, `all` |
| order | string | Sort: e.g. `id_desc` |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products?status=normal&limit=10" \
  -H "Token: ${TOKEN}"
```

---

## Create Product

**`POST /products`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Product name |
| code | string | Yes | Product code (unique) |
| type | string | No | `normal`, `branch`, `platform` |
| line | int | No | Product line ID |
| desc | string | No | Description (HTML allowed) |
| PO | string | No | Product owner (username) |
| QD | string | No | QA manager (username) |
| RD | string | No | Release manager (username) |
| acl | string | No | Access control: `open`, `private`, `custom` |
| whitelist | string | No | Whitelist groups (comma-separated IDs) |
| program | int | No | Parent program ID |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Product",
    "code": "myproduct",
    "type": "normal",
    "PO": "admin",
    "program": 1
  }'
```

---

## Get Product

**`GET /products/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1" \
  -H "Token: ${TOKEN}"
```

---

## Update Product

**`PUT /products/:id`**

Same fields as Create (all optional for update).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/products/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Name", "desc": "New description"}'
```

---

## Delete Product

**`DELETE /products/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/products/1" \
  -H "Token: ${TOKEN}"
```

---

## Search Products

**`GET /products/search`**

| Param | Type | Required | Description |
|---|---|---|---|
| keyword | string | Yes | Search term |
| status | string | No | `normal`, `closed`, `all` |
| page | int | No | Page number |
| limit | int | No | Items per page |
| withUser | bool | No | Include user info |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/search?keyword=mobile&status=normal" \
  -H "Token: ${TOKEN}"
```

---

## Product Plans

### List Plans

**`GET /products/:id/plans`** or **`GET /productplans`**

| Param | Type | Description |
|---|---|---|
| branch | int | Filter by branch ID |
| status | string | `wait`, `doing`, `done`, `closed` |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/plans?status=doing" \
  -H "Token: ${TOKEN}"
```

### Create Plan

**`POST /products/:id/plans`** or **`POST /productplans`**

| Field | Type | Required | Description |
|---|---|---|---|
| title | string | Yes | Plan title |
| begin | date | No | Start date (YYYY-MM-DD) |
| end | date | No | End date (YYYY-MM-DD) |
| branch | int | No | Branch ID |
| desc | string | No | Description |
| parent | int | No | Parent plan ID |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/plans" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"title": "Sprint 1", "begin": "2025-01-01", "end": "2025-01-15"}'
```

### Get Plan

**`GET /productplans/:id`**

Returns plan with linked stories and bugs.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/productplans/1" \
  -H "Token: ${TOKEN}"
```

### Update Plan

**`PUT /productplans/:id`**

Fields: `title`, `begin`, `end`, `desc`.

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/productplans/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"title": "Sprint 1 - Updated", "end": "2025-01-20"}'
```

### Delete Plan

**`DELETE /productplans/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/productplans/1" \
  -H "Token: ${TOKEN}"
```

### Link Stories to Plan

**`POST /productplans/:id/linkstories`**

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/productplans/1/linkstories" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"stories": [1, 2, 3]}'
```

### Unlink Stories from Plan

**`POST /productplans/:id/unlinkstories`**

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/productplans/1/unlinkstories" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"stories": [1, 2]}'
```

### Link/Unlink Bugs

**`POST /productplans/:id/linkbugs`** and **`POST /productplans/:id/unlinkbugs`**

Same pattern as stories — body: `{"bugs": [1, 2, 3]}`.

---

## Product Projects

### List Projects for Product

**`GET /products/:id/projects`**

| Param | Type | Description |
|---|---|---|
| status | string | Filter by project status |
| fields | string | Extra fields to include |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/projects" \
  -H "Token: ${TOKEN}"
```

### Create Project for Product

**`POST /products/:id/projects`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Project name |
| code | string | No | Project code |
| begin | date | Yes | Start date |
| end | date | Yes | End date |
| products | array | No | Product IDs to link |
| acl | string | No | `open`, `private`, `custom` |
| model | string | No | `scrum`, `waterfall`, `kanban`, `agileplus` |
| PM | string | No | Project manager (username) |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/projects" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q1 Release",
    "begin": "2025-01-01",
    "end": "2025-03-31",
    "model": "scrum",
    "PM": "admin"
  }'
```
