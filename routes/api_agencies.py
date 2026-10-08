import re
from flask import Blueprint, request, jsonify, Response
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user
from utils.decorators import admin_required, login_required
from services.agency_service import get_freshness_status, import_agencies_from_csv, export_agencies_to_csv, validate_url, validate_email

api_agencies_bp = Blueprint('api_agencies', __name__, url_prefix='/api')

@api_agencies_bp.route('/agencies', methods=['GET'])
def api_get_agencies():
    """GET /api/agencies - List active verified agencies with filters."""
    state = request.args.get('state', '').strip()
    district = request.args.get('district', '').strip()
    city = request.args.get('city', '').strip()
    language = request.args.get('language', '').strip()
    agency_type = request.args.get('agency_type', '').strip()
    search = request.args.get('search', '').strip()

    query = {'verified': True, 'status': {'$in': ['ACTIVE', 'Verified']}}

    if state:
        query['state'] = {'$regex': re.escape(state), '$options': 'i'}
    if district:
        query['district'] = {'$regex': re.escape(district), '$options': 'i'}
    if city:
        query['city'] = {'$regex': re.escape(city), '$options': 'i'}
    if language:
        query['languages'] = {'$regex': re.escape(language), '$options': 'i'}
    if agency_type:
        query['agency_type'] = {'$regex': re.escape(agency_type), '$options': 'i'}
    if search:
        query['$or'] = [
            {'trust_name': {'$regex': re.escape(search), '$options': 'i'}},
            {'city': {'$regex': re.escape(search), '$options': 'i'}},
            {'district': {'$regex': re.escape(search), '$options': 'i'}},
            {'state': {'$regex': re.escape(search), '$options': 'i'}}
        ]

    agencies = list(db.trusts.find(query).sort('trust_name', 1))
    result = []
    for a in agencies:
        result.append({
            'id': str(a['_id']),
            'agency_name': a.get('trust_name'),
            'state': a.get('state'),
            'district': a.get('district'),
            'city': a.get('city'),
            'public_address': a.get('address') or a.get('location'),
            'phone': a.get('phone'),
            'email': a.get('email'),
            'website': a.get('website'),
            'languages': a.get('languages'),
            'agency_type': a.get('agency_type'),
            'verified': a.get('verified'),
            'verification_source': a.get('verification_source'),
            'source_url': a.get('source_url'),
            'last_verified': a.get('last_verified'),
            'freshness': get_freshness_status(a.get('last_verified'))
        })

    return jsonify({'count': len(result), 'agencies': result})

@api_agencies_bp.route('/agencies/<agency_id>', methods=['GET'])
def api_get_agency_detail(agency_id):
    """GET /api/agencies/<agency_id> - Return public details of one agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency or not agency.get('verified') or agency.get('status') not in ['ACTIVE', 'Verified']:
        return jsonify({'error': 'Active verified agency record not found.'}), 404

    return jsonify({
        'id': str(agency['_id']),
        'agency_name': agency.get('trust_name'),
        'state': agency.get('state'),
        'district': agency.get('district'),
        'city': agency.get('city'),
        'public_address': agency.get('address') or agency.get('location'),
        'phone': agency.get('phone'),
        'email': agency.get('email'),
        'website': agency.get('website'),
        'languages': agency.get('languages'),
        'agency_type': agency.get('agency_type'),
        'verified': agency.get('verified'),
        'verification_source': agency.get('verification_source'),
        'source_url': agency.get('source_url'),
        'last_verified': agency.get('last_verified'),
        'freshness': get_freshness_status(agency.get('last_verified'))
    })

@api_agencies_bp.route('/admin/agencies', methods=['POST'])
@admin_required
def api_admin_add_agency():
    """POST /api/admin/agencies - Add agency."""
    data = request.get_json() or request.form
    trust_name = data.get('agency_name') or data.get('trust_name') or ''
    if not trust_name:
        return jsonify({'error': 'Agency name is required.'}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    mark_verified = bool(data.get('verified'))

    agency_doc = {
        'trust_name': trust_name.strip(),
        'state': (data.get('state') or 'Tamil Nadu').strip(),
        'district': (data.get('district') or '').strip(),
        'city': (data.get('city') or '').strip(),
        'address': (data.get('address') or '').strip(),
        'location': f"{data.get('city')}, {data.get('state')}",
        'phone': (data.get('phone') or '').strip(),
        'email': validate_email(data.get('email', '')),
        'website': validate_url(data.get('website', '')),
        'languages': data.get('languages', ['English', 'Tamil']),
        'agency_type': (data.get('agency_type') or 'Specialized Adoption Agency (SAA)').strip(),
        'verified': mark_verified,
        'verification_source': (data.get('verification_source') or 'Official CARA Registry').strip(),
        'source_url': validate_url(data.get('source_url', '')),
        'last_verified': now_iso if mark_verified else None,
        'status': 'ACTIVE' if mark_verified else 'PENDING_REVIEW',
        'created_at': now_iso,
        'updated_at': now_iso
    }

    res = db.trusts.insert_one(agency_doc)
    agency_doc['_id'] = str(res.inserted_id)
    return jsonify({'success': True, 'agency': agency_doc}), 21

@api_agencies_bp.route('/admin/agencies/<agency_id>', methods=['PUT'])
@admin_required
def api_admin_update_agency(agency_id):
    """PUT /api/admin/agencies/<agency_id> - Update agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404

    data = request.get_json() or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    update_doc = {'updated_at': now_iso}
    for field in ['trust_name', 'state', 'district', 'city', 'address', 'phone', 'email', 'website', 'agency_type', 'verification_source', 'source_url']:
        if field in data:
            update_doc[field] = data[field]

    if 'languages' in data:
        update_doc['languages'] = data['languages']

    db.trusts.update_one({'_id': agency['_id']}, {'$set': update_doc})
    return jsonify({'success': True, 'updated_id': agency_id})

@api_agencies_bp.route('/admin/agencies/<agency_id>/verify', methods=['POST'])
@admin_required
def api_admin_verify_agency(agency_id):
    """POST /api/admin/agencies/<agency_id>/verify - Verify agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404

    data = request.get_json() or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'verified': True,
        'status': 'ACTIVE',
        'verification_source': data.get('verification_source') or agency.get('verification_source') or 'Official CARA Registry',
        'source_url': data.get('source_url') or agency.get('source_url') or '',
        'last_verified': now_iso,
        'updated_at': now_iso
    }})

    return jsonify({'success': True, 'message': 'Agency verified and activated.'})

@api_agencies_bp.route('/admin/agencies/<agency_id>/deactivate', methods=['POST'])
@admin_required
def api_admin_deactivate_agency(agency_id):
    """POST /api/admin/agencies/<agency_id>/deactivate - Deactivate agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404

    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'status': 'INACTIVE',
        'verified': False,
        'updated_at': now_iso
    }})

    return jsonify({'success': True, 'message': 'Agency deactivated.'})

@api_agencies_bp.route('/admin/agencies/<agency_id>/reactivate', methods=['POST'])
@admin_required
def api_admin_reactivate_agency(agency_id):
    """POST /api/admin/agencies/<agency_id>/reactivate - Reactivate agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404

    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'status': 'ACTIVE',
        'verified': True,
        'last_verified': now_iso,
        'updated_at': now_iso
    }})

    return jsonify({'success': True, 'message': 'Agency reactivated.'})

@api_agencies_bp.route('/admin/agencies/import', methods=['POST'])
@admin_required
def api_admin_import_csv():
    """POST /api/admin/agencies/import - Import CSV."""
    if 'csv_file' not in request.files:
        return jsonify({'error': 'No csv_file parameter provided.'}), 400

    file = request.files['csv_file']
    res = import_agencies_from_csv(file.stream)
    return jsonify(res)

@api_agencies_bp.route('/admin/agencies/export', methods=['GET'])
@admin_required
def api_admin_export_csv():
    """GET /api/admin/agencies/export - Export CSV."""
    csv_data = export_agencies_to_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=adoption_agencies_export.csv"}
    )
