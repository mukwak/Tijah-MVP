# Tijah Alpha Setup

This app runs locally with SQLite by default. For alpha testing from anywhere, deploy the app to a public HTTPS host and set `DATABASE_URL` to a hosted Postgres database.

## Free Database

Use a free Postgres database from Neon or Supabase.

1. Create a new Postgres project.
2. Copy the pooled connection string.
3. Set it as `DATABASE_URL` in your app host.
4. Keep `DB_PATH` unset or leave it as the local default.

The app creates its tables on startup.

## App Hosting

Deploy with any HTTPS Python host that supports environment variables. Render is the simplest path for an alpha:

1. Connect this GitHub repository.
2. Use Python 3.11.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Set the environment variables from `.env.example`.

## WhatsApp Webhook

In Meta's WhatsApp app settings:

1. Callback URL: `https://your-alpha-domain.com/webhook`
2. Verify token: the same value as `META_VERIFY_TOKEN`
3. App secret: set as `META_APP_SECRET`
4. Subscribe to messages.

Keep `VERIFY_WEBHOOK_SIGNATURE=true` for alpha. Set it to `false` only for short local tunnel tests where Meta signatures are not available.

## Required Environment Variables

- `META_ACCESS_TOKEN`
- `META_PHONE_NUMBER_ID`
- `META_VERIFY_TOKEN`
- `META_APP_SECRET`
- `GOOGLE_AI_API_KEY`
- `OPENAI_API_KEY`
- `DATABASE_URL`
- `BASE_URL`

## Local Testing

Leave `DATABASE_URL` blank and run:

```bash
python test_local.py
```

For a public local tunnel, run the app locally, expose port `8000` with a tunnel, and set Meta's callback URL to the tunnel `/webhook` URL.
