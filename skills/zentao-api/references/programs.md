# Programs

## Table of Contents
- [List Programs](#list-programs)
- [Create Program](#create-program)
- [Get Program](#get-program)
- [Update Program](#update-program)
- [Delete Program](#delete-program)

---

## List Programs

**`GET /programs`**

| Param | Type | Description |
|---|---|---|
| status | string | `undone`, `wait`, `doing`, `suspended`, `closed` |
| order | string | Sort field |
| showClosed | bool | Include closed programs |
| mergeChildren | bool | Merge children into list |
| fields | string | Extra fields |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/programs?status=doing" \
  -H "Token: ${TOKEN}"
```

---

## Create Program

**`POST /programs`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Program name |
| begin | date | Yes | Start date (YYYY-MM-DD) |
| end | date | Yes | End date |
| PM | string | No | Program manager (username) |
| budget | string | No | Budget amount |
| budgetUnit | string | No | Currency unit |
| desc | string | No | Description |
| acl | string | No | `open`, `private`, `custom` |
| whitelist | string | No | Group IDs |
| parent | int | No | Parent program ID |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/programs" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "2025 Product Roadmap",
    "begin": "2025-01-01",
    "end": "2025-12-31",
    "PM": "admin",
    "budget": "500000",
    "budgetUnit": "CNY"
  }'
```

---

## Get Program

**`GET /programs/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/programs/1" \
  -H "Token: ${TOKEN}"
```

Sub-resources available via routes:
- `GET /programs/:id/products` — Products under this program
- `GET /programs/:id/projects` — Projects under this program
- `GET /programs/:id/stakeholders` — Stakeholders

---

## Update Program

**`PUT /programs/:id`**

Fields: `name`, `PM`, `budget`, `budgetUnit`, `desc`, `parent`, `begin`, `end`, `realBegan`, `realEnd`, `acl`, `whitelist`.

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/programs/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "2025 Roadmap - Updated", "budget": "600000"}'
```

---

## Delete Program

**`DELETE /programs/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/programs/1" \
  -H "Token: ${TOKEN}"
```
