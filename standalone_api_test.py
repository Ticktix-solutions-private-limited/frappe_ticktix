#!/usr/bin/env python3
"""
Standalone API test script for TickTix Identity Server.
This script tests the API without requiring Frappe initialization.
"""

import requests
import base64
import json
from datetime import datetime


def load_config():
    """Load configuration from common_site_config.json"""
    try:
        with open('/home/sagivasan/ticktix/sites/common_site_config.json', 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


def test_api_access_token(config):
    """Test getting access token using client credentials flow."""
    print("=== Testing API Access Token ===")
    
    ticktix_config = config.get('ticktix', {})
    api_config = ticktix_config.get('api', {})
    identity_server = ticktix_config.get('identity_server', {})
    
    client_id = api_config.get('client_id')
    client_secret = api_config.get('client_secret')
    
    # Use the same base URL and token path as main OAuth config
    base_url = identity_server.get('base_url', 'https://login.ticktix.com')
    token_path = identity_server.get('token_url', '/connect/token')
    token_url = f"{base_url.rstrip('/')}{token_path}"
    
    scope = api_config.get('scope', 'identityserver_admin_api offline_access')
    
    if not client_id or not client_secret:
        print("❌ Missing API client credentials in configuration")
        return None
    
    print(f"Client ID: {client_id}")
    print(f"Token URL: {token_url}")
    print(f"Scope: {scope}")
    
    # Request access token using client credentials
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # Try the supported scopes
    scope_variations = [
        scope,  # Configured scope
        'identityserver_admin_api offline_access',  # Admin API with offline access
        'identityserver_admin_api',  # Just admin API
        'openid profile roles offline_access',  # User profile scopes
        'offline_access',  # Just offline access
    ]
    
    for test_scope in scope_variations:
        print(f"\n🔄 Testing scope: '{test_scope}'")
        
        data = {
            'grant_type': 'client_credentials',
            'scope': test_scope
        }
        if test_scope:
            data['scope'] = test_scope
    
        try:
            response = requests.post(token_url, headers=headers, data=data, timeout=10)
            print(f"   Response status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data['access_token']
                expires_in = token_data.get('expires_in', 3600)
                
                print(f"   ✅ Success with scope: '{test_scope}'")
                print(f"   Token (first 20 chars): {access_token[:20]}...")
                print(f"   Expires in: {expires_in} seconds")
                return access_token
            else:
                print(f"   ❌ Failed: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request error: {str(e)}")
    
    print(f"\n❌ All scope variations failed")
    return None


def test_user_search(token, api_base, email):
    """Test searching for a user by email."""
    print(f"\n=== Testing User Search for {email} ===")
    
    if not token:
        print("❌ No access token available")
        return None
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    search_url = f"{api_base.rstrip('/')}/api/Users"
    params = {'searchText': email}
    
    try:
        print(f"🔄 Searching users at: {search_url}")
        print(f"Search params: {params}")
        
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            users_data = response.json()
            print(f"✅ Search successful")
            print(f"Found {len(users_data) if isinstance(users_data, list) else 0} users")
            
            if users_data and isinstance(users_data, list):
                for i, user in enumerate(users_data):
                    print(f"User {i+1}:")
                    print(f"  ID: {user.get('id')}")
                    print(f"  Email: {user.get('email')}")
                    print(f"  Username: {user.get('userName')}")
                    print(f"  Email Confirmed: {user.get('emailConfirmed')}")
                    
                    if user.get('email', '').lower() == email.lower():
                        print(f"  🎯 EXACT MATCH FOUND!")
                        return user
            else:
                print("No users found")
            return None
        else:
            print(f"❌ Search failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {str(e)}")
        return None


def test_user_creation(token, api_base, username, email):
    """Test creating a new user."""
    print(f"\n=== Testing User Creation for {email} ===")
    
    if not token:
        print("❌ No access token available")
        return None
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    create_url = f"{api_base.rstrip('/')}/api/Users"
    payload = {
        'UserName': username,
        'Email': email,
        'EmailConfirmed': True
    }
    
    try:
        print(f"🔄 Creating user at: {create_url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(create_url, json=payload, headers=headers, timeout=10)
        print(f"Response status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json() if response.content else {}
            print(f"✅ User created successfully!")
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"❌ User creation failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {str(e)}")
        return None


def main():
    """Run all API tests."""
    print("🚀 Starting TickTix Identity Server API Tests")
    print("=" * 50)
    
    # Load configuration
    config = load_config()
    if not config:
        print("❌ Failed to load configuration")
        return
    
    ticktix_config = config.get('ticktix', {})
    identity_server = ticktix_config.get('identity_server', {})
    api_config = ticktix_config.get('api', {})
    
    api_base = identity_server.get('provision_api', 'https://authapi.ticktix.com')
    print(f"API Base URL: {api_base}")
    
    # Test 1: Get access token
    token = test_api_access_token(config)
    if not token:
        print("\n❌ Cannot proceed without access token")
        return
    
    # Test 2: Search for Administrator user
    admin_email = api_config.get('admin_email', 'facilitix@ticktix.com')
    print(f"Using administrator email from config: {admin_email}")
    admin_user = test_user_search(token, api_base, admin_email)
    
    if not admin_user:
        print(f"\n🔄 Administrator user not found, attempting to create...")
        admin_created = test_user_creation(token, api_base, 'Administrator', admin_email)
        if admin_created:
            print("✅ Administrator user created successfully")
        else:
            print("❌ Failed to create Administrator user")
    else:
        print(f"✅ Administrator user already exists with ID: {admin_user.get('id')}")
    
    # Test 3: Search for a test user
    test_email = 'testapi@ticktix.com'
    test_user = test_user_search(token, api_base, test_email)
    
    if not test_user:
        print(f"\n🔄 Test user not found, attempting to create...")
        test_created = test_user_creation(token, api_base, 'testapi', test_email)
        if test_created:
            print("✅ Test user created successfully")
        else:
            print("❌ Failed to create test user")
    else:
        print(f"✅ Test user already exists with ID: {test_user.get('id')}")
    
    print("\n" + "=" * 50)
    print("🎉 API testing completed!")


if __name__ == '__main__':
    main()
