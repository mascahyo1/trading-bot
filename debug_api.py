import time
import hashlib
import hmac
import urllib.parse
import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("indodax_api_key")
secret = os.getenv("indodax_api_secret")

ts = int(time.time() * 1000)
params = {"timestamp": ts, "recvWindow": 5000}
qs = urllib.parse.urlencode(params)
sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()

url = f"https://api.indodax.com/api/v2/account?{qs}"
headers = {
    "Accept": "application/json",
    "X-APIKEY": key,
    "Sign": sig,
    "User-Agent": "Mozilla/5.0",
}

print(f"Key: {key[:20]}...")
print(f"Headers being sent:")
req = urllib.request.Request(url, headers=headers)
for header_name, header_value in req.header_items():
    print(f"  {header_name}: {header_value[:50]}...")

try:
    resp = urllib.request.urlopen(req, timeout=15)
    print("\nResponse:", json.loads(resp.read().decode()))
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print(f"\nHTTP {e.code}: {body[:300]}")
except Exception as e:
    print(f"\nError: {e}")
