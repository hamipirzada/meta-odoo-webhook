import json
import os
import requests

# Configuration
META_ACCESS_TOKEN = os.environ.get('META_ACCESS_TOKEN')
META_APP_SECRET = os.environ.get('META_APP_SECRET')
META_APP_ID = os.environ.get('META_APP_ID')
ODOO_URL = os.environ.get('ODOO_URL')
ODOO_DB = os.environ.get('ODOO_DB')
ODOO_USERNAME = os.environ.get('ODOO_USERNAME')
ODOO_API_KEY = os.environ.get('ODOO_API_KEY')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', '2a19a7a9136d04ba')

def create_lead_direct(odoo_lead_data):
    """Create lead in Odoo directly using API key"""
    if not ODOO_URL or not ODOO_API_KEY:
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
        
        if 'result' in result and result['result']:
            return result['result']
        return None
    except:
        return None

def fetch_lead_data(leadgen_id):
    """Fetch lead data from Meta API"""
    if not META_ACCESS_TOKEN:
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
        return None
    except:
        return None

def process_webhook(body):
    """Process webhook data"""
    try:
        data = json.loads(body)
        
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                if change.get('field') == 'leadgen':
                    leadgen_id = change['value']['leadgen_id']
                    form_id = change['value']['form_id']
                    
                    lead_data = fetch_lead_data(leadgen_id)
                    
                    if lead_data:
                        field_data = {item['name']: item['values'][0] for item in lead_data.get('field_data', [])}
                        
                        odoo_lead_data = {
                            'name': field_data.get('full_name', field_data.get('full name', 'Meta Lead')),
                            'email_from': field_data.get('email', ''),
                            'phone': field_data.get('phone_number', ''),
                            'description': f"Lead from Meta Form ID: {form_id}\nCreated: {lead_data.get('created_time', '')}"
                        }
                        
                        odoo_lead_data = {k: v for k, v in odoo_lead_data.items() if v}
                        create_lead_direct(odoo_lead_data)
        
        return {
            'statusCode': 200,
            'body': 'OK'
        }
    except:
        return {
            'statusCode': 500,
            'body': 'Error'
        }

def handler(event, context):
    """Main Vercel handler"""
    try:
        # Get method and path
        method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method', 'GET'))
        path = event.get('path', event.get('rawPath', '/'))
        query = event.get('queryStringParameters') or {}
        body = event.get('body', '')
        
        # Handle different endpoints
        if method == 'GET':
            if '/test-odoo' in path:
                # Test Odoo connection
                test_lead_data = {
                    'name': 'Test Lead from Vercel',
                    'email_from': 'test@example.com',
                    'phone': '+1234567890',
                    'description': 'Test lead from webhook'
                }
                
                result = create_lead_direct(test_lead_data)
                
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        "status": "success" if result else "error",
                        "lead_id": result,
                        "message": "Test lead created" if result else "Failed to create lead"
                    })
                }
            
            elif '/test' in path:
                # Test endpoint
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        "status": "OK",
                        "message": "Webhook server running on Vercel",
                        "environment_check": {
                            "META_ACCESS_TOKEN": "✅ Set" if META_ACCESS_TOKEN else "❌ Missing",
                            "META_APP_SECRET": "✅ Set" if META_APP_SECRET else "❌ Missing", 
                            "META_APP_ID": "✅ Set" if META_APP_ID else "❌ Missing",
                            "ODOO_URL": "✅ Set" if ODOO_URL else "❌ Missing",
                            "ODOO_API_KEY": "✅ Set" if ODOO_API_KEY else "❌ Missing",
                            "VERIFY_TOKEN": "✅ Set" if VERIFY_TOKEN else "❌ Missing"
                        }
                    })
                }
            
            else:
                # Webhook verification or default
                mode = query.get('hub.mode')
                if mode == 'subscribe':
                    token = query.get('hub.verify_token')
                    challenge = query.get('hub.challenge')
                    
                    if token == VERIFY_TOKEN:
                        return {
                            'statusCode': 200,
                            'body': challenge
                        }
                    else:
                        return {
                            'statusCode': 403,
                            'body': 'Failed verification'
                        }
                else:
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({
                            "status": "OK",
                            "message": "Meta to Odoo Webhook Server",
                            "endpoints": ["/test", "/test-odoo", "/webhook"]
                        })
                    }
        
        elif method == 'POST':
            # Handle webhook POST
            return process_webhook(body)
        
        else:
            return {
                'statusCode': 405,
                'body': 'Method Not Allowed'
            }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
