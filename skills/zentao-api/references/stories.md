# Stories

## Table of Contents
- [List Stories](#list-stories)
- [Create Story](#create-story)
- [Get Story](#get-story)
- [Update Story](#update-story)
- [Delete Story](#delete-story)
- [Assign Story](#assign-story)
- [Close Story](#close-story)
- [Activate Story](#activate-story)
- [Change Story](#change-story)
- [Review Story](#review-story)
- [Submit for Review](#submit-for-review)
- [Recall Story](#recall-story)
- [Story Grades](#story-grades)
- [Reviewer Required Check](#reviewer-required-check)
- [Record Estimate](#record-estimate)

---

## List Stories

**`GET /stories`** or **`GET /products/:id/stories`**

| Param | Type | Description |
|---|---|---|
| product | int | Product ID (required for `/stories`) |
| status | string | `draft`, `active`, `changed`, `reviewing`, `closed` |
| order | string | Sort field |
| limit | int | Items per page |
| page | int | Page number |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/products/1/stories?status=active&limit=20" \
  -H "Token: ${TOKEN}"
```

---

## Create Story

**`POST /stories`** or **`POST /products/:id/stories`**

| Field | Type | Required | Description |
|---|---|---|---|
| product | int | Yes | Product ID |
| title | string | Yes | Story title |
| module | int | No | Module ID |
| plan | int | No | Plan ID |
| spec | string | No | Story spec/description (HTML) |
| verify | string | No | Verification criteria (HTML) |
| pri | int | No | Priority 1-4 |
| estimate | float | No | Estimated hours |
| type | string | No | `story` (default), `requirement`, `epic` |
| category | string | No | Category |
| assignedTo | string | No | Assigned username |
| reviewer | string | No | Reviewer username(s) |
| source | string | No | Source of the story |
| sourceNote | string | No | Source note |
| mailto | string | No | Notify users |
| keywords | string | No | Keywords |
| needNotReview | bool | No | Skip review process |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/products/1/stories" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 1,
    "title": "User can reset password via email",
    "spec": "<p>As a user, I want to reset my password via email link</p>",
    "verify": "<p>Verify reset email is sent within 1 minute</p>",
    "pri": 2,
    "estimate": 8,
    "assignedTo": "dev1"
  }'
```

---

## Get Story

**`GET /stories/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/stories/10" \
  -H "Token: ${TOKEN}"
```

---

## Update Story

**`PUT /stories/:id`**

Same fields as Create (all optional).

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/stories/10" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"pri": 1, "estimate": 12}'
```

---

## Delete Story

**`DELETE /stories/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/stories/10" \
  -H "Token: ${TOKEN}"
```

---

## Assign Story

**`POST /stories/:id/assign`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | Yes | Target username |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/assign" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev2", "comment": "Please start implementation"}'
```

---

## Close Story

**`POST /stories/:id/close`**

| Field | Type | Required | Description |
|---|---|---|---|
| closedReason | string | Yes | `done`, `subdivided`, `duplicate`, `postponed`, `willnotdo`, `bydesign` |
| duplicateStory | int | No | Duplicate story ID (when reason=`duplicate`) |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/close" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"closedReason": "done", "comment": "Delivered in Sprint 3"}'
```

---

## Activate Story

**`POST /stories/:id/active`**

| Field | Type | Required | Description |
|---|---|---|---|
| assignedTo | string | No | Assign to username |
| status | string | No | Status |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/active" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "dev1", "comment": "Re-opening for changes"}'
```

---

## Change Story

**`POST /stories/:id/change`**

| Field | Type | Required | Description |
|---|---|---|---|
| title | string | Yes | Updated title |
| spec | string | No | Updated spec (HTML) |
| verify | string | No | Updated verification |
| reviewer | string | No | Reviewer username(s) |
| comment | string | No | Comment |
| needNotReview | bool | No | Skip review |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/change" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "User can reset password via email or SMS",
    "spec": "<p>Updated spec with SMS option</p>",
    "comment": "Added SMS reset option per PM request"
  }'
```

---

## Review Story

**`POST /stories/:id/review`**

| Field | Type | Required | Description |
|---|---|---|---|
| result | string | Yes | `pass`, `reject`, `revert`, `clarify` |
| reviewedDate | date | No | Review date |
| closedReason | string | No | Reason (when result=`reject`) |
| pri | int | No | Priority |
| estimate | float | No | Estimated hours |
| comment | string | No | Comment |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/review" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"result": "pass", "comment": "LGTM"}'
```

---

## Submit for Review

**`POST /stories/:id/submitreview`**

| Field | Type | Required | Description |
|---|---|---|---|
| reviewer | string | No | Reviewer username(s) |
| needNotReview | bool | No | Skip review if true |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/submitreview" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "pm1"}'
```

---

## Recall Story

**`DELETE /stories/:id/recall`**

| Param | Type | Description |
|---|---|---|
| type | string | `story`, `requirement`, `epic` |

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/stories/10/recall?type=story" \
  -H "Token: ${TOKEN}"
```

---

## Story Grades

**`GET /storygrades`**

| Param | Type | Description |
|---|---|---|
| type | string | `story`, `requirement`, `epic` |
| status | string | Status filter |

```bash
curl -s "${ZENTAO_URL}/api.php/v1/storygrades?type=story" \
  -H "Token: ${TOKEN}"
```

---

## Reviewer Required Check

**`GET /storyreviewerrequired/:type`**

Check if reviewer is required for a story type.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/storyreviewerrequired/story" \
  -H "Token: ${TOKEN}"
```

Response: `{"storyType": "story", "reviewerRequired": true}`

---

## Record Estimate

**`GET /stories/:id/estimate`** — Get effort records.
**`POST /stories/:id/estimate`** — Add effort record. Non-open edition only.

| Field | Type | Required | Description |
|---|---|---|---|
| id | int | No | Effort ID (for update) |
| dates | date | No | Work date |
| consumed | float | No | Hours consumed |
| objectType | string | No | Object type |
| objectID | int | No | Object ID |
| work | string | No | Work description |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/stories/10/estimate" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"dates": "2025-01-15", "consumed": 4, "work": "Analysis and design"}'
```
