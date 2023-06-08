import requests
import json
import os

api_host = os.environ.get("EXTENDED_API_HOST", "domino-extendedapi-svc.domino-platform")
api_port = os.environ.get("EXTENDED_API_PORT", "80")
url = f"http://{api_host}:{api_port}/v4-extended/autoshutdownwksrules"

payload = json.dumps({
  "users": {
    "wadkars": 3600,
    "integration-test": 21600
  },
  "override_to_default": False
})
headers = {
  'X-Domino-Api-Key': os.environ.get('DOMINO_USER_API_KEY'),
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)

## Alternatively from inside the workspace you could run. This is a safer approach to using the API Key

access_token_endpoint='http://localhost:8899/access-token'
resp = requests.get(access_token_endpoint)


token = resp.text
headers = {
             "Content-Type": "application/json",
             "Authorization": "Bearer " + token,
        }
response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
