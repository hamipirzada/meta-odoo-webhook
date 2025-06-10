# Meta to Odoo Webhook

A webhook service that receives Facebook Lead Ads and automatically creates leads in Odoo CRM.

## Features

- ✅ Receives Facebook Lead Ads webhooks
- ✅ Fetches full lead data from Meta Graph API
- ✅ Creates leads in Odoo CRM automatically
- ✅ Token refresh handling
- ✅ Deployed on Vercel (serverless)

## Setup

### 1. Deploy to Vercel

1. Fork/clone this repository
2. Connect to Vercel
3. Deploy

### 2. Environment Variables

Add these in your Vercel dashboard:

```
META_ACCESS_TOKEN=your_page_access_token
META_APP_SECRET=your_app_secret
META_APP_ID=your_app_id
ODOO_URL=https://your-instance.odoo.com
ODOO_DB=your_database_name
ODOO_USERNAME=your_odoo_username
ODOO_API_KEY=your_odoo_api_key
VERIFY_TOKEN=your_webhook_verify_token
```

### 3. Facebook Webhook Configuration

Set your webhook URL in Facebook Developer Console:
```
https://your-app.vercel.app/api/webhook
```

## API Endpoints

- `GET /api/webhook` - Webhook verification
- `POST /api/webhook` - Receive lead webhooks
- `GET /api/test` - Test server status
- `GET /api/test-odoo` - Test Odoo connection

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run locally:
   ```bash
   python app.py
   ```

3. Use ngrok for webhook testing:
   ```bash
   ngrok http 8000
   ```

## Project Structure

```
├── app.py              # Main webhook application
├── vercel.json         # Vercel configuration
├── requirements.txt    # Python dependencies
├── .gitignore         # Git ignore rules
└── README.md          # This file
```

## Support

For issues or questions, check the Vercel logs and ensure all environment variables are set correctly.