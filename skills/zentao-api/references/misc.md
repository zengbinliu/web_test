# Miscellaneous Endpoints

## Table of Contents
- [Modules](#modules)
- [Repositories](#repositories)
- [Feedbacks](#feedbacks)
- [Options](#options)
- [Required Fields](#required-fields)

---

## Modules

**`GET /modules`** — Get module tree for an object type.

| Param | Type | Description |
|---|---|---|
| type | string | `story`, `task`, `bug`, `case`, `feedback`, `product` |
| id | int | Parent object ID (product ID for story/bug/case, execution ID for task) |

```bash
# Get story modules for product 1
curl -s "${ZENTAO_URL}/api.php/v1/modules?type=story&id=1" \
  -H "Token: ${TOKEN}"

# Get task modules for execution 1
curl -s "${ZENTAO_URL}/api.php/v1/modules?type=task&id=1" \
  -H "Token: ${TOKEN}"
```

---

## Repositories

**`GET /repos`** — List code repositories.

| Param | Type | Description |
|---|---|---|
| repoUrl | string | Filter by repo URL |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/repos?limit=20" \
  -H "Token: ${TOKEN}"
```

---

## Feedbacks

### List Feedbacks

**`GET /feedbacks`**

| Param | Type | Description |
|---|---|---|
| status | string | Feedback status |
| orderBy | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |
| fields | string | Extra fields |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/feedbacks?status=wait" \
  -H "Token: ${TOKEN}"
```

### Create Feedback

**`POST /feedbacks`**

| Field | Type | Required | Description |
|---|---|---|---|
| title | string | Yes | Feedback title |
| module | int | No | Module ID |
| product | int | No | Product ID |
| type | string | No | Feedback type |
| public | bool | No | Public visibility |
| desc | string | No | Description |
| status | string | No | Status |
| feedbackBy | string | No | Submitter name |
| notify | bool | No | Send notification |
| pri | int | No | Priority |
| notifyEmail | string | No | Notification email |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/feedbacks" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Unable to export reports in PDF",
    "product": 1,
    "type": "bug",
    "pri": 2,
    "desc": "Export button throws an error when PDF is selected"
  }'
```

### Get Feedback

**`GET /feedbacks/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/feedbacks/1" \
  -H "Token: ${TOKEN}"
```

### Assign Feedback

**`POST /feedbacks/:id/assign`**

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/feedbacks/1/assign" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev1"}'
```

### Close Feedback

**`POST /feedbacks/:id/close`**

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/feedbacks/1/close" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Fixed in v1.2"}'
```

---

## Options

**`GET /options/:type`** — Get option lists for a given type.

Currently supports `type=bug`.

Returns: `typeList`, `priList`, `severityList`, `modules`, `builds` for the specified type.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/options/bug" \
  -H "Token: ${TOKEN}"
```

---

## Required Fields

**`GET /requiredFields`** — Get required field configuration for all modules.

Returns an object mapping module names to their required fields.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/requiredFields" \
  -H "Token: ${TOKEN}"
```

Response example:
```json
{
  "bug": ["title", "product"],
  "story": ["title", "product"],
  "task": ["name", "execution"],
  ...
}
```
