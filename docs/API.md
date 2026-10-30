# Conversation search and pagination

All mail endpoints retain the deployment's existing authentication and account
visibility rules. The public landing does not expose private mail APIs.

`GET /api/messages` lists conversations, not every message inside each thread.
Its filters are `view`, `category`, `account` and `search`. Use `view=all` when
checking history across inbox, archive and sent mail. Search includes stored
recipients as well as sender, subject and body; it is case-insensitive.

For complete results, supply `limit` between 1 and 500. Pages are ordered by
descending date and id, independently of pinned status. The response contains
`messages` and `next`. When `next` is an object, send all of its fields as query
parameters to the same endpoint. It preserves the selected filters, page size,
and the `before_date`/`before_id` cursor. Stop when `next` is `null`.

```python
query = {"view": "all", "search": recipient, "limit": 200}
while query:
    page = session.get(origin + "/api/messages", params=query).json()
    inspect_conversations(page["messages"])
    query = page["next"]
```

Invalid page sizes, non-finite dates and incomplete cursors return HTTP 422.
A page without a match is an empty `messages` array with `next: null`.
New arrivals appear on a refreshed first page; they do not shift an existing
cursor and repeat older pages.

Without `limit` or a cursor, the endpoint preserves the existing pinned-first
visible list, capped at 100 conversations, and returns only `messages`.
That default is not a complete archive export. `limit` is no longer silently
ignored. Offset/page-number pagination is not supported.

The existing `GET /api/client/messages` feed remains available for a complete
unfiltered catalogue: pages contain 200 conversations and its `next` object
contains the `before_date`/`before_id` cursor.

To examine all messages inside a returned conversation, use
`GET /api/messages/{id}/thread?lazy=true` for metadata, and fetch bodies or
attachments only when needed. A conversation summary or sent flag alone does
not establish successful delivery or the absence of a later bounce or reply.

# HTML drafts

`PUT /api/drafts` accepts an optional `html` field next to the plain-text
`body`. When `html` is non-empty, sending (immediate or scheduled, SMTP or
Gmail) builds a `multipart/alternative` message: `body` becomes the
`text/plain` part and `html` the `text/html` part, so clients render the HTML
and fall back to text. Drafts without `html` are sent as `text/plain` exactly
as before. The web and iOS composers do not edit `html`; saving such a draft
from a composer drops it.
