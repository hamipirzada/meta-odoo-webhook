from flask import Flask, request, jsonify
import requests
import json
import hmac
import hashlib
import os

app = Flask(__name__)

# Configuration - Environment variables from Render
META_ACCESS_TOKEN = os.environ.get('META_ACCESS_TOKEN')
META_APP_SECRET = os.environ.get('META_APP_SECRET')
META_APP_ID = os.environ.get('META_APP_ID')
ODOO_URL = os.environ.get('ODOO_URL')
ODOO_DB = os.environ.get('ODOO_DB')
ODOO_USERNAME = os.environ.get('ODOO_USERNAME')
ODOO_API_KEY = os.environ.get('ODOO_API_KEY')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', '2a19a7a9136d04ba')

def verify_signature(payload, signature):
    if not signature or not META_APP_SECRET:
        return False
    expected_signature = 'sha256=' + hmac.new(
        META_APP_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def get_long_lived_token():
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
            return response.json().get('access_token')
        else:
            print(f"❌ Failed to get long-lived token: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception getting long-lived token: {str(e)}")
        return None

def fetch_lead_data(leadgen_id):
    if not META_ACCESS_TOKEN:
        print("❌ META_ACCESS_TOKEN is not set!")
        return None
    url = f"https://graph.facebook.com/v23.0/{leadgen_id}"
    params = {
        'access_token': META_ACCESS_TOKEN,
        'fields': 'id,created_time,field_data'
    }
    try:
        response = requests.get(url, params=params, timeout=8)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print("🔄 Token expired, trying to refresh...")
            new_token = get_long_lived_token()
            if new_token:
                params['access_token'] = new_token
                response = requests.get(url, params=params, timeout=8)
                if response.status_code == 200:
                    return response.json()
            print("❌ Token refresh failed")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception fetching lead: {str(e)}")
    return None

def create_lead_direct(odoo_lead_data):
    if not ODOO_URL or not ODOO_API_KEY:
        print("❌ Odoo config missing")
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
                2,
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
        return result.get('result')
    except Exception as e:
        print(f"❌ Odoo error: {str(e)}")
        return None

@app.route('/', methods=['GET', 'POST', 'HEAD'])
def handle_webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        if mode == 'subscribe':
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')
            if token == VERIFY_TOKEN:
                return challenge, 200
            return 'Failed verification', 403
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
        try:
            raw_data = request.get_data()
            signature = request.headers.get('X-Hub-Signature-256')
            data = request.get_json()

            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('field') == 'leadgen':
                        leadgen_id = change['value']['leadgen_id']
                        form_id = change['value']['form_id']
                        lead_data = fetch_lead_data(leadgen_id)
                        if lead_data:
                            field_data = {
                                item['name']: item['values'][0]
                                for item in lead_data.get('field_data', [])
                            }
                            odoo_lead_data = {
                                'name': field_data.get('full_name', 'Meta Lead'),
                                'email_from': field_data.get('email', ''),
                                'phone': field_data.get('phone_number', ''),
                                'type': 'opportunity',
                                'stage_id': 1,
                                'team_id': 1,
                                'description': (
                                    f"Lead from Meta Form ID: {form_id}\n"
                                    f"Created: {lead_data.get('created_time', '')}\n\n"
                                    f"Business Type: {field_data.get('what_type_of_business_do_you_run?', 'N/A')}\n"
                                    f"Role: {field_data.get('what_is_your_role_within_the_company?', 'N/A')}\n"
                                    f"Demo Interest: {field_data.get('can_i_book_a_demo?', 'N/A')}"
                                )
                            }
                            odoo_lead_data = {k: v for k, v in odoo_lead_data.items() if v}
                            create_lead_direct(odoo_lead_data)
            return 'OK', 200
        except Exception as e:
            print("❌ Exception in webhook handler:", str(e))
            return "Error", 500
    return '', 200  # Fallback for HEAD and other methods

@app.route('/webhook', methods=['GET', 'POST'])
def webhook_endpoint():
    return handle_webhook()

@app.route('/test', methods=['GET'])
def test_endpoint():
    return jsonify({
        "status": "OK",
        "message": "Webhook server is running on Render",
        "odoo_url": ODOO_URL,
        "odoo_db": ODOO_DB,
        "meta_token_set": bool(META_ACCESS_TOKEN),
        "webhook_url": request.host_url + "webhook"
    })

@app.route('/test-odoo', methods=['GET'])
def test_odoo():
    test_lead_data = {
        'name': 'Test Lead from Render',
        'email_from': 'test@example.com',
        'phone': '+1234567890',
        'description': 'Test lead created manually from Render deployment'
    }
    result = create_lead_direct(test_lead_data)
    if result:
        return jsonify({"status": "success", "lead_id": result})
    return jsonify({"status": "error", "message": "Failed to create lead"}), 500

# For local testing
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
