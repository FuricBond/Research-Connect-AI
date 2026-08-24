# Opportunity & System API Documentation

Base URL in development:

```text
http://localhost:8000
```

## System Health

### `GET /api/health`
Returns system status.

**Response:**
```json
{
  "status": "ok"
}
```

---

## Opportunity Endpoints

### `GET /api/opportunities`
List opportunities with filtering, full-text search, deadline filtering, sorting, and pagination.

**Query Parameters:**
- `search` (optional string): Case-insensitive search on `title`, `summary`, and `description`.
- `opportunity_type` (optional string enum): `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, `SPECIAL_ISSUE`.
- `status` (optional string enum): `ACTIVE`, `EXPIRED`, `ARCHIVED`, `DRAFT`, `UNVERIFIED` (default: `ACTIVE` and `UNVERIFIED`).
- `delivery_mode` (optional string enum): `ONLINE`, `OFFLINE`, `HYBRID`.
- `source_id` (optional UUID): Filter by source provider UUID.
- `upcoming` (optional boolean, default `false`): Filter for opportunities whose `submission_deadline` is in the future.
- `sort` (optional string enum, default `newest`): `newest`, `deadline`, `title`.
- `page` (optional integer, $\ge 1$, default `1`): Page number (1-indexed).
- `page_size` (optional integer, $1 \le N \le 100$, default `20`): Items per page.

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "title": "International Conference on Advanced Computer Science",
      "opportunity_type": "CONFERENCE",
      "publisher": null,
      "organizer": null,
      "summary": null,
      "delivery_mode": "OFFLINE",
      "location": "Vienna, Austria",
      "submission_deadline": "2026-08-22T00:00:00Z",
      "event_start_date": "2026-10-24",
      "event_end_date": "2026-10-25",
      "indexing": null,
      "website_url": null,
      "submission_url": null,
      "is_predatory_flag": false,
      "risk_score": 0.0,
      "status": "ACTIVE",
      "created_at": "2026-08-24T00:00:00Z",
      "updated_at": "2026-08-24T00:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

---

### `GET /api/opportunities/{opportunity_id}`
Retrieve complete metadata for a single opportunity by UUID.

**Path Parameters:**
- `opportunity_id` (UUID): Unique opportunity identifier.

**Response (200 OK):**
Returns `OpportunityRead` object containing all metadata including `description`, `slug`, `series_name`, `edition`, `notification_date`, `camera_ready_deadline`, `apc_or_fee`, `risk_reasons`, and `source_id`.

**Errors:**
- `404 Not Found`: Opportunity does not exist.
- `422 Unprocessable Entity`: Invalid UUID format.
