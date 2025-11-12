import sendgrid
import os
from sendgrid.helpers.mail import Mail, Email

def send(email,subject,content):
    try:
        api_key = os.getenv('SENDGRID_API_KEY')
        if not api_key:
            raise ValueError("SendGrid API key not configured")
        
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        from_email = Email("info@toxindex.com")
        mail = Mail(from_email=from_email, to_emails=email, subject=subject, html_content=content)
        response = sg.send(mail)
        return response
    except Exception as e:
        import logging
        logging.error(f"Failed to send email via SendGrid: {str(e)}")
        raise