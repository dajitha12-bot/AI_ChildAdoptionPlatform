import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.mongodb import db, init_db
from utils.auth import hash_password
from services.agency_service import import_agencies_from_csv, create_agency_indexes

def seed():
    print("Seeding database for Smart Child Adoption Support Platform...")
    init_db()
    create_agency_indexes()

    # Clear existing collections for a clean seed
    db.users.delete_many({})
    db.trusts.delete_many({})
    db.adoption_requests.delete_many({})
    db.journeys.delete_many({})
    db.notifications.delete_many({})
    db.ai_conversations.delete_many({})
    db.email_logs.delete_many({})

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Admin Account
    admin_user = {
        'name': 'System Administrator',
        'email': 'admin@smartadoption.org',
        'password_hash': hash_password('Admin@123'),
        'role': 'admin',
        'phone': '+91 9876543210',
        'address': 'Headquarters, Chennai, Tamil Nadu',
        'language': 'English',
        'preferences': {},
        'created_at': now_iso,
        'updated_at': now_iso
    }
    admin_id = db.users.insert_one(admin_user).inserted_id
    print(f"Created Admin account: admin@smartadoption.org (ID: {admin_id})")

    # 2. Import Official India-Wide Adoption Agencies CSV
    csv_file_path = os.path.join(os.path.dirname(__file__), 'official_indian_agencies.csv')
    if os.path.exists(csv_file_path):
        with open(csv_file_path, 'rb') as f:
            res = import_agencies_from_csv(f)
            print(f"Imported Official Agencies: {res.get('successful_count')} successful, {res.get('skipped_count')} skipped, {res.get('failed_count')} failed.")

    # 3. Trust User Accounts Mapping (Ensuring login credentials for sample trust handlers)
    sample_trusts_login_data = [
        {
            'trust_name': 'ABC Adoption Support Trust',
            'email': 'trust.abc@smartadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9443123456',
            'location': 'Madurai, Tamil Nadu'
        },
        {
            'trust_name': 'Hope Adoption & Family Care Center',
            'email': 'trust.hope@smartadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9444987654',
            'location': 'Chennai, Tamil Nadu'
        },
        {
            'trust_name': 'Coimbatore Family Welfare & Adoption Trust',
            'email': 'trust.family@smartadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9422334455',
            'location': 'Coimbatore, Tamil Nadu'
        },
        {
            'trust_name': 'Sunshine Child Care Institution',
            'email': 'trust.sunshine@smartadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9411223344',
            'location': 'Trichy, Tamil Nadu'
        }
    ]

    abc_trust_id = None
    for t_data in sample_trusts_login_data:
        user_doc = {
            'name': t_data['trust_name'],
            'email': t_data['email'],
            'password_hash': hash_password(t_data['password']),
            'role': 'trust',
            'phone': t_data['phone'],
            'address': t_data['location'],
            'language': 'English',
            'preferences': {'location': t_data['location'], 'languages': ['Tamil', 'English']},
            'created_at': now_iso,
            'updated_at': now_iso
        }
        t_user_id = db.users.insert_one(user_doc).inserted_id

        # Update matching trust doc with user_id
        matching_trust = db.trusts.find_one({'trust_name': t_data['trust_name']})
        if matching_trust:
            db.trusts.update_one({'_id': matching_trust['_id']}, {'$set': {'user_id': str(t_user_id)}})
            if t_data['trust_name'] == 'ABC Adoption Support Trust':
                abc_trust_id = str(matching_trust['_id'])
        print(f"Mapped Trust User Account: {t_data['trust_name']} ({t_data['email']})")

    # 4. Sample Adopter Account
    adopter_user = {
        'name': 'Ajitha D R',
        'email': 'user@example.com',
        'password_hash': hash_password('User@123'),
        'role': 'adopter',
        'phone': '+91 9898989898',
        'address': '12 West Street, Madurai, Tamil Nadu',
        'language': 'Tamil',
        'family_info': {
            'marital_status': 'Married',
            'occupation': 'Software Engineer',
            'annual_income': '₹12,000,000'
        },
        'preferences': {
            'location': 'Madurai',
            'age_group': '0-2 years',
            'languages': ['Tamil', 'English']
        },
        'created_at': now_iso,
        'updated_at': now_iso
    }
    adopter_id = db.users.insert_one(adopter_user).inserted_id
    adopter_id_str = str(adopter_id)
    print(f"Created Adopter account: user@example.com (ID: {adopter_id_str})")

    # 5. Sample Adoption Request & Journey Timeline
    if abc_trust_id:
        req_doc = {
            'request_id': 'ADP1024',
            'adopter_id': adopter_id_str,
            'trust_id': abc_trust_id,
            'status': 'TRUST_REVIEW',
            'created_at': now_iso,
            'updated_at': now_iso
        }
        db.adoption_requests.insert_one(req_doc)

        journey_doc = {
            'request_id': 'ADP1024',
            'adopter_id': adopter_id_str,
            'registration': True,
            'profile_completed': True,
            'request_sent': True,
            'trust_review': True,
            'approved': False,
            'further_process': False,
            'completed': False,
            'current_stage': 'TRUST_REVIEW',
            'updated_at': now_iso
        }
        db.journeys.insert_one(journey_doc)

    # Initial Notifications
    db.notifications.insert_one({
        'user_id': adopter_id_str,
        'message': 'Welcome to Smart Child Adoption Support Platform! Your profile is complete.',
        'type': 'registration',
        'is_read': False,
        'created_at': now_iso
    })
    db.notifications.insert_one({
        'user_id': adopter_id_str,
        'message': 'Adoption request ADP1024 submitted to ABC Adoption Support Trust. Current status: Trust Review.',
        'type': 'request_sent',
        'is_read': False,
        'created_at': now_iso
    })

    print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed()
