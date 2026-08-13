# Test Cases

## Table of Contents
- [Test Cases](#test-cases-1)
- [Test Suites](#test-suites)
- [Test Tasks](#test-tasks)
- [Test Results](#test-results)

---

## Test Cases

### List Test Cases

**`GET /testcases`** or **`GET /products/:id/testcases`**

| Param | Type | Description |
|---|---|---|
| product | int | Product ID |
| status | string | Case status |
| branch | int | Branch ID |
| module | int | Module ID |
| caseType | string | Case type |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/testcases?limit=20" \
  -H "Token: ${TOKEN}"
```

### Create Test Case

**`POST /testcases`** or **`POST /products/:id/testcases`**

| Field | Type | Required | Description |
|---|---|---|---|
| product | int | Yes | Product ID |
| title | string | Yes | Case title |
| type | string | Yes | `feature`, `performance`, `config`, `install`, `security`, `interface`, `other` |
| pri | int | Yes | Priority 1-4 |
| steps | array | Yes | Test steps (see below) |
| module | int | No | Module ID |
| story | int | No | Related story ID |
| stage | string | No | Test stage |
| precondition | string | No | Precondition text |
| keywords | string | No | Keywords |
| files | binary | No | files |

Steps array — each step:

| Field | Type | Required | Description |
|---|---|---|---|
| desc | string | Yes | Step description |
| expect | string | Yes | Expected result |
| type | string | No | `item` (step) or `group` (group header) |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/testcases" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 1,
    "title": "Login with valid credentials",
    "type": "feature",
    "pri": 1,
    "precondition": "User account exists",
    "steps": [
      {"desc": "Go to login page", "expect": "Login form displayed", "type": "item"},
      {"desc": "Enter valid username and password", "expect": "Fields accept input", "type": "item"},
      {"desc": "Click Login button", "expect": "User redirected to dashboard", "type": "item"}
    ]
  }'
```

### Get Test Case

**`GET /testcases/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/testcases/1" \
  -H "Token: ${TOKEN}"
```

### Update Test Case

**`PUT /testcases/:id`**

Fields: `title`, `pri`, `story`, `type`, `stage`, `product`, `module`, `branch`, `precondition`, `script`, `steps`.

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/testcases/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"title": "Login with valid credentials (updated)", "pri": 2}'
```

### Delete Test Case

**`DELETE /testcases/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/testcases/1" \
  -H "Token: ${TOKEN}"
```

---

## Test Suites

### List Test Suites

**`GET /testsuites`** or **`GET /products/:id/testsuites`**

| Param | Type | Description |
|---|---|---|
| product | int | Product ID |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/testsuites" \
  -H "Token: ${TOKEN}"
```

### Create Test Suite

**`POST /testsuites`** or **`POST /products/:id/testsuites`**

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Suite name |
| type | string | No | Suite type |
| desc | string | No | Description |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/testsuites" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Smoke Tests", "desc": "Basic smoke test suite"}'
```

### Get Test Suite

**`GET /testsuites/:id`** — Returns suite with its test cases.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/testsuites/1" \
  -H "Token: ${TOKEN}"
```

### Delete Test Suite

**`DELETE /testsuites/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/testsuites/1" \
  -H "Token: ${TOKEN}"
```

---

## Test Tasks

### List Test Tasks

**`GET /testtasks`** or **`GET /products/:id/testtasks`** or **`GET /projects/:id/testtasks`**

| Param | Type | Description |
|---|---|---|
| product | int | Product ID |
| branch | int | Branch ID |
| status | string | `wait`, `doing`, `done`, `blocked` |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/testtasks?status=doing" \
  -H "Token: ${TOKEN}"
```

### Create Test Task

**`POST /testtasks`** or **`POST /products/:id/testtasks`**

| Field | Type | Required | Description |
|---|---|---|---|
| product | int | Yes | Product ID |
| name | string | Yes | Task name |
| begin | date | Yes | Start date |
| end | date | Yes | End date |
| execution | int | No | Execution/sprint ID |
| build | int | No | Build ID |
| owner | string | No | Owner username |
| type | string | No | Task type |
| pri | int | No | Priority |
| status | string | No | Status |
| desc | string | No | Description |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/testtasks" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 1,
    "name": "Sprint 1 Regression",
    "begin": "2025-01-10",
    "end": "2025-01-15",
    "owner": "tester1"
  }'
```

### Get Test Task

**`GET /testtasks/:id`** — Returns test task with its test cases.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/testtasks/1" \
  -H "Token: ${TOKEN}"
```

### Delete Test Task

**`DELETE /testtasks/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/testtasks/1" \
  -H "Token: ${TOKEN}"
```

---

## Test Results

### List Test Results

**`GET /testcases/:id/results`**

| Param | Type | Description |
|---|---|---|
| version | int | Case version |
| runID | int | Run ID |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/testcases/1/results" \
  -H "Token: ${TOKEN}"
```

### Submit Test Result

**`POST /testcases/:id/results`**

| Field | Type | Required | Description |
|---|---|---|---|
| testtask | int | Yes | Test task ID |
| version | int | No | Case version |
| steps | array | Yes | Step results |

Steps array — each step result:

| Field | Type | Description |
|---|---|---|
| result | string | `pass`, `fail`, `blocked`, `n/a` |
| real | string | Actual result |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/testcases/1/results" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "testtask": 1,
    "steps": [
      {"result": "pass", "real": "Login form displayed correctly"},
      {"result": "pass", "real": "Fields accepted input"},
      {"result": "fail", "real": "Redirected to error page instead of dashboard"}
    ]
  }'
```
