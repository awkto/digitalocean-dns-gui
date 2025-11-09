from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flasgger import Swagger
from dotenv import load_dotenv, set_key
import os
import json
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app)

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "DigitalOcean DNS Manager API",
        "description": "API for managing DNS records in DigitalOcean",
        "version": "1.0.0",
        "contact": {
            "name": "DigitalOcean DNS Manager"
        }
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "tags": [
        {
            "name": "Health",
            "description": "Health check and status endpoints"
        },
        {
            "name": "Configuration",
            "description": "DigitalOcean configuration management"
        },
        {
            "name": "DNS Records",
            "description": "DNS record management operations"
        }
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# DigitalOcean credentials and configuration (mutable for runtime updates)
config = {
    'API_TOKEN': os.getenv('DO_API_TOKEN'),
    'DNS_ZONE': os.getenv('DO_DNS_ZONE')
}

# Legacy support - keep these for compatibility
API_TOKEN = config['API_TOKEN']
DNS_ZONE = config['DNS_ZONE']

# DigitalOcean API base URL
DO_API_BASE = "https://api.digitalocean.com/v2"

def is_config_complete():
    """Check if all required configuration is present"""
    return all([
        config.get('API_TOKEN'),
        config.get('DNS_ZONE')
    ])

def update_config(new_config):
    """Update the configuration in memory and .env file"""
    global config, API_TOKEN, DNS_ZONE
    
    config.update(new_config)
    
    # Update global variables
    API_TOKEN = config['API_TOKEN']
    DNS_ZONE = config['DNS_ZONE']
    
    # Save to .env file
    env_file = '.env'
    if not os.path.exists(env_file):
        with open(env_file, 'w') as f:
            f.write('')
    
    set_key(env_file, 'DO_API_TOKEN', config['API_TOKEN'])
    set_key(env_file, 'DO_DNS_ZONE', config['DNS_ZONE'])

# DigitalOcean API helper functions
def get_headers():
    """Get headers for DigitalOcean API requests"""
    if not config.get('API_TOKEN'):
        raise ValueError("DigitalOcean API token is not configured")
    return {
        'Authorization': f"Bearer {config['API_TOKEN']}",
        'Content-Type': 'application/json'
    }

def make_do_request(method, endpoint, data=None):
    """Make a request to DigitalOcean API"""
    url = f"{DO_API_BASE}{endpoint}"
    headers = get_headers()
    
    if method == 'GET':
        response = requests.get(url, headers=headers)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data)
    elif method == 'PUT':
        response = requests.put(url, headers=headers, json=data)
    elif method == 'DELETE':
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")
    
    return response

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint
    ---
    tags:
      - Health
    summary: Check API health status
    description: Returns the health status of the API and the configured DNS zone
    responses:
      200:
        description: API is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
            zone:
              type: string
              example: example.com
    """
    return jsonify({'status': 'healthy', 'zone': config.get('DNS_ZONE')})

@app.route('/api/config/status', methods=['GET'])
def config_status():
    """Check if DigitalOcean configuration is complete
    ---
    tags:
      - Configuration
    summary: Get configuration status
    description: Check if DigitalOcean API credentials and DNS zone are configured
    responses:
      200:
        description: Configuration status
        schema:
          type: object
          properties:
            configured:
              type: boolean
              example: true
            zone:
              type: string
              example: example.com
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        complete = is_config_complete()
        return jsonify({
            'configured': complete,
            'zone': config.get('DNS_ZONE') if complete else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration (with masked token)
    ---
    tags:
      - Configuration
    summary: Get current configuration
    description: Retrieve the current DigitalOcean API configuration (token and DNS zone)
    responses:
      200:
        description: Current configuration
        schema:
          type: object
          properties:
            api_token:
              type: string
              example: dop_v1_xxxxxxxxxxxxx
            dns_zone:
              type: string
              example: example.com
            has_token:
              type: boolean
              example: true
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        api_token = config.get('API_TOKEN', '')
        masked_token = api_token if api_token else ''

        return jsonify({
            'api_token': masked_token,
            'dns_zone': config.get('DNS_ZONE', ''),
            'has_token': bool(api_token)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save DigitalOcean configuration
    ---
    tags:
      - Configuration
    summary: Save configuration
    description: Save DigitalOcean API token and DNS zone configuration
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - api_token
            - dns_zone
          properties:
            api_token:
              type: string
              example: dop_v1_xxxxxxxxxxxxx
              description: DigitalOcean API token
            dns_zone:
              type: string
              example: example.com
              description: DNS zone/domain name
    responses:
      200:
        description: Configuration saved successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: Configuration saved successfully
            zone:
              type: string
              example: example.com
      400:
        description: Missing required fields
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        data = request.json

        # Validate required fields
        required_fields = ['api_token', 'dns_zone']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        # Update configuration
        new_config = {
            'API_TOKEN': data['api_token'],
            'DNS_ZONE': data['dns_zone']
        }

        update_config(new_config)

        return jsonify({
            'success': True,
            'message': 'Configuration saved successfully',
            'zone': config['DNS_ZONE']
        })
    except Exception as e:
        print(f"Error saving configuration: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/test', methods=['POST'])
def test_config():
    """Test DigitalOcean API credentials before saving
    ---
    tags:
      - Configuration
    summary: Test API credentials
    description: Test DigitalOcean API credentials and DNS zone connectivity before saving
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - api_token
            - dns_zone
          properties:
            api_token:
              type: string
              example: dop_v1_xxxxxxxxxxxxx
              description: DigitalOcean API token to test
            dns_zone:
              type: string
              example: example.com
              description: DNS zone to verify
    responses:
      200:
        description: Connection successful
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: Connection successful! Found 10 DNS records.
            record_count:
              type: integer
              example: 10
            zone:
              type: string
              example: example.com
      400:
        description: Missing required fields
        schema:
          type: object
          properties:
            error:
              type: string
      401:
        description: Authentication failed
        schema:
          type: object
          properties:
            error:
              type: string
              example: Authentication failed. Please check your API token.
      404:
        description: DNS zone not found
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Connection error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        data = request.json

        # Validate required fields
        required_fields = ['api_token', 'dns_zone']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        # Try to list records from the domain
        try:
            headers = {
                'Authorization': f"Bearer {data['api_token']}",
                'Content-Type': 'application/json'
            }

            response = requests.get(
                f"{DO_API_BASE}/domains/{data['dns_zone']}/records",
                headers=headers
            )

            if response.status_code == 200:
                records = response.json().get('domain_records', [])
                record_count = len(records)

                return jsonify({
                    'success': True,
                    'message': f'Connection successful! Found {record_count} DNS records.',
                    'record_count': record_count,
                    'zone': data['dns_zone']
                })
            elif response.status_code == 401:
                return jsonify({'error': 'Authentication failed. Please check your API token.'}), 401
            elif response.status_code == 404:
                return jsonify({'error': f'DNS zone "{data["dns_zone"]}" not found in your DigitalOcean account.'}), 404
            else:
                error_msg = response.json().get('message', 'Unknown error')
                return jsonify({'error': f'Connection failed: {error_msg}'}), response.status_code

        except requests.exceptions.RequestException as req_error:
            return jsonify({'error': f'Connection failed: {str(req_error)}'}), 500

    except Exception as e:
        print(f"Error testing configuration: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/records', methods=['GET'])
def get_records():
    """Get all DNS records from the zone
    ---
    tags:
      - DNS Records
    summary: List all DNS records
    description: Retrieve all DNS records from the configured DigitalOcean DNS zone
    responses:
      200:
        description: List of DNS records
        schema:
          type: object
          properties:
            records:
              type: array
              items:
                type: object
                properties:
                  name:
                    type: string
                    example: www
                  type:
                    type: string
                    example: A
                  ttl:
                    type: integer
                    example: 3600
                  id:
                    type: integer
                    example: 123456789
                  fqdn:
                    type: string
                    example: www.example.com
                  values:
                    type: array
                    items:
                      type: string
                    example: ["192.0.2.1"]
            zone:
              type: string
              example: example.com
      400:
        description: Configuration incomplete
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
            details:
              type: string
    """
    try:
        # Check if configuration is complete
        if not is_config_complete():
            return jsonify({'error': 'DigitalOcean configuration is incomplete. Please configure your credentials.'}), 400
        
        print(f"Attempting to connect to DigitalOcean DNS Zone: {config['DNS_ZONE']}")
        
        # Fetch all records with pagination support
        all_domain_records = []
        page = 1
        per_page = 200  # DigitalOcean allows up to 200 per page
        
        while True:
            response = make_do_request('GET', f"/domains/{config['DNS_ZONE']}/records?page={page}&per_page={per_page}")
            
            if response.status_code != 200:
                error_msg = response.json().get('message', 'Unknown error')
                return jsonify({'error': f'Failed to fetch records: {error_msg}'}), response.status_code
            
            response_data = response.json()
            domain_records = response_data.get('domain_records', [])
            all_domain_records.extend(domain_records)
            
            # Check if there are more pages
            links = response_data.get('links', {})
            pages = links.get('pages', {})
            
            if 'next' not in pages:
                break  # No more pages
            
            page += 1
        
        records = []
        for record in all_domain_records:
            record_data = {
                'name': record.get('name'),
                'type': record.get('type'),
                'ttl': record.get('ttl'),
                'id': record.get('id'),
                'fqdn': f"{record.get('name')}.{config['DNS_ZONE']}" if record.get('name') != '@' else config['DNS_ZONE']
            }
            
            # Extract record values based on type
            data_value = record.get('data')
            if record.get('type') == 'MX':
                priority = record.get('priority', 0)
                record_data['values'] = [f"{priority} {data_value}"]
            elif record.get('type') == 'SRV':
                priority = record.get('priority', 0)
                weight = record.get('weight', 0)
                port = record.get('port', 0)
                record_data['values'] = [f"{priority} {weight} {port} {data_value}"]
            else:
                record_data['values'] = [data_value] if data_value else []
            
            records.append(record_data)
        
        print(f"Successfully retrieved {len(records)} records")
        return jsonify({'records': records, 'zone': config['DNS_ZONE']})
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR: {str(e)}")
        print(error_details)
        return jsonify({'error': str(e), 'details': error_details}), 500

@app.route('/api/records', methods=['POST'])
def create_record():
    """Create a new DNS record
    ---
    tags:
      - DNS Records
    summary: Create a DNS record
    description: Create a new DNS record in the configured zone
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - type
            - values
          properties:
            name:
              type: string
              example: www
              description: Record name (use @ for root domain)
            type:
              type: string
              example: A
              enum: [A, AAAA, CNAME, MX, TXT, SRV, NS]
              description: DNS record type
            ttl:
              type: integer
              example: 3600
              description: Time to live in seconds (default 3600)
            values:
              type: array
              items:
                type: string
              example: ["192.0.2.1"]
              description: Record values (format depends on type)
    responses:
      201:
        description: Record created successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: Record created successfully
            name:
              type: string
              example: www
      400:
        description: Invalid request or configuration
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        data = request.json
        record_name = data.get('name')
        record_type = data.get('type')
        ttl = data.get('ttl', 3600)
        values = data.get('values', [])

        if not record_name or not record_type or not values:
            return jsonify({'error': 'Missing required fields: name, type, values'}), 400
        
        if not is_config_complete():
            return jsonify({'error': 'DigitalOcean configuration is incomplete.'}), 400
        
        # Prepare the record data for DigitalOcean API
        record_data = {
            'type': record_type,
            'name': record_name,
            'ttl': ttl
        }
        
        # Handle different record types
        if record_type in ['A', 'AAAA', 'CNAME', 'TXT', 'NS']:
            if len(values) > 1 and record_type == 'CNAME':
                return jsonify({'error': 'CNAME records can only have one value'}), 400
            record_data['data'] = values[0]
        elif record_type == 'MX':
            # MX format: "priority exchange"
            parts = values[0].split(' ', 1)
            if len(parts) == 2:
                record_data['priority'] = int(parts[0])
                record_data['data'] = parts[1]
            else:
                return jsonify({'error': 'MX record must be in format: "priority exchange"'}), 400
        elif record_type == 'SRV':
            # SRV format: "priority weight port target"
            parts = values[0].split(' ', 3)
            if len(parts) == 4:
                record_data['priority'] = int(parts[0])
                record_data['weight'] = int(parts[1])
                record_data['port'] = int(parts[2])
                record_data['data'] = parts[3]
            else:
                return jsonify({'error': 'SRV record must be in format: "priority weight port target"'}), 400
        else:
            return jsonify({'error': f'Unsupported record type: {record_type}'}), 400
        
        # Create the record via DigitalOcean API
        response = make_do_request('POST', f"/domains/{config['DNS_ZONE']}/records", record_data)
        
        if response.status_code in [200, 201]:
            return jsonify({'message': 'Record created successfully', 'name': record_name}), 201
        else:
            error_msg = response.json().get('message', 'Unknown error')
            return jsonify({'error': f'Failed to create record: {error_msg}'}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/records/<record_type>/<path:record_name>', methods=['PUT'])
def update_record(record_type, record_name):
    """Update an existing DNS record
    ---
    tags:
      - DNS Records
    summary: Update a DNS record
    description: Update an existing DNS record by type and name
    parameters:
      - in: path
        name: record_type
        type: string
        required: true
        description: DNS record type (A, AAAA, CNAME, MX, TXT, SRV, NS)
        example: A
      - in: path
        name: record_name
        type: string
        required: true
        description: Record name
        example: www
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - values
          properties:
            ttl:
              type: integer
              example: 3600
              description: Time to live in seconds
            values:
              type: array
              items:
                type: string
              example: ["192.0.2.1"]
              description: Updated record values
            id:
              type: integer
              example: 123456789
              description: Record ID (optional, will be looked up if not provided)
    responses:
      200:
        description: Record updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: Record updated successfully
            name:
              type: string
              example: www
      400:
        description: Invalid request or configuration
        schema:
          type: object
          properties:
            error:
              type: string
      404:
        description: Record not found
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        data = request.json
        ttl = data.get('ttl', 3600)
        values = data.get('values', [])
        record_id = data.get('id')

        if not values:
            return jsonify({'error': 'Missing required field: values'}), 400
        
        if not is_config_complete():
            return jsonify({'error': 'DigitalOcean configuration is incomplete.'}), 400
        
        # For DigitalOcean, we need to find the record ID first if not provided
        if not record_id:
            # Get all records and find the matching one
            response = make_do_request('GET', f"/domains/{config['DNS_ZONE']}/records")
            if response.status_code == 200:
                records = response.json().get('domain_records', [])
                for rec in records:
                    if rec.get('name') == record_name and rec.get('type') == record_type:
                        record_id = rec.get('id')
                        break
            
            if not record_id:
                return jsonify({'error': f'Record {record_name} ({record_type}) not found'}), 404
        
        # Prepare the update data
        update_data = {
            'type': record_type,
            'name': record_name,
            'ttl': ttl
        }
        
        # Handle different record types
        if record_type in ['A', 'AAAA', 'CNAME', 'TXT', 'NS']:
            if len(values) > 1 and record_type == 'CNAME':
                return jsonify({'error': 'CNAME records can only have one value'}), 400
            update_data['data'] = values[0]
        elif record_type == 'MX':
            parts = values[0].split(' ', 1)
            if len(parts) == 2:
                update_data['priority'] = int(parts[0])
                update_data['data'] = parts[1]
            else:
                return jsonify({'error': 'MX record must be in format: "priority exchange"'}), 400
        elif record_type == 'SRV':
            parts = values[0].split(' ', 3)
            if len(parts) == 4:
                update_data['priority'] = int(parts[0])
                update_data['weight'] = int(parts[1])
                update_data['port'] = int(parts[2])
                update_data['data'] = parts[3]
            else:
                return jsonify({'error': 'SRV record must be in format: "priority weight port target"'}), 400
        else:
            return jsonify({'error': f'Unsupported record type: {record_type}'}), 400
        
        # Update the record via DigitalOcean API
        response = make_do_request('PUT', f"/domains/{config['DNS_ZONE']}/records/{record_id}", update_data)
        
        if response.status_code == 200:
            return jsonify({'message': 'Record updated successfully', 'name': record_name})
        else:
            error_msg = response.json().get('message', 'Unknown error')
            return jsonify({'error': f'Failed to update record: {error_msg}'}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/records/<record_type>/<path:record_name>', methods=['DELETE'])
def delete_record(record_type, record_name):
    """Delete a DNS record
    ---
    tags:
      - DNS Records
    summary: Delete a DNS record
    description: Delete a DNS record by type and name
    parameters:
      - in: path
        name: record_type
        type: string
        required: true
        description: DNS record type (A, AAAA, CNAME, MX, TXT, SRV, NS)
        example: A
      - in: path
        name: record_name
        type: string
        required: true
        description: Record name
        example: www
      - in: query
        name: id
        type: integer
        required: false
        description: Record ID (optional, will be looked up if not provided)
        example: 123456789
    responses:
      200:
        description: Record deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: Record deleted successfully
            name:
              type: string
              example: www
      400:
        description: Configuration incomplete
        schema:
          type: object
          properties:
            error:
              type: string
      404:
        description: Record not found
        schema:
          type: object
          properties:
            error:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            error:
              type: string
    """
    try:
        if not is_config_complete():
            return jsonify({'error': 'DigitalOcean configuration is incomplete.'}), 400

        # Get record ID from query parameter or find it
        record_id = request.args.get('id')
        
        if not record_id:
            # Get all records and find the matching one
            response = make_do_request('GET', f"/domains/{config['DNS_ZONE']}/records")
            if response.status_code == 200:
                records = response.json().get('domain_records', [])
                for rec in records:
                    if rec.get('name') == record_name and rec.get('type') == record_type:
                        record_id = rec.get('id')
                        break
            
            if not record_id:
                return jsonify({'error': f'Record {record_name} ({record_type}) not found'}), 404
        
        # Delete the record
        response = make_do_request('DELETE', f"/domains/{config['DNS_ZONE']}/records/{record_id}")
        
        if response.status_code == 204:
            return jsonify({'message': 'Record deleted successfully', 'name': record_name})
        else:
            error_msg = response.json().get('message', 'Unknown error') if response.text else 'Unknown error'
            return jsonify({'error': f'Failed to delete record: {error_msg}'}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Check if environment variables are set and log a warning if not
    required_vars = ['DO_API_TOKEN', 'DO_DNS_ZONE']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"WARNING: Missing environment variables: {', '.join(missing_vars)}")
        print("The application will start, but you need to configure DigitalOcean credentials in Settings.")
        print(f"Starting DigitalOcean DNS Manager (unconfigured)")
    else:
        print(f"Starting DigitalOcean DNS Manager for zone: {DNS_ZONE}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
