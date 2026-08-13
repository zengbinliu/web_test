# Todos

## Table of Contents
- [List Todos](#list-todos)
- [Create Todo](#create-todo)
- [Get Todo](#get-todo)
- [Update Todo](#update-todo)
- [Delete Todo](#delete-todo)
- [Finish Todo](#finish-todo)
- [Activate Todo](#activate-todo)

---

## List Todos

**`GET /todos`**

| Param | Type | Description |
|---|---|---|
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/todos?limit=20" \
  -H "Token: ${TOKEN}"
```

---

## Create Todo

**`POST /todos`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Todo title |
| date | date | No | Date (YYYY-MM-DD) |
| type | string | No | `custom`, `bug`, `task`, `story` |
| pri | int | No | Priority 1-4 |
| desc | string | No | Description |
| begin | time | No | Begin time (HH:MM) |
| end | time | No | End time (HH:MM) |
| status | string | No | `wait`, `doing`, `done` |
| private | bool | No | Private todo |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/todos" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Review Sprint 1 stories",
    "date": "2025-01-15",
    "type": "custom",
    "pri": 2,
    "begin": "09:00",
    "end": "10:00"
  }'
```

---

## Get Todo

**`GET /todos/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/todos/1" \
  -H "Token: ${TOKEN}"
```

---

## Update Todo

**`PUT /todos/:id`**

Fields: `name`, `date`, `type`, `pri`, `desc`, `begin`, `end`, `status`, `private`.

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/todos/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Review Sprint 1 stories (updated)", "pri": 1}'
```

---

## Delete Todo

**`DELETE /todos/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/todos/1" \
  -H "Token: ${TOKEN}"
```

---

## Finish Todo

**`GET /todos/:id/finish`** — Note: uses GET, not POST.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/todos/1/finish" \
  -H "Token: ${TOKEN}"
```

---

## Activate Todo

**`GET /todos/:id/activate`** — Note: uses GET, not POST.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/todos/1/activate" \
  -H "Token: ${TOKEN}"
```
