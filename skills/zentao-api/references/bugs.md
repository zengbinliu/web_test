# Bugs

## Table of Contents
- [List Bugs](#list-bugs)
- [Create Bug](#create-bug)
- [Get Bug](#get-bug)
- [Update Bug](#update-bug)
- [Delete Bug](#delete-bug)
- [Resolve Bug](#resolve-bug)
- [Close Bug](#close-bug)
- [Confirm Bug](#confirm-bug)
- [Assign Bug](#assign-bug)
- [Activate Bug](#activate-bug)
- [Record Estimate](#record-estimate)

---

## List Bugs

**`GET /bugs`** or **`GET /products/:id/bugs`**

| Param | Type | Description |
|---|---|---|
| product | int | Product ID (required for `/bugs` without product context) |
| status | string | `active`, `resolved`, `closed`, `all` |
| order | string | Sort: e.g. `id_desc`, `severity_asc` |
| limit | int | Items per page |
| page | int | Page number |

```bash
# List bugs for product 1
curl -s "${ZENTAO_URL}/api.php/v1/products/1/bugs?status=active&limit=20" \
  -H "Token: ${TOKEN}"
```

---

## Create Bug

**`POST /bugs`** or **`POST /products/:id/bugs`**

| Field | Type | Required | Description |
|---|---|---|---|
| product | int | Yes | Product ID |
| title | string | Yes | Bug title |
| module | int | No | Module ID |
| project | int | No | Project ID |
| execution | int | No | Execution/sprint ID |
| openedBuild | string | No | Build where found (e.g. `trunk`) |
| type | string | No | `codeerror`, `config`, `install`, `security`, `performance`, `standard`, `automation`, `designdefect`, `others` |
| severity | int | No | 1-4 (1=critical, 4=minor) |
| pri | int | No | Priority 1-4 |
| os | string | No | `all`, `windows`, `linux`, `mac`, etc. |
| browser | string | No | `all`, `ie`, `chrome`, `firefox`, etc. |
| steps | string | No | Steps to reproduce (HTML) |
| story | int | No | Related story ID |
| task | int | No | Related task ID |
| assignedTo | string | No | Assigned username |
| deadline | date | No | Deadline (YYYY-MM-DD) |
| mailto | string | No | Notify users (comma-separated) |
| keywords | string | No | Keywords |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/bugs" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 1,
    "title": "Login page crashes on empty password",
    "type": "codeerror",
    "severity": 2,
    "pri": 1,
    "steps": "<p>1. Go to login page</p><p>2. Leave password empty</p><p>3. Click submit</p>",
    "assignedTo": "dev1"
  }'
```

---

## Get Bug

**`GET /bugs/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/bugs/42" \
  -H "Token: ${TOKEN}"
```

---

## Update Bug

**`PUT /bugs/:id`**

Same fields as Create (all optional).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/bugs/42" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"severity": 1, "pri": 1, "assignedTo": "dev2"}'
```

---

## Delete Bug

**`DELETE /bugs/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/bugs/42" \
  -H "Token: ${TOKEN}"
```

---

## Resolve Bug

**`POST /bugs/:id/resolve`**

| Field | Type | Required | Description |
|---|---|---|---|
| resolution | string | Yes | `bydesign`, `duplicate`, `external`, `fixed`, `notrepro`, `postponed`, `willnotfix`, `tostory` |
| resolvedBuild | string | No | Build where fixed (e.g. `trunk`) |
| resolvedDate | datetime | No | Resolution date |
| duplicateBug | int | No | Duplicate bug ID (when resolution=`duplicate`) |
| assignedTo | string | No | Assign to user after resolve |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/bugs/42/resolve" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"resolution": "fixed", "resolvedBuild": "trunk"}'
```

---

## Close Bug

**`POST /bugs/:id/close`**

| Field | Type | Required | Description |
|---|---|---|---|
| comment | string | No | Closing comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/bugs/42/close" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Verified fixed in build 123"}'
```

---

## Confirm Bug

**`POST /bugs/:id/confirm`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | No | Assign to username |
| mailto | string | No | Notify users |
| comment | string | No | Comment |
| pri | int | No | Priority |
| type | string | No | Bug type |
| status | string | No | Status |
| deadline | date | No | Deadline |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/bugs/42/confirm" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev1", "pri": 2}'
```

---

## Assign Bug

**`POST /bugs/:id/assign`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | Yes | Target username |
| mailto | string | No | Notify users |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/bugs/42/assign" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev2", "comment": "Please investigate"}'
```

---

## Activate Bug

**`POST /bugs/:id/active`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | No | Assign to username |
| openedBuild | string | No | Build where re-found |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/bugs/42/active" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev1", "comment": "Still reproduces in build 124"}'
```

---

## Record Estimate

**`GET /bugs/:id/estimate`** — Get effort records.
**`POST /bugs/:id/estimate`** — Add effort record. Non-open edition only.

| Field | Type | Required | Description |
|---|---|---|---|
| id | int | No | Effort ID (for update) |
| dates | date | No | Work date |
| consumed | float | No | Hours consumed |
| objectType | string | No | Object type |
| objectID | int | No | Object ID |
| work | string | No | Work description |

```bash
# Get efforts
curl -s "${ZENTAO_URL}/api.php/v1/bugs/42/estimate" \
  -H "Token: ${TOKEN}"

# Add effort
curl -s -X POST "${ZENTAO_URL}/api.php/v1/bugs/42/estimate" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"dates": "2025-01-15", "consumed": 2.5, "work": "Investigated root cause"}'
```
