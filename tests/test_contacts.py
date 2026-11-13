"""Exercise persistence and validation without touching the real collection."""
import tempfile
import unittest
from pathlib import Path

import db
from main import app


class ContactsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / 'test.db'
        db.init_db()
        self.client = app.test_client()

    def tearDown(self):
        db.DATABASE_PATH = self.previous_path
        self.temp.cleanup()

    def test_contact_lifecycle_and_persistence(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/health').json, {'status': 'ok'})
        result = self.client.post('/api/contacts', json={'name': 'Demo Person', 'email': 'demo@example.com', 'event': 'Demo Expo'})
        self.assertEqual(result.status_code, 201)
        contact_id = result.json['id']
        # Re-running startup schema must preserve the saved record.
        db.init_db()
        self.assertEqual(self.client.get('/api/contacts').json[0]['name'], 'Demo Person')
        self.assertEqual(self.client.put('/api/contacts/' + contact_id, json={'name': 'Updated Person'}).status_code, 200)
        self.assertEqual(self.client.get('/api/contacts').json[0]['name'], 'Updated Person')
        self.assertEqual(self.client.delete('/api/contacts/' + contact_id).status_code, 200)
        self.assertEqual(self.client.get('/api/contacts').json, [])

    def test_invalid_fields_and_duplicates(self):
        for payload in ({}, {'name': '   '}, {'name': 9}, {'name': 'x' * 151}, {'name': 'Demo', 'email': 'bad-email'}):
            self.assertEqual(self.client.post('/api/contacts', json=payload).status_code, 400)
        self.client.post('/api/contacts', json={'name': 'Demo', 'email': 'same@example.com'})
        self.assertEqual(self.client.post('/api/contacts', json={'name': 'Other', 'email': 'SAME@example.com'}).status_code, 409)
        self.assertEqual(self.client.put('/api/contacts/missing', json={'name': 'Nobody'}).status_code, 404)
        self.assertEqual(self.client.delete('/api/contacts/missing').status_code, 404)

    def test_user_text_remains_data(self):
        value = '<script>alert(1)</script>'
        self.client.post('/api/contacts', json={'name': value, 'notes': "'); DROP TABLE contacts;--"})
        self.assertEqual(self.client.get('/api/contacts').json[0]['name'], value)
        self.assertEqual(len(self.client.get('/api/contacts').json), 1)


if __name__ == '__main__':
    unittest.main()
