# Users

## Table of Contents
- [List Users](#list-users)
- [Create User](#create-user)
- [Get Current User](#get-current-user)
- [Get User by ID](#get-user-by-id)
- [Update User](#update-user)
- [Delete User](#delete-user)
- [Groups](#groups)
- [Departments](#departments)

---

## List Users

**`GET /users`**

| Param | Type | Description |
|---|---|---|
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/users?limit=50" \
  -H "Token: ${TOKEN}"
```

---

## Create User

**`POST /users`**

| Field | Type | Required | Description |
|---|---|---|---|
| account | string | Yes | Username (login name) |
| password | string | Yes | Password |
| realname | string | No | Display name |
| role | string | No | User role |
| dept | int | No | Department ID |
| email | string | No | Email address |
| gender | string | No | `m`, `f` |
| commiter | string | No | VCS committer ID |
| join | date | No | Join date |
| type | string | No | User type |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/users" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "account": "newdev",
    "password": "SecurePass123",
    "realname": "New Developer",
    "role": "dev",
    "dept": 1,
    "email": "newdev@example.com"
  }'
```

---

## Get Current User

**`GET /user`** — Returns the currently authenticated user.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/user" \
  -H "Token: ${TOKEN}"
```

---

## Get User by ID

**`GET /users/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/users/5" \
  -H "Token: ${TOKEN}"
```

---

## Update User

**`PUT /users/:id`**

Same fields as Create (all optional, except `account`).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/users/5" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"realname": "Updated Name", "role": "pm"}'
```

---

## Delete User

**`DELETE /users/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/users/5" \
  -H "Token: ${TOKEN}"
```

---

## Groups

**`GET /groups`** — List all permission groups.

Returns groups with their privileges (`privs`) and member accounts.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/groups" \
  -H "Token: ${TOKEN}"
```

---

## Departments

### List Departments

**`GET /departments`** — Returns department tree.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/departments" \
  -H "Token: ${TOKEN}"
```

### Get Department

**`GET /departments/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/departments/1" \
  -H "Token: ${TOKEN}"
```

### Update Department

**`PUT /departments/:id`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Department name |
| parent | int | No | Parent department ID |
| manager | string | No | Manager username |

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/departments/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Engineering", "manager": "admin"}'
```

### Delete Department

**`DELETE /departments/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/departments/1" \
  -H "Token: ${TOKEN}"
```
