import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import logging
from config import Config
from database.mongodb import db

logger = logging.getLogger(__name__)

def _log_email(user_id, recipient_email, email_type, subject, status, error_message=""):
    """Log email attempt in MongoDB email_logs collection."""
    log_doc = {
        'user_id': str(user_id) if user_id else None,
        'email': recipient_email,
        'email_type': email_type,
        'subject': subject,
        'status': status,
        'sent_at': datetime.now(timezone.utc).isoformat(),
        'error_message': error_message
    }
    try:
        db.email_logs.insert_one(log_doc)
    except Exception as e:
        logger.error(f"Failed to record email log: {e}")

def send_smtp_email(to_email, subject, body_text, email_type='GENERAL', user_id=None):
    """Sends an email using configured SMTP parameters. Returns (success: bool, msg: str)."""
    if not to_email:
        return False, "No recipient email address provided."

    # Check if SMTP parameters are configured
    if not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD:
        msg = f"[SIMULATION] Real SMTP credentials not set in .env. Email to {to_email} logged as SENT_SIMULATED."
        logger.info(msg)
        _log_email(user_id, to_email, email_type, subject, 'SENT_SIMULATED', 'SMTP credentials not configured in environment')
        return True, msg

    try:
        msg = MIMEMultipart()
        msg['From'] = Config.SMTP_FROM or Config.SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

        server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10)
        server.starttls()
        server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        _log_email(user_id, to_email, email_type, subject, 'SENT')
        return True, f"Email sent successfully to {to_email}"
    except Exception as e:
        err_msg = str(e)
        logger.error(f"SMTP email sending failed to {to_email}: {err_msg}")
        _log_email(user_id, to_email, email_type, subject, 'FAILED', err_msg)
        return False, f"SMTP Error: {err_msg}"

def send_registration_email(user_name, user_email, user_id=None):
    """Sends welcome registration email to adopter."""
    subject = "Registration Successful – Smart Child Adoption Platform"
    body = f"""Hello {user_name},

Your account has been successfully registered on the Smart Child Adoption Support Platform.

You can now log in and complete your profile and adoption preferences.

Thank you.
Smart Child Adoption Support Team
    """
    return send_smtp_email(user_email, subject, body, email_type='REGISTRATION', user_id=user_id)

def send_approval_email(user_name, user_email, trust_name, user_id=None):
    """Sends adoption request approval email to adopter."""
    subject = "Adoption Request Approved – Smart Child Adoption Platform"
    body = f"""Hello {user_name},

Your adoption request submitted to {trust_name} has been approved for the next stage of the process.

Please log in to view your updated application status and next steps.

Thank you.
Smart Child Adoption Support Team
    """
    return send_smtp_email(user_email, subject, body, email_type='APPROVAL', user_id=user_id)

def send_status_update_email(user_name, user_email, new_status, trust_name, user_id=None):
    """Sends general status update email."""
    subject = f"Adoption Status Update: {new_status} – Smart Child Adoption Platform"
    body = f"""Hello {user_name},

Your adoption application with {trust_name} has been updated to: {new_status}.

Please log in to your dashboard to review your updated adoption journey timeline.

Thank you.
Smart Child Adoption Support Team
    """
    return send_smtp_email(user_email, subject, body, email_type='STATUS_UPDATE', user_id=user_id)

def send_application_submitted_email(applicant_email, application_id, agency_name, user_id=None):
    """Sends official application submission confirmation email (Section 8 format)."""
    subject = f"Application Submitted – {application_id}"
    body = f"""Dear Applicant,

Your adoption application has been successfully submitted.

Application ID:
{application_id}

Selected Agency:
{agency_name}

Current Status:
SUBMITTED

You will receive further updates when the agency reviews your application.

Please check your application journey for the latest status.

Thank you,
Smart Child Adoption Support Platform"""
    return send_smtp_email(applicant_email, subject, body, email_type='APPLICATION_SUBMITTED', user_id=user_id)

def send_application_status_update_email(applicant_email, application_id, agency_name, new_status, user_id=None):
    """Sends official application status update email (Section 10 format)."""
    subject = f"Application Status Updated – {application_id}"
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")
    body = f"""Dear Applicant,

Your application status has been updated.

Application ID:
{application_id}

Agency:
{agency_name}

Current Status:
{new_status}

Last Updated:
{now_str}

Please log in to the platform to view your latest application journey.

Thank you,
Smart Child Adoption Support Platform"""
    return send_smtp_email(applicant_email, subject, body, email_type='APPLICATION_STATUS_UPDATE', user_id=user_id)


def fetch_recent_emails(user_email=None, limit=10):
    """Retrieves recent emails via IMAP, falling back to database email logs if IMAP is unconfigured or fails."""
    # First check database email_logs as primary source of platform email history
    query = {}
    if user_email:
        query['email'] = user_email
    logs = list(db.email_logs.find(query).sort('sent_at', -1).limit(limit))

    # Try IMAP if configured
    imap_emails = []
    if Config.IMAP_USERNAME and Config.IMAP_PASSWORD:
        try:
            mail = imaplib.IMAP4_SSL(Config.IMAP_HOST, Config.IMAP_PORT)
            mail.login(Config.IMAP_USERNAME, Config.IMAP_PASSWORD)
            mail.select('inbox')

            search_criterion = f'TO "{user_email}"' if user_email else 'ALL'
            status, messages = mail.search(None, search_criterion)
            if status == 'OK' and messages[0]:
                email_ids = messages[0].split()[-limit:]
                for e_id in reversed(email_ids):
                    res, msg_data = mail.fetch(e_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject = msg.get('Subject', 'No Subject')
                            from_addr = msg.get('From', 'Unknown')
                            date_hdr = msg.get('Date', '')
                            imap_emails.append({
                                'subject': subject,
                                'from': from_addr,
                                'date': date_hdr,
                                'source': 'IMAP'
                            })
            mail.logout()
        except Exception as e:
            logger.warning(f"IMAP retrieval failed ({e}). Returning database email logs.")

    # Combine database logs and IMAP results
    result_emails = []
    for log in logs:
        result_emails.append({
            'subject': log.get('subject', ''),
            'recipient': log.get('email', ''),
            'email_type': log.get('email_type', ''),
            'status': log.get('status', ''),
            'sent_at': log.get('sent_at', ''),
            'source': 'PLATFORM_LOG'
        })
    result_emails.extend(imap_emails)

    return result_emails

def find_trust_related_emails(user_email):
    """Finds emails specifically related to adoption trust updates for a given user email."""
    if not user_email:
        return []
    logs = list(db.email_logs.find({'email': user_email}).sort('sent_at', -1).limit(5))
    return [{
        'subject': log.get('subject', ''),
        'type': log.get('email_type', ''),
        'status': log.get('status', ''),
        'date': log.get('sent_at', '')
    } for log in logs]


def send_matching_completed_email(applicant_email, application_id, agency_name, user_id=None):
    """Sends official child-family matching completed email (Requirement 20 & 21 format)."""
    subject = f"Child-Family Matching Completed – {application_id}"
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")
    body = f"""Dear Applicant,

Your child-family matching process with {agency_name} has been successfully completed and authorized by the Trust Board.

Application ID:
{application_id}

Agency:
{agency_name}

Completion Date:
{now_str}

Please log in to your dashboard to view the authorized information and next administrative steps.

Thank you,
Smart Child Adoption Support Platform"""
    return send_smtp_email(applicant_email, subject, body, email_type='MATCHING_COMPLETED', user_id=user_id)
