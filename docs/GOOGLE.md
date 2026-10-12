# Connect real Google mailboxes

Milo connects directly to Gmail API through the official Google OAuth library.
One owner-controlled web OAuth client belongs to the Milo service. Each Google
mailbox grants access separately; phones and Linux clients reuse the service's
stored accounts rather than holding Google refresh tokens themselves.

## One-time Google setup

1. Select or create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com).
3. Configure Google Auth Platform branding/audience and the Gmail permission
   `https://www.googleapis.com/auth/gmail.modify`. Milo uses this for reading,
   organizing and explicit sending; it does not request permanent deletion.
4. Create an OAuth client of type **Web application**. Register exactly the
   callback shown in Milo → Add account. For the intended Grog deployment:

   ```text
   https://milo.grooooog.space/api/oauth/google/callback
   ```

   The domain must actually be provisioned before using this redirect. For
   local development the CLI shows a loopback callback such as
   `http://127.0.0.1:8025/api/oauth/google/callback`.
5. Download the client JSON and import it in Milo → Add account. Alternatively,
   keep the JSON outside the public checkout with mode 0600 and pass its path
   through `MILO_GOOGLE_CLIENT` or `--google-client` on the service host.
6. Click **Continue with Google**, select the real account and grant Gmail
   access. Repeat for other mailboxes. The first sync begins immediately; older
   messages continue backfilling in subsequent passes.

The imported client secret and mailbox refresh tokens are encrypted with the
service vault key. They never appear in the browser API or public repository.
In the private Mac deployment the public callback only relays to the fixed
Tailscale origin. The private backend uses PKCE, browser binding and one-time
expiring state; clients need Tailscale access for the return navigation.
Reconnecting the same address retains its account identity and cached mail.
Milo → Settings → Account → Manage lets you rename or pause the mailbox. Its
Reconnect button suggests and validates that exact address, so choosing another
Google account cannot silently change the mailbox being repaired. A paused
account keeps its cache and drafts; pending label edits wait until it resumes.

## Consent mode and lasting access

While the Google project is **Testing**, add each account to its test users.
Google expires external Testing refresh tokens after seven days for Gmail
scopes. A lasting deployment requires configuring the appropriate publishing
status and audience in Google Auth Platform; Workspace policies can impose
additional restrictions. Gmail modify is a restricted scope, and a generally
available third-party application can require verification. Follow the Console's
requirements for the actual audience rather than assuming a public source
repository makes the OAuth application verified.

See Google's [web-server OAuth guide](https://developers.google.com/identity/protocols/oauth2/web-server),
[refresh-token rules](https://developers.google.com/identity/protocols/oauth2#expiration)
and [Gmail scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes).

## Live validation still required

Protocol tests exercise code exchange, PKCE, encrypted storage, token renewal,
label changes and Gmail history/backfill recovery with controlled responses.
They do not authorize a real account. After authorization, validate new-message
receipt, read/star/archive changes against Gmail, persistence after restarting
Milo and a manually confirmed reply. Sending real mail requires the owner's
explicit choice in the compose screen.
