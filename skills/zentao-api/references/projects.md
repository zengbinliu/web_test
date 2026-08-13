# Projects

## Table of Contents
- [List Projects](#list-projects)
- [Create Project](#create-project)
- [Get Project](#get-project)
- [Update Project](#update-project)
- [Delete Project](#delete-project)
- [Project Bugs](#project-bugs)
- [Project Stories](#project-stories)
- [Project Releases](#project-releases)
- [Project Cases](#project-cases)

---

## List Projects

**`GET /projects`**

| Param | Type | Description |
|---|---|---|
| status | string | `undone`, `wait`, `doing`, `suspended`, `closed`, `all` |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects?status=doing&limit=10" \
  -H "Token: ${TOKEN}"
```

---

## Create Project

**`POST /projects`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Project name |
| begin | date | Yes | Start date (YYYY-MM-DD) |
| end | date | Yes | End date |
| parent | int | No | Parent program ID |
| PM | string | No | Project manager (username) |
| budget | string | No | Budget amount |
| model | string | No | `scrum`, `waterfall`, `kanban`, `agileplus` |
| products | array | No | Product IDs to link |
| desc | string | No | Description |
| acl | string | No | `open`, `private`, `custom` |
| whitelist | string | No | Group IDs (comma-separated) |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/projects" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q1 2025 Release",
    "begin": "2025-01-01",
    "end": "2025-03-31",
    "model": "scrum",
    "PM": "admin",
    "products": [1, 2]
  }'
```

---

## Get Project

**`GET /projects/:id`**

Supports `fields` param for extra data:

| Field Value | Description |
|---|---|
| team | Include team members |
| products | Include linked products |
| stat | Include statistics |
| workhour | Include work hours |
| actions | Include action history |
| dynamics | Include recent activity |

```bash
# Basic
curl -s "${ZENTAO_URL}/api.php/v1/projects/1" \
  -H "Token: ${TOKEN}"

# With extra fields
curl -s "${ZENTAO_URL}/api.php/v1/projects/1?fields=team,stat,products" \
  -H "Token: ${TOKEN}"
```

---

## Update Project

**`PUT /projects/:id`**

Same fields as Create (all optional).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/projects/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Q1 2025 Release - Updated", "end": "2025-04-15"}'
```

---

## Delete Project

**`DELETE /projects/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/projects/1" \
  -H "Token: ${TOKEN}"
```

---

## Project Bugs

**`GET /projects/:id/bugs`**

| Param | Type | Description |
|---|---|---|
| product | int | Filter by product |
| branch | int | Filter by branch |
| build | int | Filter by build |
| status | string | Bug status filter |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects/1/bugs?status=active" \
  -H "Token: ${TOKEN}"
```

---

## Project Stories

**`GET /projects/:id/stories`**

| Param | Type | Description |
|---|---|---|
| product | int | Filter by product |
| branch | int | Filter by branch |
| status | string | Story status filter |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects/1/stories?status=active" \
  -H "Token: ${TOKEN}"
```

---

## Project Releases

### List Releases

**`GET /projects/:id/releases`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects/1/releases" \
  -H "Token: ${TOKEN}"
```

### Create Release under Project

**`POST /projects/:id/releases`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Release name |
| build | int | Yes | Build ID |
| product | int | Yes | Product ID |
| date | date | No | Release date |
| notify | bool | No | Send notification |
| mailto | string | No | Notify users |
| desc | string | No | Description |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/projects/1/releases" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "v1.0.0",
    "build": 5,
    "product": 1,
    "date": "2025-03-31"
  }'
```

---

## Project Cases

**`GET /projects/:id/testcases`**

| Param | Type | Description |
|---|---|---|
| product | int | Filter by product |
| branch | int | Filter by branch |
| status | string | Case status |
| caseType | string | Case type |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/projects/1/testcases" \
  -H "Token: ${TOKEN}"
```
