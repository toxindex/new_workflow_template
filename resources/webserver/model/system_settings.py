import webserver.datastore as ds
from datetime import datetime
import logging

class SystemSettings:
    def __init__(self, setting_id, setting_key, setting_value, description, created_at, updated_at):
        self.setting_id = setting_id
        self.setting_key = setting_key
        self.setting_value = setting_value
        self.description = description
        self.created_at = created_at
        self.updated_at = updated_at

    @staticmethod
    def get_setting(key, default=None):
        """Get a system setting by key"""
        try:
            result = ds.find('SELECT setting_value FROM system_settings WHERE setting_key = (%s)', (key,))
            if result:
                return result['setting_value']
            return default
        except Exception as e:
            logging.error(f"Error getting system setting {key}: {e}")
            return default

    @staticmethod
    def get_setting_int(key, default=0):
        """Get a system setting as integer"""
        try:
            value = SystemSettings.get_setting(key, str(default))
            return int(value)
        except (ValueError, TypeError):
            logging.error(f"Error converting system setting {key} to int: {value}")
            return default

    @staticmethod
    def set_setting(key, value, description=None):
        """Set a system setting"""
        try:
            # Check if setting exists
            existing = ds.find('SELECT setting_id FROM system_settings WHERE setting_key = (%s)', (key,))
            
            if existing:
                # Update existing setting
                ds.execute(
                    'UPDATE system_settings SET setting_value = (%s), updated_at = (%s) WHERE setting_key = (%s)',
                    (str(value), datetime.now(), key)
                )
            else:
                # Insert new setting
                ds.execute(
                    'INSERT INTO system_settings (setting_key, setting_value, description) VALUES (%s, %s, %s)',
                    (key, str(value), description)
                )
            return True
        except Exception as e:
            logging.error(f"Error setting system setting {key}: {e}")
            return False

    @staticmethod
    def get_all_settings():
        """Get all system settings"""
        try:
            results = ds.find_all('SELECT * FROM system_settings ORDER BY setting_key')
            return [SystemSettings(**result) for result in results]
        except Exception as e:
            logging.error(f"Error getting all system settings: {e}")
            return []

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'setting_id': self.setting_id,
            'setting_key': self.setting_key,
            'setting_value': self.setting_value,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        } 