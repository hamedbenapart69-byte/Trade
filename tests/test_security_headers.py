import os, unittest
from fastapi.testclient import TestClient
from app.main import app

class SecurityHeadersTests(unittest.TestCase):
 def setUp(self):
  os.environ['CONTROL_API_TOKEN']='headers-control-token-long-enough-123456'
  self.client=TestClient(app)
 def tearDown(self):
  self.client.close(); os.environ.pop('CONTROL_API_TOKEN',None)
 def test_security_headers_are_set(self):
  r=self.client.get('/health')
  self.assertEqual(r.status_code,200)
  self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')
  self.assertEqual(r.headers['X-Frame-Options'],'DENY')
  self.assertEqual(r.headers['Referrer-Policy'],'no-referrer')
  self.assertEqual(r.headers['Cache-Control'],'no-store')
  self.assertIn("default-src 'self'",r.headers['Content-Security-Policy'])
  self.assertIn("object-src 'none'",r.headers['Content-Security-Policy'])
  self.assertIn('camera=()',r.headers['Permissions-Policy'])
if __name__=='__main__': unittest.main()
