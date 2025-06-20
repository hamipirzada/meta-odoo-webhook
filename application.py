from flask import Flask, request, jsonify
import requests
import json
import hmac
import hashlib
import os

app = Flask(__name__)

# Configuration - Environment variables from Vercel
META_ACCESS_TOKEN = os.environ.get('META_ACCESS_TOKEN')
META_APP_SECRET = os.environ.get('META_APP_SECRET')
META_APP_ID = os.environ.get('META_APP_ID')
ODOO_URL = os.environ.get('ODOO_URL')
ODOO_DB = os.environ.get('ODOO_DB')
ODOO_USERNAME = os.environ.get('ODOO_USERNAME')
ODOO_API_KEY = os.environ.get('ODOO_API_KEY')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', '2a19a7a9136d04ba')

def verify_signature(payload, signature):
    """Verify webhook signature"""
    if not signature or not META_APP_SECRET:
        return False
    
    expected_signature = 'sha256=' + hmac.new(
        META_APP_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

def get_long_lived_token():
    """Get a long-lived access token"""
    if not META_APP_ID or not META_APP_SECRET or not META_ACCESS_TOKEN:
        return None
        
    url = f"https://graph.facebook.com/v23.0/oauth/access_token"
    params = {
        'grant_type': 'fb_exchange_token',
        'client_id': META_APP_ID,
        'client_secret': META_APP_SECRET,
        'fb_exchange_token': META_ACCESS_TOKEN
    }
    
    try:
        response = requests.get(url, params=params, timeout=8)
        if response.status_code == 200:
            data = response.json()
            return data.get('access_token')
        else:
            print(f"❌ Failed to get long-lived token: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception getting long-lived token: {str(e)}")
        return None

def fetch_lead_data(leadgen_id):
    """Fetch full lead data from Meta API with token refresh"""
    print(f"🔑 Using token: {META_ACCESS_TOKEN[:20]}..." if META_ACCESS_TOKEN else "❌ NO TOKEN SET!")
    
    if not META_ACCESS_TOKEN:
        print("❌ META_ACCESS_TOKEN is empty or not set!")
        return None
    
    url = f"https://graph.facebook.com/v23.0/{leadgen_id}"
    params = {
        'access_token': META_ACCESS_TOKEN,
        'fields': 'id,created_time,field_data'
    }
    
    print(f"🌐 Fetching lead data from: {url}")
    
    try:
        response = requests.get(url, params=params, timeout=8)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            # Token expired, try to refresh
            print("🔄 Token expired, attempting to refresh...")
            new_token = get_long_lived_token()
            if new_token:
                print("✅ Token refreshed successfully")
                params['access_token'] = new_token
                response = requests.get(url, params=params, timeout=8)
                if response.status_code == 200:
                    return response.json()
            
            print("❌ Failed to refresh token")
            return None
        else:
            print(f"❌ Error fetching lead from Graph API: {response.status_code}")
            print(f"Response content: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception fetching lead: {str(e)}")
        return None

def create_lead_direct(odoo_lead_data):
    """Create lead in Odoo directly using API key"""
    
    print("📝 Creating lead in Odoo directly...")
    
    if not ODOO_URL or not ODOO_API_KEY:
        print("❌ Odoo configuration missing")
        return None
    
    create_url = f"{ODOO_URL}/jsonrpc"
    create_data = {
        'jsonrpc': '2.0',
        'method': 'call',
        'params': {
            'service': 'object',
            'method': 'execute_kw',
            'args': [
                ODOO_DB,
                2,  # Using a default UID (assuming admin user ID is 2)
                ODOO_API_KEY,
                'crm.lead',
                'create',
                [odoo_lead_data]
            ]
        },
        'id': 1
    }
    
    try:
        response = requests.post(create_url, json=create_data, timeout=8)
        result = response.json()
        
        print("📥 Create response:", json.dumps(result, indent=2))
        
        if 'result' in result and result['result']:
            lead_id = result['result']
            print(f"✅ Lead created successfully! ID: {lead_id}")
            return lead_id
        else:
            print("❌ Failed to create lead:", result.get('error', 'Unknown error'))
            return None
            
    except Exception as e:
        print(f"❌ Exception during Odoo operation: {str(e)}")
        return None

@app.route('/', methods=['GET', 'POST'])
def handle_webhook():
    """Handle both GET (verification) and POST (webhook) requests at root"""
    
    if request.method == 'GET':
        # Check if it's a webhook verification request
        mode = request.args.get('hub.mode')
        if mode == 'subscribe':
            # Webhook verification
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')

            print("🔍 Webhook verification requested")
            print(f"Mode: {mode}, Token: {token}, Challenge: {challenge}")

            if token == VERIFY_TOKEN:
                print("✅ Webhook verified")
                return challenge, 200
            else:
                print("❌ Webhook verification failed")
                return 'Failed verification', 403
        else:
            # Regular GET request - return status
            return jsonify({
                "status": "OK", 
                "message": "Meta to Odoo Webhook Server",
                "endpoints": {
                    "webhook": "/webhook",
                    "test": "/test", 
                    "test_odoo": "/test-odoo"
                }
            })
    
    elif request.method == 'POST':
        # Webhook data processing
        print("\n🔔 WEBHOOK RECEIVED!")
        print("=" * 50)
        print("Headers:", dict(request.headers))
        
        try:
            raw_data = request.get_data()
            print("Raw Payload:", raw_data.decode('utf-8'))
            
            # Signature verification (disabled for debugging)
            signature = request.headers.get('X-Hub-Signature-256')
            # if not verify_signature(raw_data, signature):
            #     print("❌ Invalid signature")
            #     return 'Invalid signature', 403

            data = request.get_json()
            print("📦 Parsed JSON:", json.dumps(data, indent=2))

            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('field') == 'leadgen':
                        leadgen_id = change['value']['leadgen_id']
                        form_id = change['value']['form_id']
                        page_id = change['value']['page_id']

                        print(f"🔗 Processing lead: leadgen_id={leadgen_id}, form_id={form_id}")

                        lead_data = fetch_lead_data(leadgen_id)

                        if lead_data:
                            print("✅ Lead data fetched successfully!")
                            print("Lead details:", json.dumps(lead_data, indent=2))
                            
                            # Parse Meta lead data
                            field_data = {item['name']: item['values'][0] for item in lead_data.get('field_data', [])}
                            print("📊 Parsed field data:", field_data)
                            
                            # Map Meta fields to Odoo fields
                            odoo_lead_data = {
                                'name': field_data.get('full_name', field_data.get('full name', 'Meta Lead')),
                                'email_from': field_data.get('email', ''),
                                'phone': field_data.get('phone_number', ''),
                                'type' : 'opportunity',
                                'stage_id': 1,
				"team_id"  : 1,  
                                'description': f"Lead from Meta Form ID: {form_id}\nCreated: {lead_data.get('created_time', '')}\n\nAdditional Info:\n" + 
                                              f"Business Type: {field_data.get('what_type_of_business_do_you_run?', 'N/A')}\n" +
                                              f"Role: {field_data.get('what_is_your_role_within_the_company?', 'N/A')}\n" +
                                              f"Demo Interest: {field_data.get('can_i_book_a_demo?', 'N/A')}",
                            }
                            
                            # Remove empty fields
                            odoo_lead_data = {k: v for k, v in odoo_lead_data.items() if v}
                            print("🎯 Odoo lead data:", odoo_lead_data)
                            
                            # Create lead in Odoo
                            result = create_lead_direct(odoo_lead_data)
                            if result:
                                print(f"🎉 SUCCESS! Lead created in Odoo with ID: {result}")
                            else:
                                print("❌ Failed to create lead in Odoo")
                        else:
                            print("⚠️ Failed to fetch lead data from Facebook")

            print("=" * 50)
            return 'OK', 200

        except Exception as e:
            print("❌ Exception in webhook handler:", str(e))
            import traceback
            traceback.print_exc()
            return "Error", 500

@app.route('/webhook', methods=['GET', 'POST'])
def webhook_endpoint():
    """Dedicated webhook endpoint"""
    return handle_webhook()

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify server is running"""
    return jsonify({
        "status": "OK", 
        "message": "Webhook server is running on Vercel",
        "odoo_url": ODOO_URL,
        "odoo_db": ODOO_DB,
        "meta_token_set": bool(META_ACCESS_TOKEN),
        "webhook_url": request.host_url + "webhook"
    })

@app.route('/test-odoo', methods=['GET'])
def test_odoo():
    """Test Odoo connection manually"""
    print("🧪 Testing Odoo connection...")
    
    test_lead_data = {
        'name': 'Test Lead from Vercel Webhook',
        'email_from': 'test@example.com',
        'phone': '+1234567890',
        'description': 'This is a test lead created manually from Vercel'
    }
    
    result = create_lead_direct(test_lead_data)
    
    if result:
        return jsonify({"status": "success", "lead_id": result, "message": "Test lead created successfully"})
    else:
        return jsonify({"status": "error", "message": "Failed to create test lead"}), 500

# For local development
if __name__ == '__main__':
    app.run(host='0.0.0.0' ,debug=True, port=8000)
