import json
import urllib.request

url = 'http://127.0.0.1:8000/api/chat'
payload = {'message': 'ping', 'session_id': None, 'user_id': 'user_test'}
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode('utf-8', errors='replace')
        print('STATUS', r.status)
        print(body[:800])
except Exception as e:
    print('ERR', e)
