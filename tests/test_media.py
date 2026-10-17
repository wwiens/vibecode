"""Upload lifecycle, persistence, range streaming, validation, and concurrency."""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import main
import media_store


def box(kind, payload):
    return struct.pack('>I4s',len(payload)+8,kind)+payload

# Small structural fixture. Real video playback is checked with the bundled Sintel MP4.
MP4 = box(b'ftyp',b'mp42'+bytes(4)+b'isommp42') + box(b'moov',box(b'mvhd',bytes(12)+struct.pack('>II',1000,52000)+bytes(20))+box(b'trak',box(b'mdia',box(b'hdlr',bytes(8)+b'vide'+bytes(12))))) + box(b'mdat',bytes(128))
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j9ioAAAAASUVORK5CYII=')

class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.original_root,self.original_db=main.DATA_DIR,main.DATABASE_PATH
        main.DATA_DIR=Path(self.temporary.name)
        main.DATABASE_PATH=main.DATA_DIR/'app.db'
        main.initialize()
        self.client=main.app.test_client()

    def tearDown(self):
        main.DATA_DIR,main.DATABASE_PATH=self.original_root,self.original_db
        self.temporary.cleanup()

    def start(self,data=MP4,**metadata):
        payload=dict(filename='movie.mp4',size=len(data),fingerprint=hashlib.sha256(data[:65536]).hexdigest(),duration=52,title='My short film',year=2026,type='movie',genres=['Independent'],rating='NR',family=False)
        payload.update(metadata)
        return self.client.post('/api/uploads',json=payload)

    def chunk(self,id,data,offset=0,client=None,**headers):
        return (client or self.client).patch('/api/uploads/'+id,data=data,content_type='application/octet-stream',headers={'Upload-Offset':str(offset),'X-Chunk-SHA256':hashlib.sha256(data).hexdigest(),**headers})

    def publish(self,data=MP4,**metadata):
        response=self.start(data,**metadata)
        self.assertEqual(response.status_code,201,response.json)
        id=response.json['upload']['id']
        for offset in range(0,len(data),media_store.CHUNK_BYTES):
            response=self.chunk(id,data[offset:offset+media_store.CHUNK_BYTES],offset)
            self.assertEqual(response.status_code,200,response.json)
        response=self.client.post('/api/uploads/'+id+'/complete',json={})
        self.assertEqual(response.status_code,201,response.json)
        return response.json

    def test_real_video_upload_catalog_range_download_watchlist_and_resume(self):
        real=Path('static/video/sintel-trailer.mp4').read_bytes()
        result=self.publish(real,filename='../../Sintel trailer.mp4')
        title=next(t for t in self.client.get('/api/catalog').json['titles'] if t['id']==result['title_id'])
        self.assertTrue(title['uploaded'])
        self.assertAlmostEqual(title['episodes'][0]['duration'],52.208333,places=2)
        self.assertEqual(title['episodes'][0]['original_name'],'Sintel_trailer.mp4')
        url=title['video_url']
        response=self.client.get(url,headers={'Range':'bytes=100-299'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.data,real[100:300])
        self.assertEqual(response.headers['Content-Range'],f'bytes 100-299/{len(real)}')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        etag=response.headers['ETag'];response.close()
        response=self.client.get(url,headers={'Range':'bytes=-64'})
        self.assertEqual(response.data,real[-64:]);response.close()
        response=self.client.get(url,headers={'Range':f'bytes={len(real)+5}-'})
        self.assertEqual(response.status_code,416)
        response=self.client.head(url)
        self.assertEqual(int(response.headers['Content-Length']),len(real));response.close()
        response=self.client.get(url,headers={'If-None-Match':etag})
        self.assertEqual(response.status_code,304);response.close()
        response=self.client.get(url+'?download=1')
        self.assertIn('attachment',response.headers['Content-Disposition']);response.close()
        self.assertEqual(self.client.put('/api/saved/'+title['id'],json={'in_list':True}).status_code,200)
        self.assertEqual(self.client.put('/api/progress/'+title['id'],json={'episode':1,'position':20,'duration':52}).status_code,200)
        state=self.client.get('/api/state').json
        self.assertEqual(state['saved'][0]['title_id'],title['id'])
        self.assertEqual(state['progress'][0]['position'],20)
        self.assertEqual(self.client.get('/api/state?profile=2').json['progress'],[])
        self.assertEqual(self.client.post('/api/uploads/'+result['video_id']+'/complete',json={}).status_code,200)
        main.initialize()
        self.assertEqual(len(self.client.get('/api/library').json['titles']),1)

    def test_resume_survives_fresh_python_process_and_ignores_uncommitted_tail(self):
        session=self.start().json['upload'];id=session['id']
        half=len(MP4)//2
        self.assertEqual(self.chunk(id,MP4[:half]).status_code,200)
        # Simulate a process stopping after writing a chunk but before committing its offset.
        with (main.DATA_DIR/'media'/'pending'/f'{id}.part').open('ab') as handle:
            handle.write(b'uncommitted bytes')
        environment=os.environ.copy();environment['RAILWAY_ENVIRONMENT_ID']='test';environment['RAILWAY_VOLUME_MOUNT_PATH']=str(main.DATA_DIR)
        script="""import base64,hashlib,main,sys
c=main.app.test_client();id=sys.argv[1];offset=int(sys.argv[2]);data=base64.b64decode(sys.argv[3])
assert c.get('/api/uploads/'+id).json['upload']['offset']==offset
r=c.patch('/api/uploads/'+id,data=data,content_type='application/octet-stream',headers={'Upload-Offset':str(offset),'X-Chunk-SHA256':hashlib.sha256(data).hexdigest()});assert r.status_code==200,r.json
r=c.post('/api/uploads/'+id+'/complete',json={});assert r.status_code==201,r.json
print(r.json['title_id'])
"""
        done=subprocess.run([sys.executable,'-c',script,id,str(half),base64.b64encode(MP4[half:]).decode()],env=environment,capture_output=True,text=True,check=True)
        self.assertIn('upload-',done.stdout)
        video=self.client.get('/api/library').json['titles'][0]['video_url']
        response=self.client.get(video);self.assertEqual(response.data,MP4);response.close()

    def test_bad_chunks_offsets_checksum_limits_and_incomplete_finish(self):
        id=self.start().json['upload']['id']
        self.assertEqual(self.client.post('/api/uploads/'+id+'/complete',json={}).status_code,409)
        self.assertEqual(self.chunk(id,MP4[:30],5).status_code,409)
        self.assertEqual(self.chunk(id,MP4[:30],**{'X-Chunk-SHA256':'0'*64}).status_code,422)
        self.assertEqual(self.chunk(id,b'').status_code,400)
        self.assertEqual(self.chunk(id,MP4+b'overflow').status_code,400)
        self.assertEqual(self.client.patch('/api/uploads/'+id,data=b'x',content_type='text/plain').status_code,415)
        self.assertEqual(self.client.get('/api/uploads/'+id).json['upload']['offset'],0)
        response=self.client.patch('/api/uploads/'+id,data=b'x'*(media_store.CHUNK_BYTES+1),content_type='application/octet-stream')
        self.assertEqual(response.status_code,413)
        self.assertEqual(self.client.get('/api/uploads/'+id).json['upload']['offset'],0)

    def test_simultaneous_chunk_retries_do_not_duplicate_data(self):
        id=self.start().json['upload']['id']
        def append(_):
            with main.app.test_client() as client:return self.chunk(id,MP4,client=client).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(append,range(2))),[200,409])
        self.assertEqual((main.DATA_DIR/'media'/'pending'/f'{id}.part').read_bytes(),MP4)
        self.assertEqual(self.client.get('/api/uploads/'+id).json['upload']['offset'],len(MP4))

    def test_file_type_spoofing_audio_only_and_mismatched_fingerprint(self):
        self.assertEqual(self.start(filename='file.html').status_code,400)
        self.assertEqual(self.start(size=media_store.MAX_VIDEO_BYTES+1).status_code,400)
        for data in (b'<html>'+b'x'*120,MP4.replace(b'vide',b'soun')):
            id=self.start(data).json['upload']['id'];self.chunk(id,data)
            self.assertEqual(self.client.post('/api/uploads/'+id+'/complete',json={}).status_code,400)
            self.assertEqual(self.client.delete('/api/uploads/'+id).status_code,200)
        id=self.start(fingerprint='0'*64).json['upload']['id'];self.chunk(id,MP4)
        self.assertEqual(self.client.post('/api/uploads/'+id+'/complete',json={}).status_code,422)
        self.assertEqual(self.client.get('/api/library').json['titles'],[])
        # Unicode filenames retain a valid generated basename and their video extension.
        self.assertEqual(self.start(filename='电影.mp4').status_code,201)

    def test_capacity_reservation_and_cancellation(self):
        with patch.object(media_store,'LIBRARY_BYTES',len(MP4)*2):
            id=self.start().json['upload']['id']
            before=self.client.get('/api/library').json['storage']
            self.assertEqual(before['reserved_bytes'],len(MP4))
            self.assertEqual(self.start(size=len(MP4)+1).status_code,507)
            self.chunk(id,MP4[:50])
            storage=self.client.get('/api/library').json['storage']
            self.assertEqual(storage['used_bytes'],50)
            self.assertEqual(storage['reserved_bytes'],len(MP4)-50)
            self.assertEqual(self.client.delete('/api/uploads/'+id).status_code,200)
            self.assertFalse((main.DATA_DIR/'media'/'pending'/f'{id}.part').exists())
            self.assertEqual(self.client.get('/api/library').json['storage']['reserved_bytes'],0)
            self.assertEqual(self.client.get('/api/uploads/'+id).status_code,404)
        with patch.object(media_store.shutil,'disk_usage',return_value=type('Disk',(),{'free':media_store.DISK_RESERVE_BYTES})()):
            self.assertEqual(self.start().status_code,507)

    def test_metadata_posters_search_kids_and_origin(self):
        result=self.publish(title='Adult film',genres=['Documentary'])
        id=result['title_id']
        self.assertEqual(self.client.get('/api/library?profile=3').status_code,403)
        self.assertEqual(self.client.post('/api/uploads?profile=3',json={}).status_code,400)
        self.assertEqual(self.client.get('/media/videos/'+result['video_id']+'?profile=3').status_code,404)
        self.assertEqual(self.client.patch('/api/library/'+id,json={'family':True}).status_code,400)
        self.assertEqual(self.client.patch('/api/library/'+id,json={'title':'Family film','rating':'PG','family':True,'genres':['Nature']}).status_code,200)
        self.assertIn(id,[t['id'] for t in self.client.get('/api/catalog?profile=3&q=family').json['titles']])
        self.assertIn('Nature',self.client.get('/api/catalog').json['genres'])
        self.assertEqual(self.client.post('/api/library/'+id+'/poster',data={'file':(io.BytesIO(b'<svg/>'),'unsafe.svg')}).status_code,400)
        response=self.client.post('/api/library/'+id+'/poster',data={'file':(io.BytesIO(PNG),'cover.png')})
        self.assertEqual(response.status_code,200,response.json)
        title=self.client.get('/api/library').json['titles'][0]
        response=self.client.get(title['image']);self.assertEqual(response.data,PNG);response.close()
        self.assertEqual(self.client.post('/api/library/'+id+'/poster',data={'file':(io.BytesIO(PNG),'replacement.png')}).status_code,200)
        self.assertEqual(len(list((main.DATA_DIR/'media'/'posters').iterdir())),1)
        self.assertEqual(self.client.delete('/api/library/'+id+'/poster').status_code,200)
        self.assertEqual(list((main.DATA_DIR/'media'/'posters').iterdir()),[])
        self.assertEqual(self.client.post('/api/uploads',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        response=self.client.post('/api/uploads',json={},headers={'Origin':'https://localhost'})
        self.assertEqual(response.status_code,400) # Same host behind an HTTPS reverse proxy is accepted.

    def test_series_episode_replacement_deletion_and_progress(self):
        first=self.publish(type='series',season=2,episode=4,episode_title='Arrival')
        id=first['title_id']
        second=self.publish(title_id=id,season=2,episode=5,episode_title='Return')
        self.assertEqual(self.client.put('/api/progress/'+id,json={'episode':1004,'position':12,'duration':52}).status_code,200)
        self.assertEqual(self.client.put('/api/progress/'+id,json={'episode':2,'position':12,'duration':52}).status_code,400)
        self.assertEqual(self.start(title_id=id,season=2,episode=4).status_code,409)
        replacement=self.publish(title_id=id,season=2,episode=4,replace=True)
        self.assertEqual(self.client.get('/api/state').json['progress'],[])
        self.assertFalse((main.DATA_DIR/'media'/'videos'/(first['video_id']+'.mp4')).exists())
        self.assertEqual(len(self.client.get('/api/library').json['titles'][0]['episodes']),2)
        self.assertEqual(self.client.delete('/api/library/'+id+'/videos/'+second['video_id']).status_code,200)
        self.assertEqual(self.client.delete('/api/library/'+id+'/videos/'+replacement['video_id']).status_code,409)
        self.client.put('/api/saved/'+id,json={'in_list':True})
        self.publish_poster(id)
        pending=self.start(title_id=id,season=3,episode=1).json['upload']['id'];self.chunk(pending,MP4[:20])
        self.assertEqual(self.client.delete('/api/library/'+id).status_code,200)
        self.assertEqual(self.client.get('/api/library').json['titles'],[])
        self.assertEqual(self.client.get('/api/state').json['saved'],[])
        self.assertEqual(self.client.get('/api/library').json['uploads'],[])
        for directory in ('videos','posters','pending'):
            self.assertEqual(list((main.DATA_DIR/'media'/directory).iterdir()),[])

    def publish_poster(self,id):
        response=self.client.post('/api/library/'+id+'/poster',data={'file':(io.BytesIO(PNG),'cover.png')})
        self.assertEqual(response.status_code,200,response.json)

    def test_restart_recovery_during_finalize_and_deferred_delete_cleanup(self):
        id=self.start().json['upload']['id']
        self.chunk(id,MP4)
        partial=main.DATA_DIR/'media'/'pending'/f'{id}.part'
        published=main.DATA_DIR/'media'/'videos'/f'{id}.mp4'
        partial.replace(published)  # A process stopped immediately after the final rename.
        result=self.client.post('/api/uploads/'+id+'/complete',json={})
        self.assertEqual(result.status_code,201,result.json)
        title=result.json['title_id']
        with patch.object(Path,'unlink',side_effect=OSError('temporarily unavailable')):
            self.assertEqual(self.client.delete('/api/library/'+title).status_code,200)
        self.assertTrue(published.exists())
        # A later management request retries cleanup without restoring the deleted title.
        self.assertEqual(self.client.get('/api/library').json['titles'],[])
        self.assertFalse(published.exists())
        with main.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM media_garbage').fetchone()[0],0)

    def test_webm_validation(self):
        def element(id,payload):
            self.assertLess(len(payload),127)
            return bytes.fromhex(id)+bytes([0x80+len(payload)])+payload
        ebml=element('1a45dfa3',element('4282',b'webm'))
        segment=element('18538067',element('1654ae6b',element('ae',element('83',b'\x01')))+element('1f43b675',b'\x00'*64))
        webm=ebml+segment
        result=self.publish(webm,filename='clip.webm')
        response=self.client.get('/media/videos/'+result['video_id']);self.assertEqual(response.mimetype,'video/webm');response.close()
        self.assertEqual(media_store.inspect_video(main.DATA_DIR/'media'/'videos'/(result['video_id']+'.webm'),'.webm',52),52)

if __name__=='__main__':unittest.main()
