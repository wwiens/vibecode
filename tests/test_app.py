"""Behavior and deployment-contract checks; uses only isolated temporary SQLite data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import main

class AppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_path = main.DATABASE_PATH
        main.DATABASE_PATH = Path(self.temporary.name) / 'app.db'
        main.initialize()
        self.client = main.app.test_client()

    def tearDown(self):
        main.DATABASE_PATH = self.original_path
        self.temporary.cleanup()

    def test_home_health_and_bundled_assets(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/health').json, {'status':'ok'})
        catalog = self.client.get('/api/catalog').json
        self.assertEqual(len(catalog['titles']), 18)
        for item in catalog['titles']:
            for key in ('image','backdrop'):
                response = self.client.get(item[key])
                self.assertEqual(response.status_code, 200, item[key])
                response.close()
        video = self.client.get(catalog['demo_video'], headers={'Range':'bytes=0-100'})
        self.assertEqual(video.status_code, 206)
        self.assertEqual(len(video.data), 101)
        video.close()

    def test_search_genres_types_and_kids_restriction(self):
        self.assertEqual([t['id'] for t in self.client.get('/api/catalog?q=chalamet').json['titles']], ['dune'])
        self.assertTrue(all(t['type'] == 'movie' and 'Sci-Fi' in t['genres'] for t in self.client.get('/api/catalog?type=movie&genre=Sci-Fi').json['titles']))
        self.assertEqual(self.client.get('/api/catalog?q=unlikely-no-results').json['titles'], [])
        kids = self.client.get('/api/catalog?profile=3').json['titles']
        self.assertEqual([t['id'] for t in kids], ['spiderverse'])
        self.assertEqual(self.client.put('/api/saved/dune?profile=3',json={'in_list':True}).status_code, 400)
        self.assertEqual(self.client.put('/api/progress/dune?profile=3',json={'position':1,'duration':50}).status_code, 400)

    def test_watchlist_likes_profile_isolation_and_removal(self):
        self.assertEqual(self.client.put('/api/saved/dune',json={'in_list':True}).status_code, 200)
        self.client.put('/api/saved/dune',json={'liked':True})
        record = self.client.get('/api/state').json['saved'][0]
        self.assertEqual((record['in_list'],record['liked']), (1,1))
        self.assertEqual(self.client.get('/api/state?profile=2').json['saved'], [])
        self.client.put('/api/saved/dune',json={'in_list':False})
        record = self.client.get('/api/state').json['saved'][0]
        self.assertEqual((record['in_list'],record['liked']), (0,1))
        main.initialize()
        self.assertEqual(self.client.get('/api/state').json['saved'][0]['liked'], 1)

    def test_profiles_validation_and_cascading_delete(self):
        for invalid in ('', 'x'*21, 5, None):
            self.assertEqual(self.client.post('/api/profiles',json={'name':invalid}).status_code, 400)
        response = self.client.post('/api/profiles',json={'name':'Test viewer','color':'green'})
        self.assertEqual(response.status_code, 201)
        id = response.json['id']
        self.client.put(f'/api/saved/dune?profile={id}',json={'in_list':True})
        self.client.put(f'/api/progress/dune?profile={id}',json={'position':12,'duration':52})
        self.client.patch(f'/api/profiles/{id}',json={'name':'Renamed','autoplay':False})
        self.assertEqual(self.client.get(f'/api/state?profile={id}').json['profile']['name'], 'Renamed')
        self.assertEqual(self.client.delete(f'/api/profiles/{id}').status_code, 200)
        with main.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM saved WHERE profile_id=?',(id,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM progress WHERE profile_id=?',(id,)).fetchone()[0],0)

    def test_progress_validation_resume_episodes_and_delete(self):
        self.client.put('/api/progress/stranger-things',json={'position':15,'duration':52,'episode':2})
        self.client.put('/api/progress/stranger-things',json={'position':22,'duration':52,'episode':2})
        result = self.client.get('/api/state').json['progress']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['position'],22)
        self.assertEqual(result[0]['episode'],2)
        for payload in ({'position':-1,'duration':52}, {'position':100,'duration':50}, {'position':'bad'}, {'position':1,'duration':50,'episode':100}, {'position':float('nan'),'duration':50}):
            self.assertEqual(self.client.put('/api/progress/stranger-things',json=payload).status_code,400)
        self.assertEqual(self.client.put('/api/progress/dune',json={'position':1,'duration':52,'episode':2}).status_code,400)
        self.client.delete('/api/progress/stranger-things')
        self.assertEqual(self.client.get('/api/state').json['progress'],[])

    def test_invalid_requests_are_json_and_profile_limit(self):
        self.assertEqual(self.client.post('/api/profiles',data='bad',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post('/api/profiles',json=[]).status_code,400)
        self.assertEqual(self.client.put('/api/saved/not-a-title',json={'in_list':True}).status_code,400)
        self.assertEqual(self.client.put('/api/saved/dune',json={'in_list':'yes'}).status_code,400)
        self.assertEqual(self.client.get('/api/catalog?profile=999').status_code,400)
        self.assertEqual(self.client.get('/api/catalog?profile=abc').status_code,400)
        self.assertEqual(self.client.get('/api/not-found').status_code,404)
        self.assertIn('error',self.client.get('/api/not-found').json)
        self.client.post('/api/profiles',json={'name':'four'})
        self.client.post('/api/profiles',json={'name':'five'})
        self.assertEqual(self.client.post('/api/profiles',json={'name':'six'}).status_code,400)
        for id in range(2,6): self.client.delete(f'/api/profiles/{id}')
        self.assertEqual(self.client.delete('/api/profiles/1').status_code,400)

    def test_restart_preserves_volume_records_and_startup_requires_volume(self):
        environment = os.environ.copy()
        environment['RAILWAY_ENVIRONMENT_ID'] = 'test-environment'
        environment.pop('RAILWAY_VOLUME_MOUNT_PATH',None)
        failure = subprocess.run([sys.executable,'-c','import main'],env=environment,capture_output=True,text=True)
        self.assertNotEqual(failure.returncode,0)
        self.assertIn('attach a Railway volume at /data',failure.stderr)
        environment['RAILWAY_VOLUME_MOUNT_PATH'] = self.temporary.name
        create = "import main; c=main.app.test_client(); assert c.put('/api/saved/dune',json={'in_list':True}).status_code==200"
        subprocess.run([sys.executable,'-c',create],env=environment,check=True,capture_output=True)
        read = "import main; c=main.app.test_client(); assert c.get('/api/state').json['saved'][0]['in_list']==1; print('retained')"
        result = subprocess.run([sys.executable,'-c',read],env=environment,check=True,capture_output=True,text=True)
        self.assertIn('retained',result.stdout)

if __name__ == '__main__':
    unittest.main()
