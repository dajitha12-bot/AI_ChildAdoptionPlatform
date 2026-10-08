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
    db.adoption_applications.delete_many({})
    db.journeys.delete_many({})
    db.notifications.delete_many({})
    db.ai_conversations.delete_many({})
    db.email_logs.delete_many({})
    db.child_profiles.delete_many({})
    db.child_matches.delete_many({})

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

    # 3. Trust User Accounts Mapping for ALL 12 Agencies
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
        },
        {
            'trust_name': 'Maharashtra Child Adoption Society',
            'email': 'contact@mahachildadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9820011223',
            'location': 'Mumbai, Maharashtra'
        },
        {
            'trust_name': 'Pune Family Support & Adoption Center',
            'email': 'info@puneadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9822055667',
            'location': 'Pune, Maharashtra'
        },
        {
            'trust_name': 'Karnataka Adoption Support Foundation',
            'email': 'support@karnatakaadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9845099887',
            'location': 'Bengaluru, Karnataka'
        },
        {
            'trust_name': 'Delhi Child Welfare & Adoption Agency',
            'email': 'delhi.adoption@wcd.delhi.gov.in',
            'password': 'Trust@123',
            'phone': '+91 9810033445',
            'location': 'New Delhi, Delhi'
        },
        {
            'trust_name': 'Kerala Adoption Resource Center',
            'email': 'kochi@keralaadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9447012345',
            'location': 'Kochi, Kerala'
        },
        {
            'trust_name': 'West Bengal Child Rights & Adoption Society',
            'email': 'info@wbadoption.org',
            'password': 'Trust@123',
            'phone': '+91 9830067890',
            'location': 'Kolkata, West Bengal'
        },
        {
            'trust_name': 'Telangana Child Protection & Adoption Bureau',
            'email': 'contact@telanganaadoption.gov.in',
            'password': 'Trust@123',
            'phone': '+91 9849011223',
            'location': 'Hyderabad, Telangana'
        },
        {
            'trust_name': 'Gujarat Adoption Support Agency',
            'email': 'info@gujaratchildwelfare.org',
            'password': 'Trust@123',
            'phone': '+91 9898077665',
            'location': 'Ahmedabad, Gujarat'
        }
    ]

    trust_id_map = {}
    for t_data in sample_trusts_login_data:
        user_doc = {
            'name': t_data['trust_name'],
            'email': t_data['email'],
            'password_hash': hash_password(t_data['password']),
            'role': 'trust',
            'phone': t_data['phone'],
            'address': t_data['location'],
            'language': 'English',
            'preferences': {'location': t_data['location'], 'languages': ['English']},
            'created_at': now_iso,
            'updated_at': now_iso
        }
        t_user_id = db.users.insert_one(user_doc).inserted_id

        # Update matching trust doc with user_id or insert if missing
        matching_trust = db.trusts.find_one({'trust_name': t_data['trust_name']})
        if matching_trust:
            db.trusts.update_one({'_id': matching_trust['_id']}, {'$set': {'user_id': str(t_user_id), 'verified': True, 'status': 'ACTIVE'}})
            trust_id_map[t_data['trust_name']] = str(matching_trust['_id'])
        else:
            trust_doc = {
                'trust_name': t_data['trust_name'],
                'email': t_data['email'],
                'user_id': str(t_user_id),
                'phone': t_data['phone'],
                'address': t_data['location'],
                'verified': True,
                'status': 'ACTIVE',
                'agency_type': 'Specialized Adoption Agency (SAA)',
                'verification_source': 'Central Adoption Resource Authority (CARA)',
                'created_at': now_iso,
                'updated_at': now_iso
            }
            ins_t_id = db.trusts.insert_one(trust_doc).inserted_id
            trust_id_map[t_data['trust_name']] = str(ins_t_id)

        print(f"Mapped Trust User Account: {t_data['trust_name']} ({t_data['email']})")

    # 4. Primary Demo Adopter Account
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

    # Additional Demo Adopters for multi-trust applications
    demo_adopters_seed = [
        {'name': 'Priya Raman', 'email': 'priya@example.com', 'location': 'Madurai', 'income': '₹900,000'},
        {'name': 'Ramesh Kumar', 'email': 'ramesh@example.com', 'location': 'Chennai', 'income': '₹1,500,000'},
        {'name': 'Anitha Sundaram', 'email': 'anitha@example.com', 'location': 'Chennai', 'income': '₹1,200,000'},
        {'name': 'Karthik Viswanathan', 'email': 'karthik@example.com', 'location': 'Coimbatore', 'income': '₹1,800,000'},
        {'name': 'Deepa Lakshmi', 'email': 'deepa@example.com', 'location': 'Trichy', 'income': '₹850,000'},
        {'name': 'Sanjay Deshmukh', 'email': 'sanjay@example.com', 'location': 'Mumbai', 'income': '₹2,200,000'},
        {'name': 'Sunita Joshi', 'email': 'sunita@example.com', 'location': 'Pune', 'income': '₹1,400,000'},
        {'name': 'Vikram Rao', 'email': 'vikram@example.com', 'location': 'Bengaluru', 'income': '₹2,500,000'},
        {'name': 'Amitabh Sharma', 'email': 'amitabh@example.com', 'location': 'New Delhi', 'income': '₹1,900,000'},
        {'name': 'Lakshmi Menon', 'email': 'lakshmi@example.com', 'location': 'Kochi', 'income': '₹1,100,000'},
        {'name': 'Subhash Roy', 'email': 'subhash@example.com', 'location': 'Kolkata', 'income': '₹1,300,000'},
        {'name': 'Rajesh Reddy', 'email': 'rajesh@example.com', 'location': 'Hyderabad', 'income': '₹2,000,000'},
        {'name': 'Bhavna Patel', 'email': 'bhavna@example.com', 'location': 'Ahmedabad', 'income': '₹1,600,000'}
    ]

    demo_adopter_ids = {}
    for da in demo_adopters_seed:
        da_doc = {
            'name': da['name'],
            'email': da['email'],
            'password_hash': hash_password('User@123'),
            'role': 'adopter',
            'phone': '+91 9876500000',
            'address': f"Main Road, {da['location']}",
            'language': 'English',
            'family_info': {
                'marital_status': 'Married',
                'occupation': 'Professional',
                'annual_income': da['income']
            },
            'preferences': {
                'location': da['location'],
                'age_group': '0-2 years',
                'languages': ['English']
            },
            'created_at': now_iso,
            'updated_at': now_iso
        }
        da_id = db.users.insert_one(da_doc).inserted_id
        demo_adopter_ids[da['email']] = str(da_id)

    # 5. Seed Applications & Journeys for EVERY Trust (1 to 2 per trust)
    app_counter = 1024

    # Map each trust to 1 or 2 applications and children
    trust_application_specs = [
        # ABC Adoption Support Trust
        {'trust_name': 'ABC Adoption Support Trust', 'adopter_email': 'user@example.com', 'adopter_name': 'Ajitha D R', 'status': 'TRUST_REVIEW', 'stage': 'TRUST_REVIEW'},
        {'trust_name': 'ABC Adoption Support Trust', 'adopter_email': 'priya@example.com', 'adopter_name': 'Priya Raman', 'status': 'APPROVED', 'stage': 'APPROVED'},

        # Hope Adoption & Family Care Center
        {'trust_name': 'Hope Adoption & Family Care Center', 'adopter_email': 'ramesh@example.com', 'adopter_name': 'Ramesh Kumar', 'status': 'UNDER_REVIEW', 'stage': 'UNDER_REVIEW'},
        {'trust_name': 'Hope Adoption & Family Care Center', 'adopter_email': 'anitha@example.com', 'adopter_name': 'Anitha Sundaram', 'status': 'APPROVED', 'stage': 'APPROVED'},

        # Coimbatore Family Welfare & Adoption Trust
        {'trust_name': 'Coimbatore Family Welfare & Adoption Trust', 'adopter_email': 'karthik@example.com', 'adopter_name': 'Karthik Viswanathan', 'status': 'SUBMITTED', 'stage': 'SUBMITTED'},

        # Sunshine Child Care Institution
        {'trust_name': 'Sunshine Child Care Institution', 'adopter_email': 'deepa@example.com', 'adopter_name': 'Deepa Lakshmi', 'status': 'TRUST_REVIEW', 'stage': 'TRUST_REVIEW'},

        # Maharashtra Child Adoption Society
        {'trust_name': 'Maharashtra Child Adoption Society', 'adopter_email': 'sanjay@example.com', 'adopter_name': 'Sanjay Deshmukh', 'status': 'UNDER_REVIEW', 'stage': 'UNDER_REVIEW'},

        # Pune Family Support & Adoption Center
        {'trust_name': 'Pune Family Support & Adoption Center', 'adopter_email': 'sunita@example.com', 'adopter_name': 'Sunita Joshi', 'status': 'APPROVED', 'stage': 'APPROVED'},

        # Karnataka Adoption Support Foundation
        {'trust_name': 'Karnataka Adoption Support Foundation', 'adopter_email': 'vikram@example.com', 'adopter_name': 'Vikram Rao', 'status': 'FURTHER_PROCESS', 'stage': 'FURTHER_PROCESS'},

        # Delhi Child Welfare & Adoption Agency
        {'trust_name': 'Delhi Child Welfare & Adoption Agency', 'adopter_email': 'amitabh@example.com', 'adopter_name': 'Amitabh Sharma', 'status': 'TRUST_REVIEW', 'stage': 'TRUST_REVIEW'},

        # Kerala Adoption Resource Center
        {'trust_name': 'Kerala Adoption Resource Center', 'adopter_email': 'lakshmi@example.com', 'adopter_name': 'Lakshmi Menon', 'status': 'UNDER_REVIEW', 'stage': 'UNDER_REVIEW'},

        # West Bengal Child Rights & Adoption Society
        {'trust_name': 'West Bengal Child Rights & Adoption Society', 'adopter_email': 'subhash@example.com', 'adopter_name': 'Subhash Roy', 'status': 'APPROVED', 'stage': 'APPROVED'},

        # Telangana Child Protection & Adoption Bureau
        {'trust_name': 'Telangana Child Protection & Adoption Bureau', 'adopter_email': 'rajesh@example.com', 'adopter_name': 'Rajesh Reddy', 'status': 'SUBMITTED', 'stage': 'SUBMITTED'},

        # Gujarat Adoption Support Agency
        {'trust_name': 'Gujarat Adoption Support Agency', 'adopter_email': 'bhavna@example.com', 'adopter_name': 'Bhavna Patel', 'status': 'TRUST_REVIEW', 'stage': 'TRUST_REVIEW'}
    ]

    for spec in trust_application_specs:
        t_name = spec['trust_name']
        t_id = trust_id_map.get(t_name)
        if not t_id:
            continue

        a_email = spec['adopter_email']
        a_id = adopter_id_str if a_email == 'user@example.com' else demo_adopter_ids.get(a_email)
        req_id = f"ADP{app_counter}"
        app_counter += 1

        req_doc = {
            'request_id': req_id,
            'adopter_id': a_id,
            'trust_id': t_id,
            'status': spec['status'],
            'created_at': now_iso,
            'updated_at': now_iso
        }
        db.adoption_requests.insert_one(req_doc)

        app_doc = {
            'application_id': req_id,
            'adopter_id': a_id,
            'trust_id': t_id,
            'applicant_name': spec['adopter_name'],
            'applicant_email': a_email,
            'status': spec['status'],
            'marital_status': 'Married',
            'preferred_age_group': '0-2 years',
            'created_at': now_iso,
            'updated_at': now_iso
        }
        db.adoption_applications.insert_one(app_doc)

        journey_doc = {
            'request_id': req_id,
            'adopter_id': a_id,
            'registration': True,
            'profile_completed': True,
            'request_sent': True,
            'trust_review': spec['stage'] in ['TRUST_REVIEW', 'UNDER_REVIEW', 'APPROVED', 'FURTHER_PROCESS', 'COMPLETED'],
            'approved': spec['stage'] in ['APPROVED', 'FURTHER_PROCESS', 'COMPLETED'],
            'further_process': spec['stage'] in ['FURTHER_PROCESS', 'COMPLETED'],
            'completed': spec['stage'] == 'COMPLETED',
            'current_stage': spec['stage'],
            'updated_at': now_iso
        }
        db.journeys.insert_one(journey_doc)

        db.notifications.insert_one({
            'user_id': a_id,
            'message': f"Application {req_id} sent to {t_name}. Status: {spec['status']}",
            'type': 'application',
            'is_read': False,
            'created_at': now_iso
        })

    # Initial Welcome Notification for Primary Adopter
    db.notifications.insert_one({
        'user_id': adopter_id_str,
        'message': 'Welcome to Smart Child Adoption Support Platform! Your profile is complete.',
        'type': 'registration',
        'is_read': False,
        'created_at': now_iso
    })

    # 6. Sample Child Profiles for EVERY TRUST (1 to 2 profiles per trust)
    ch_counter = 101
    sample_children_list = []

    for t_name, t_id in trust_id_map.items():
        sample_children_list.append({
            'child_id': f"CH-{ch_counter}",
            'trust_id': t_id,
            'child_name': f"Child Profile {ch_counter} (Infant)",
            'age_range': '0-2 years',
            'gender': 'Female' if ch_counter % 2 == 0 else 'Male',
            'language': 'English / Local',
            'location_region': t_name.split(' ')[0],
            'authorized_support_category': 'General Adoption Support',
            'available_for_matching': True,
            'status': 'AVAILABLE',
            'created_at': now_iso,
            'updated_at': now_iso
        })
        ch_counter += 1

        sample_children_list.append({
            'child_id': f"CH-{ch_counter}",
            'trust_id': t_id,
            'child_name': f"Child Profile {ch_counter} (Toddler)",
            'age_range': '2-4 years',
            'gender': 'Male' if ch_counter % 2 == 0 else 'Female',
            'language': 'English / Local',
            'location_region': t_name.split(' ')[0],
            'authorized_support_category': 'Special Care Support',
            'available_for_matching': True,
            'status': 'AVAILABLE',
            'created_at': now_iso,
            'updated_at': now_iso
        })
        ch_counter += 1

    db.child_profiles.insert_many(sample_children_list)

    print(f"Database seeding completed successfully! Mapped logins and demo applications for {len(trust_id_map)} Trusts.")

if __name__ == '__main__':
    seed()
