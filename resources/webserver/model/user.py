import webserver.datastore as ds
from webserver.controller import stripe_controller

import secrets, uuid
import flask_login
from werkzeug.security import generate_password_hash, check_password_hash

import logging

class User(flask_login.UserMixin):
  
  def __init__(self, user_id, email, token, hashpw, stripe_customer_id, email_verified=False, created_at=None):
    self.user_id = user_id
    self.email = email
    self.token = token
    self.hashpw = hashpw
    self.stripe_customer_id = stripe_customer_id
    self.email_verified = email_verified
    self.created_at = created_at
    self.name = email.split('@')[0] if '@' in email else email

  def is_authenticated(self):
    return super().is_authenticated

  def get_id(self):
    return self.user_id
  
  def is_anonymous(self):
    return super().is_anonymous
  
  def validate_password(self,password):
    return check_password_hash(self.hashpw,password)

  def set_password(self, password):
    """Set a new password for the user"""
    self.hashpw = generate_password_hash(password)

  @staticmethod
  def user_exists(email: str) -> bool:
    res = ds.find("SELECT email from users where email = (%s)",(email,))
    return res is not None

  @staticmethod
  def make_token():
    return secrets.token_urlsafe(16)  

  @staticmethod
  def from_row(row):
    return User(
      row['user_id'], 
      row['email'], 
      row['token'], 
      row['hashpw'], 
      row['stripe_customer_id'],
      row.get('email_verified', False),  # Get email_verified with default False
      row.get('created_at') # Get created_at with default None
    )

  @staticmethod
  def get(user_id):
    res = ds.find("SELECT * from users where user_id = (%s)",(user_id,))
    return User.from_row(res) if res is not None else None

  @staticmethod
  def get_user(email):
    res = ds.find("SELECT * from users where email = (%s)",(email,))
    return User.from_row(res) if res is not None else None

  @staticmethod
  def create_stripe_customer(email):
    return stripe_controller.create_customer(email)
  
  @staticmethod
  def create_datastore_customer(email, password, stripe_customer_id):
    try:
      hashpw = generate_password_hash(password)
      token = User.make_token()
      user_id = uuid.uuid4()
      
      # Get the basic group ID
      basic_group = ds.find("SELECT group_id FROM user_groups WHERE name = 'basic'")
      if not basic_group:
        logging.error("[User.create_datastore_customer] Basic group not found")
        raise ValueError("Basic user group not found")
      
      params = (user_id, email, hashpw, token, stripe_customer_id, basic_group['group_id'])
      logging.info(f"[User.create_datastore_customer] Params: {params}")
      ds.execute("INSERT INTO users (user_id, email, hashpw, token, stripe_customer_id, group_id) values (%s,%s,%s,%s,%s,%s)", params)
    except Exception as e:
      logging.error(f"[User.create_datastore_customer] Exception: {e}", exc_info=True)
      raise  # Re-raise the exception so create_user can handle it
  
  @staticmethod
  def create_user(email, password):
    try:
      logging.info(f"[User.create_user] Creating user: {email}")
      if User.user_exists(email):
        logging.warning(f"[User.create_user] User already exists: {email}")
        raise ValueError(f"{email} already exists")
      customer = User.create_stripe_customer(email)
      User.create_datastore_customer(email, password, customer.id)
      return User.get_user(email)
    except Exception as e:
      logging.error(f"[User.create_user] Exception: {e}", exc_info=True)
      return None

  @staticmethod
  def delete_user(email):
    if not User.user_exists(email): 
      raise ValueError(f"{email} does not exist")
    user = User.get_user(email)
    
    # Only try to delete Stripe customer if it's not a placeholder
    if user.stripe_customer_id and not user.stripe_customer_id.startswith('placeholder_'):
      try:
        stripe_controller.delete_customer(user.stripe_customer_id)
      except Exception as e:
        logging.warning(f"[User.delete_user] Failed to delete Stripe customer: {e}")
    
    ds.execute("DELETE FROM users WHERE email = (%s)",(email,))

  @staticmethod
  def update_password(user_id, hashed_password):
    """Update user password in database"""
    try:
      ds.execute("UPDATE users SET hashpw = (%s) WHERE user_id = (%s)", (hashed_password, user_id))
    except Exception as e:
      logging.error(f"Failed to update password for user {user_id}: {str(e)}")
      raise