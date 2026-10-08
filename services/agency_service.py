import csv
import io
import re
import logging
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db

logger = logging.getLogger(__name__)

def create_agency_indexes():
    """Creates required MongoDB indexes on trusts collection."""
    try:
        db.trusts.create_index([("state", 1)])
        db.trusts.create_index([("district", 1)])
        db.trusts.create_index([("city", 1)])
        db.trusts.create_index([("agency_type", 1)])
        db.trusts.create_index([("status", 1)])
        db.trusts.create_index([("verified", 1)])
        db.trusts.create_index([("trust_name", 1)])
        logger.info("MongoDB agency indexes verified.")
    except Exception as e:
        logger.warning(f"Index creation note: {e}")

def get_freshness_status(last_verified):
    """
    Calculates verification freshness status based on last_verified date.
    Rules:
    - <= 90 days: Recently Verified (Green)
    - 91-180 days: Review Due (Yellow)
    - > 180 days: Verification Required (Red/Orange)
    - None / Unverified: Pending Verification (Gray)
    """
    if not last_verified:
        return {
            'status': 'Pending Verification',
            'days': None,
            'badge_class': 'badge-secondary',
            'color': '#6B7280'
        }

    try:
        if isinstance(last_verified, str):
            # Parse ISO date or YYYY-MM-DD
            dt_str = last_verified.replace('Z', '+00:00')
            if 'T' in dt_str:
                dt = datetime.fromisoformat(dt_str)
            else:
                dt = datetime.strptime(dt_str[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
        elif isinstance(last_verified, datetime):
            dt = last_verified
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            return {'status': 'Pending Verification', 'days': None, 'badge_class': 'badge-secondary', 'color': '#6B7280'}

        now = datetime.now(timezone.utc)
        days = (now - dt).days

        if days <= 90:
            return {
                'status': 'Recently Verified',
                'days': days,
                'badge_class': 'badge-approved',
                'color': '#065F46'
            }
        elif days <= 180:
            return {
                'status': 'Review Due',
                'days': days,
                'badge_class': 'badge-pending',
                'color': '#92400E'
            }
        else:
            return {
                'status': 'Verification Required',
                'days': days,
                'badge_class': 'badge-rejected',
                'color': '#991B1B'
            }
    except Exception as e:
        logger.error(f"Error calculating freshness for {last_verified}: {e}")
        return {'status': 'Pending Verification', 'days': None, 'badge_class': 'badge-secondary', 'color': '#6B7280'}

def validate_url(url):
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
    return url

def validate_email(email_str):
    if not email_str:
        return ""
    email_str = email_str.strip().lower()
    regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    if re.match(regex, email_str):
        return email_str
    return ""

def import_agencies_from_csv(file_stream):
    """
    Imports agency records from a CSV file into the trusts collection.
    Performs validation, normalization, duplicate detection, and returns import summary.
    """
    successful_count = 0
    skipped_count = 0
    failed_count = 0
    errors = []

    try:
        content = file_stream.read().decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(content))

        now_iso = datetime.now(timezone.utc).isoformat()

        for row_idx, row in enumerate(csv_reader, start=2):
            try:
                trust_name = row.get('agency_name') or row.get('trust_name') or ''
                trust_name = trust_name.strip()

                if not trust_name:
                    failed_count += 1
                    errors.append(f"Row {row_idx}: Missing required Agency Name.")
                    continue

                state = (row.get('state') or 'Tamil Nadu').strip()
                district = (row.get('district') or '').strip()
                city = (row.get('city') or district or '').strip()
                address = (row.get('public_address') or row.get('address') or '').strip()
                phone = (row.get('phone') or row.get('public_phone') or '').strip()
                email = validate_email(row.get('email') or row.get('public_email') or '')
                website = validate_url(row.get('website') or row.get('source_url') or '')
                agency_type = (row.get('agency_type') or 'Specialized Adoption Agency (SAA)').strip()
                verification_source = (row.get('verification_source') or 'Official CARA / Government Registry').strip()
                source_url = validate_url(row.get('source_url') or website or '')

                # Parse languages
                lang_str = row.get('languages') or 'English, Tamil'
                if isinstance(lang_str, str):
                    languages = [l.strip() for l in lang_str.split(',') if l.strip()]
                else:
                    languages = ['English', 'Tamil']

                # Parse verification status
                verified_raw = str(row.get('verified', '')).strip().lower()
                is_verified = verified_raw in ['true', '1', 'yes', 'verified']

                status_raw = str(row.get('status', '')).strip().upper()
                if status_raw in ['ACTIVE', 'VERIFIED']:
                    status_val = 'ACTIVE' if is_verified else 'PENDING_REVIEW'
                elif status_raw in ['INACTIVE', 'DEACTIVATED', 'SUSPENDED']:
                    status_val = 'INACTIVE'
                else:
                    status_val = 'ACTIVE' if is_verified else 'PENDING_REVIEW'

                last_verified = row.get('last_verified') or (now_iso if is_verified else None)

                # Duplicate detection by trust_name + state + city
                existing = db.trusts.find_one({
                    'trust_name': {'$regex': f"^{re.escape(trust_name)}$", '$options': 'i'},
                    'state': {'$regex': f"^{re.escape(state)}$", '$options': 'i'},
                    'city': {'$regex': f"^{re.escape(city)}$", '$options': 'i'}
                })

                agency_doc = {
                    'trust_name': trust_name,
                    'state': state,
                    'district': district,
                    'city': city,
                    'address': address,
                    'location': f"{city}, {state}" if city else state,
                    'phone': phone,
                    'email': email,
                    'website': website,
                    'languages': languages,
                    'agency_type': agency_type,
                    'verified': is_verified,
                    'verification_source': verification_source,
                    'source_url': source_url,
                    'last_verified': last_verified,
                    'status': status_val,
                    'description': f"Official {agency_type} operating in {city}, {state}.",
                    'updated_at': now_iso
                }

                if existing:
                    # Update existing record safely
                    db.trusts.update_one({'_id': existing['_id']}, {'$set': agency_doc})
                    skipped_count += 1
                else:
                    agency_doc['created_at'] = now_iso
                    db.trusts.insert_one(agency_doc)
                    successful_count += 1

            except Exception as row_err:
                failed_count += 1
                errors.append(f"Row {row_idx}: Error parsing - {row_err}")

        return {
            'success': True,
            'successful_count': successful_count,
            'skipped_count': skipped_count,
            'failed_count': failed_count,
            'errors': errors
        }
    except Exception as e:
        logger.error(f"CSV Import Exception: {e}")
        return {
            'success': False,
            'error': str(e),
            'successful_count': 0,
            'skipped_count': 0,
            'failed_count': 0,
            'errors': [str(e)]
        }

def export_agencies_to_csv():
    """Exports all agency records from the trusts collection to a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        'Agency ID', 'Agency Name', 'State', 'District', 'City', 'Address',
        'Phone', 'Email', 'Website', 'Languages', 'Agency Type',
        'Verified', 'Verification Source', 'Source URL', 'Last Verified',
        'Status', 'Freshness Status'
    ]
    writer.writerow(headers)

    agencies = list(db.trusts.find().sort('trust_name', 1))
    for a in agencies:
        freshness = get_freshness_status(a.get('last_verified'))
        langs = ", ".join(a.get('languages', [])) if isinstance(a.get('languages'), list) else str(a.get('languages', ''))
        writer.writerow([
            str(a['_id']),
            a.get('trust_name', ''),
            a.get('state', ''),
            a.get('district', ''),
            a.get('city', ''),
            a.get('address', ''),
            a.get('phone', ''),
            a.get('email', ''),
            a.get('website', ''),
            langs,
            a.get('agency_type', ''),
            'TRUE' if a.get('verified') else 'FALSE',
            a.get('verification_source', ''),
            a.get('source_url', ''),
            a.get('last_verified', ''),
            a.get('status', ''),
            freshness['status']
        ])

    return output.getvalue()
