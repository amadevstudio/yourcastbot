import sys
import requests
import json

# from lxml import etree
itunes_id = sys.argv[1]

payload = {'entity': 'podcast', 'id': itunes_id}
api_url_base = 'https://itunes.apple.com/lookup'
response = requests.get(api_url_base, params=payload)

loaded_json = json.loads(response.content.decode('utf-8'))["results"]

if len(sys.argv) > 2 and sys.argv[2] == 'sir':
	sir = True
	print(loaded_json, flush=True)
	print("\n\nRSS:\n", flush=True)
else:
	sir = False

rss = None
for result in loaded_json:
	if "feedUrl" in result:
		rss = requests.get(result["feedUrl"])
		collectionName = result["collectionName"]
		feedUrl = result["feedUrl"]
		lastDate = result["releaseDate"]
		itunesLink = result["collectionViewUrl"]

		# root = etree.fromstring(rss.content).getchildren()[0]
		print(rss.content, flush=True)
		break

if rss is None and not sir:
	print(
		"No rss founded, try \npython "
		+ sys.path[0] + "/get_rss.py " + str(itunes_id) + " sir")
