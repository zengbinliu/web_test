# Tasks

## Table of Contents
- [List Tasks](#list-tasks)
- [Create Task](#create-task)
- [Get Task](#get-task)
- [Update Task](#update-task)
- [Delete Task](#delete-task)
- [Start Task](#start-task)
- [Finish Task](#finish-task)
- [Close Task](#close-task)
- [Pause Task](#pause-task)
- [Restart Task](#restart-task)
- [Assign Task](#assign-task)
- [Activate Task](#activate-task)
- [Record Estimate](#record-estimate)
- [Batch Create Tasks](#batch-create-tasks)
- [Create Sub-Task](#create-sub-task)

---

## List Tasks

**`GET /tasks`** or **`GET /executions/:id/tasks`**

| Param | Type | Description |
|---|---|---|
| execution | int | Execution/sprint ID |
| status | string | `wait`, `doing`, `done`, `pause`, `cancel`, `closed` |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/executions/1/tasks?status=doing" \
  -H "Token: ${TOKEN}"
```

---

## Create Task

**`POST /tasks`** or **`POST /executions/:id/tasks`**

| Field | Type | Required | Description |
|---|---|---|---|
| execution | int | Yes | Execution/sprint ID |
| name | string | Yes | Task name |
| type | string | No | `design`, `devel`, `test`, `study`, `discuss`, `ui`, `affair`, `misc` |
| assignedTo | string | No | Assigned username |
| estimate | float | No | Estimated hours |
| desc | string | No | Description (HTML) |
| pri | int | No | Priority 1-4 |
| module | int | No | Module ID |
| story | int | No | Related story ID |
| estStarted | date | No | Estimated start date |
| deadline | date | No | Deadline |
| mailto | string | No | Notify users |
| color | string | No | Color code |
| parent | int | No | Parent task ID (for sub-tasks) |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/executions/1/tasks" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "execution": 1,
    "name": "Implement password reset API",
    "type": "devel",
    "assignedTo": "dev1",
    "estimate": 8,
    "pri": 2,
    "story": 10,
    "estStarted": "2025-01-15",
    "deadline": "2025-01-17"
  }'
```

---

## Get Task

**`GET /tasks/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/tasks/5" \
  -H "Token: ${TOKEN}"
```

---

## Update Task

**`PUT /tasks/:id`**

Same fields as Create (all optional).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/tasks/5" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"estimate": 12, "deadline": "2025-01-20"}'
```

---

## Delete Task

**`DELETE /tasks/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/tasks/5" \
  -H "Token: ${TOKEN}"
```

---

## Start Task

**`POST /tasks/:id/start`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | No | Assign to username |
| consumed | float | No | Hours already consumed |
| left | float | No | Hours remaining |
| comment | string | No | Comment |
| realStarted | datetime | No | Actual start date |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/start" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"realStarted": "2025-01-15 09:00:00", "left": 8}'
```

---

## Finish Task

**`POST /tasks/:id/finish`**

| Field | Type | Required | Description |
|---|---|---|---|
| currentConsumed | float | Yes | Hours consumed in this session |
| realStarted | datetime | Yes | Actual start date |
| finishedDate | datetime | Yes | Finish date |
| assignedTo | string | No | Assign to (for review) |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/finish" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "currentConsumed": 6,
    "realStarted": "2025-01-15 09:00:00",
    "finishedDate": "2025-01-16 17:00:00",
    "comment": "Implementation complete, ready for review"
  }'
```

---

## Close Task

**`POST /tasks/:id/close`**

| Field | Type | Required | Description |
|---|---|---|---|
| comment | string | No | Closing comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/close" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Verified and closed"}'
```

---

## Pause Task

**`POST /tasks/:id/pause`**

| Field | Type | Required | Description |
|---|---|---|---|
| comment | string | No | Reason for pausing |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/pause" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Blocked by dependency on task #3"}'
```

---

## Restart Task

**`POST /tasks/:id/restart`**

| Field | Type | Required | Description |
|---|---|---|---|
| consumed | float | Yes | Total hours consumed so far |
| left | float | Yes | Hours remaining |
| assignedTo | string | No | Assign to username |
| realStarted | datetime | No | Restart date |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/restart" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"consumed": 4, "left": 6, "comment": "Dependency resolved"}'
```

---

## Assign Task

**`POST /tasks/:id/assignto`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | Yes | Target username |
| comment | string | No | Comment |
| left | float | No | Hours remaining |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/assignto" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev2", "left": 4}'
```

---

## Activate Task

**`POST /tasks/:id/active`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | No | Assign to username |
| left | float | No | Hours remaining |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/active" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev1", "left": 4}'
```

---

## Record Estimate

**`GET /tasks/:id/estimate`** — Get effort records.
**`POST /tasks/:id/estimate`** — Add effort record.

| Field | Type | Required | Description |
|---|---|---|---|
| date | date | No | Work date |
| consumed | float | No | Hours consumed |
| left | float | No | Hours remaining |
| work | string | No | Work description |

```bash
# Get effort records
curl -s "${ZENTAO_URL}/api.php/v1/tasks/5/estimate" \
  -H "Token: ${TOKEN}"

# Add effort
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/estimate" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"date": "2025-01-15", "consumed": 3, "left": 5, "work": "API design and coding"}'
```

---

## Batch Create Tasks

**`POST /tasks/batchCreate`** or **`POST /executions/:id/tasks/batchCreate`**

| Field | Type | Required | Description |
|---|---|---|---|
| execution | int | Yes | Execution/sprint ID |
| tasks | array | Yes | Array of task objects |

Each task object:

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Task name |
| type | string | No | Task type |
| module | int | No | Module ID |
| parent | int | No | Parent task ID |
| color | string | No | Color code |
| estimate | float | No | Estimated hours |
| estStarted | date | No | Estimated start date |
| deadline | date | No | Deadline |
| desc | string | No | Description |
| pri | int | No | Priority |
| story | int | No | Related story ID |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/executions/1/tasks/batchCreate" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "execution": 1,
    "tasks": [
      {"name": "Design API schema", "type": "design", "estimate": 4},
      {"name": "Implement endpoints", "type": "devel", "estimate": 8},
      {"name": "Write unit tests", "type": "test", "estimate": 4}
    ]
  }'
```

---

## Create Sub-Task

**`POST /tasks/:parentId/component`** — Create a sub-task under a parent task.

| Field | Type | Required | Description |
|---|---|---|---|
| name | string | Yes | Sub-task name |
| parent | int | Yes | Parent task ID |
| type | string | No | Task type |
| assignedTo | string | No | Assigned username |
| estimate | float | No | Estimated hours |
| color | string | No | Color code |
| story | int | No | Related story |
| module | int | No | Module ID |
| pri | int | No | Priority |
| desc | string | No | Description |
| estStarted | date | No | Estimated start |
| deadline | date | No | Deadline |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/tasks/5/component" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Implement email sending",
    "parent": 5,
    "type": "devel",
    "assignedTo": "dev1",
    "estimate": 3
  }'
```
