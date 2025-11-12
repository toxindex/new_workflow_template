import stripe
import os
import ssl
import requests
from requests.adapters import HTTPAdapter

# Configure Stripe
stripe.api_version = '2020-08-27'
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Create SSL context with TLS 1.2 requirement
context = ssl.create_default_context()
context.minimum_version = ssl.TLSVersion.TLSv1_2

# Create a session with our SSL context
session = requests.Session()
adapter = HTTPAdapter()
adapter.init_poolmanager(connections=10, maxsize=10, ssl_context=context)
session.mount('https://', adapter)

# Configure Stripe to use our session
stripe.default_http_client = stripe.http_client.RequestsClient(verify_ssl_certs=True, session=session)

def validate_api_key():
    """Validate if the Stripe API key is working correctly"""
    try:
        if not stripe.api_key:
            return False, "No API key configured"
        
        # Test with a simple API call
        stripe.Customer.list(limit=1)
        return True, "API key is valid"
        
    except stripe.error.AuthenticationError:
        return False, "Invalid API key"
    except stripe.error.PermissionError:
        return False, "API key lacks required permissions"
    except Exception as e:
        return False, f"API key validation failed: {str(e)}"

def create_customer(email):
  try:
    if not stripe.api_key:
      raise ValueError("Stripe API key not configured")
    return stripe.Customer.create(email=email)
  except Exception as e:
    import logging
    logging.error(f"Failed to create Stripe customer for {email}: {str(e)}")
    raise

def delete_customer(stripe_customer_id):
  try:
    if not stripe.api_key:
      raise ValueError("Stripe API key not configured")
    return stripe.Customer.delete(stripe_customer_id)
  except Exception as e:
    import logging
    logging.error(f"Failed to delete Stripe customer {stripe_customer_id}: {str(e)}")
    raise

def create_customer_portal_session(stripe_customer_id):
  return stripe.billing_portal.Session.create(customer=stripe_customer_id)
