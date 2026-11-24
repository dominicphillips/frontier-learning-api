// Field shapes shown next to each endpoint. Values are type names, not observed data.
// Aggregate /v1/* shapes; provider routes omit provider and use plain category slugs.

export const RESOURCE_SHAPE = `{
  "id": "string",
  "provider": "openai | claude | gemini",
  "title": "string",
  "url": "string",
  "kind": "string",
  "categoryIds": ["provider:slug"],
  "audiences": ["string"],
  "tags": ["string"],
  "summary": "string | null",
  "level": "string | null",
  "duration": {
    "courseMinutes": "number | null",
    "pathMinutes": "number | null",
    "videoSeconds": "number | null"
  },
  "detail": {
    "audience": "string | null",
    "prerequisites": ["string"],
    "objectives": ["string"],
    "sections": ["…"]
  },
  "media": ["…"],
  "artwork": {
    "url": "string",
    "alt": "string | null",
    "sourceUrl": "string"
  },
  "provenance": {
    "sourceUrls": ["string"],
    "fetchedAt": "string",
    "contentHash": "string",
    "method": "manual | fixture | crawler | managed-agent"
  }
}`

export const LIST_SHAPE = `{
  "items": ["Resource"],
  "nextCursor": "string | null",
  "total": "number",
  "snapshotId": "string"
}`

export const LEARNING_PATH_LIST_SHAPE = `{
  "items": [
    {
      "id": "string",
      "provider": "openai | claude | gemini",
      "title": "string",
      "url": "string",
      "kind": "learning-path",
      "categoryIds": ["provider:slug"],
      "audiences": ["string"],
      "tags": ["string"],
      "summary": "string | null",
      "level": "string | null",
      "duration": {
        "courseMinutes": "number | null",
        "pathMinutes": "number | null",
        "videoSeconds": "number | null"
      },
      "stepCount": "number",
      "steps": [
        {
          "position": "number",
          "sectionTitle": "string | null",
          "title": "string",
          "url": "string",
          "kind": "string",
          "resourceId": "string | null",
          "summary": "string | null",
          "level": "string | null",
          "duration": "Duration | null",
          "context": "string | null"
        }
      ],
      "artwork": "Artwork | null",
      "provenance": "Provenance"
    }
  ],
  "nextCursor": "string | null",
  "total": "number",
  "snapshotId": "string"
}`

export const CATEGORIES_SHAPE = `{
  "items": [
    {
      "id": "provider:slug",
      "provider": "openai | claude | gemini",
      "slug": "string",
      "label": "string",
      "count": "number"
    }
  ],
  "snapshotId": "string"
}`

export const PROVIDERS_SHAPE = `{
  "items": [
    {
      "id": "openai | claude | gemini",
      "label": "string",
      "sourceUrl": "string",
      "resourcePrefix": "oa_ | ca_ | ga_",
      "kinds": ["string"],
      "status": "Status"
    }
  ]
}`
