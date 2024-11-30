import sys
import requests
import json

search_query = sys.argv[1]

api_url_base = 'https://itunes.apple.com/search'
payload = {'media': 'podcast', 'term': search_query}
response = requests.get(api_url_base, params=payload)

try:
	result = json.loads(response.content.decode('utf-8'))
	print(result, flush=True)
except Exception:
	print({
		"error": "parsingError"
	})
