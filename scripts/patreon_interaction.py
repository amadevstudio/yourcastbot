import json

import requests

from config import (
    patreon_creator_access_token, patreon_subs_perpage,
    patreon_api_v2_url, patreon_request_timeout)

headers = {'Authorization': "Bearer {}".format(patreon_creator_access_token)}

# https://docs.patreon.com/#campaigns
campaigns = requests.get(
    "{}/campaigns".format(patreon_api_v2_url),
    params={'page[count]': 1}, headers=headers,
    timeout=patreon_request_timeout).json()
campaign_id = campaigns['data'][0]['id']

# https://docs.patreon.com/#members
members = requests.get(
    "{}/campaigns/{}/members".format(patreon_api_v2_url, campaign_id),
    params={
        'fields[member]': ','.join([
            'email', 'currently_entitled_amount_cents', 'patron_status',
            'last_charge_date', 'last_charge_status']),
        'page[count]': patreon_subs_perpage,
    },
    headers=headers, timeout=patreon_request_timeout).json()

print(json.dumps(members, indent=2, ensure_ascii=False))
