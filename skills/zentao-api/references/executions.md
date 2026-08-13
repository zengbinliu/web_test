# Executions

## Table of Contents
- [List Executions](#list-executions)
- [Create Execution](#create-execution)
- [Get Execution](#get-execution)
- [Update Execution](#update-execution)
- [Delete Execution](#delete-execution)
- [Execution Tasks](#execution-tasks)
- [Execution Stories](#execution-stories)
- [Execution Bugs](#execution-bugs)
- [Execution Builds](#execution-builds)
- [Execution Cases](#execution-cases)

---

## List Executions

**`GET /executions`** or **`GET /projects/:id/executions`**

| Param | Type | Description |
|---|---|---|
| project | int | Filter by project ID |
| status | string | `undone`, `wait`, `doing`, `suspended`, `closed` |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects/1/executions?status=doing" \
  -H "Token: ${TOKEN}"
```

---

## Create Execution

**`POST /executions`**

| Field | Type | Required | Description |
|---|---|---|---|
| project | int | Yes | Parent project ID |
| name | string | Yes | Execution/sprint name |
| code | string | No | Short code |
| begin | date | Yes | Start date |
| end | date | Yes | End date |
| lifetime | string | No | `short`, `long`, `ops` |
| days | int | No | Working days |
| acl | string | No | `open`, `private`, `custom` |
| PO | string | No | Product owner (username) |
| PM | string | No | Project manager |
| QD | string | No | QA director |
| RD | string | No | Release director |
| desc | string | No | Description |
| products | array | No | Product IDs to link |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/executions" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "project": 1,
    "name": "Sprint 1",
    "begin": "2025-01-01",
    "end": "2025-01-15",
    "lifetime": "short",
    "PM": "admin"
  }'
```

---

## Get Execution

**`GET /executions/:id`**

Supports `fields` param for extra data:

| Field Value | Description |
|---|---|
| modules | Module tree |
| builds | Build list |
| moduleoptionmenu | Module option menu |
| members | Team members |
| stories | Linked stories |
| actions | Action history |
| dynamics | Recent activity |
| chartdata | Chart data |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/executions/1?fields=members,stories" \
  -H "Token: ${TOKEN}"
```

---

## Update Execution

**`PUT /executions/:id`**

Same fields as Create (all optional).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/executions/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Sprint 1 - Extended", "end": "2025-01-20"}'
```

---

## Delete Execution

**`DELETE /executions/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/executions/1" \
  -H "Token: ${TOKEN}"
```

---

## Execution Tasks

Listed in [references/tasks.md](tasks.md) — use `GET /executions/:id/tasks` or `POST /executions/:id/tasks`.

---

## Execution Stories

**`GET /executions/:id/stories`**

| Param | Type | Description |
|---|---|---|
| storyType | string | `story`, `requirement`, `epic` |
| status | string | Story status |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/executions/1/stories?status=active" \
  -H "Token: ${TOKEN}"
```

---

## Execution Bugs

**`GET /executions/:id/bugs`**

Same params as [project bugs](projects.md#project-bugs).

```bash
curl -s "${ZENTAO_URL}/api.php/v1/executions/1/bugs?status=active" \
  -H "Token: ${TOKEN}"
```

---

## Execution Builds

**`GET /executions/:id/builds`**

| Param | Type | Description |
|---|---|---|
| status | string | Build status |
| param | string | Extra filter |
| order | string | Sort field |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/executions/1/builds" \
  -H "Token: ${TOKEN}"
```

---

## Execution Cases

**`GET /executions/:id/testcases`**

| Param | Type | Description |
|---|---|---|
| product | int | Filter by product |
| branch | int | Filter by branch |
| status | string | Case status |
| module | int | Filter by module |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/executions/1/testcases" \
  -H "Token: ${TOKEN}"
```
