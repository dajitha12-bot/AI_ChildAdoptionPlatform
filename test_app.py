import unittest
import io
from app import app
from seed.seed_data import seed
from database.mongodb import db

class SmartAdoptionEnhancedTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        seed()

    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'SMART CHILD ADOPTION PLATFORM', response.data)

    def test_adopter_verified_agencies_and_filters(self):
        # Login as adopter
        self.client.post('/login', data={
            'email': 'user@example.com',
            'password': 'User@123',
            'role': 'adopter'
        }, follow_redirects=True)

        # Access Verified Agencies Directory
        res = self.client.get('/adopter/trusts')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'ABC Adoption Support Trust', res.data)
        self.assertIn(b'Hope Adoption', res.data)

        # Filter by State = Maharashtra
        res_mh = self.client.get('/adopter/trusts?state=Maharashtra')
        self.assertEqual(res_mh.status_code, 200)
        self.assertIn(b'Maharashtra Child Adoption Society', res_mh.data)

    def test_public_api_agencies_endpoints(self):
        # GET /api/agencies
        res = self.client.get('/api/agencies?state=Tamil%20Nadu')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(data['count'], 0)

        # GET /api/agencies/<id>
        agency_id = data['agencies'][0]['id']
        res_single = self.client.get(f'/api/agencies/{agency_id}')
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.get_json()['id'], agency_id)

    def test_admin_trust_data_management_and_deactivation(self):
        # Login as admin
        self.client.post('/login', data={
            'email': 'admin@smartadoption.org',
            'password': 'Admin@123',
            'role': 'admin'
        }, follow_redirects=True)

        # Access Trust Data Management
        res_admin = self.client.get('/admin/trust-data-management')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'Trust Data Management', res_admin.data)
        self.assertIn(b'Total Agencies', res_admin.data)

        # Fetch an active agency ID
        active_agency = db.trusts.find_one({'verified': True, 'status': 'ACTIVE'})
        self.assertIsNotNone(active_agency)
        agency_id = str(active_agency['_id'])

        # Deactivate Agency
        res_deact = self.client.post(f'/admin/trust/deactivate/{agency_id}', follow_redirects=True)
        self.assertEqual(res_deact.status_code, 200)
        self.assertIn(b'DEACTIVATED', res_deact.data)

        # Verify agency is EXCLUDED from adopter search
        self.client.post('/login', data={
            'email': 'user@example.com',
            'password': 'User@123',
            'role': 'adopter'
        }, follow_redirects=True)

        res_search = self.client.get(f'/api/agencies?search={active_agency["trust_name"]}')
        self.assertEqual(res_search.get_json()['count'], 0)

    def test_csv_import_and_export(self):
        # Login as admin
        self.client.post('/login', data={
            'email': 'admin@smartadoption.org',
            'password': 'Admin@123',
            'role': 'admin'
        }, follow_redirects=True)

        # Test CSV Export
        res_export = self.client.get('/admin/trust/export-csv')
        self.assertEqual(res_export.status_code, 200)
        self.assertIn(b'Agency Name', res_export.data)

        # Test CSV Import
        sample_csv = (
            "agency_name,state,district,city,public_address,phone,email,website,languages,agency_type,verified,verification_source,source_url,last_verified,status\n"
            '"Test Import SAA","Kerala","Wayanad","Kalpetta","Address","+91 9400011223","test@keralaadoption.org","https://keralaadoption.org","Malayalam, English","Specialized Adoption Agency (SAA)",true,"CARA","https://cara.wcd.gov.in","2026-09-01T00:00:00Z","ACTIVE"\n'
        )
        data = {'csv_file': (io.BytesIO(sample_csv.encode('utf-8')), 'test_import.csv')}
        res_import = self.client.post('/admin/trust/import-csv', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res_import.status_code, 200)
        self.assertIn(b'CSV Import Completed', res_import.data)

    def test_ai_database_grounded_agency_search(self):
        # Login as adopter
        self.client.post('/login', data={
            'email': 'user@example.com',
            'password': 'User@123',
            'role': 'adopter'
        }, follow_redirects=True)

        # Grounded AI Agency Search Request
        res_ai = self.client.post('/api/ai/agency-search', json={
            'question': 'I am from Madurai and prefer Tamil. Which verified adoption agencies can I approach?',
            'language': 'English'
        })
        self.assertEqual(res_ai.status_code, 200)
        json_data = res_ai.get_json()
        self.assertIn('agencies', json_data)
        self.assertGreater(len(json_data['agencies']), 0)
        self.assertIn('ABC Adoption Support Trust', [a['agency_name'] for a in json_data['agencies']])

if __name__ == '__main__':
    unittest.main()
