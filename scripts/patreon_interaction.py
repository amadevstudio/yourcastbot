import patreon

creator_access_token = "6jzw4B9fOW-QOEBJ64szhxdU1fJ-0mWO8CSYid8ZrfY"

api_client = patreon.API(creator_access_token)
# print(dir(api_client))
campaign_id = api_client.fetch_campaign_and_patrons().data()[0].id()
pledges_response = api_client.fetch_page_of_pledges(
    campaign_id,
    25,
)

# names = []
all_pledges = pledges_response.data()
# print(all_pledges)
# for pledge in all_pledges:
#     patron_id = pledge.relationship('patron').id()
#     # x = pledge.relationship('patron').attributes()
#     # print(x)
#     # patron = find_resource_by_type_and_id('user', patron_id)
#     # names.append(patron.attribute('full_name'))
#     names.append(patron_id)

# https://docs.patreon.com/?python#campaign
names_and_membershipss = [{
    # 'attributes': member.attributes(),
    # 'relationships': member.relationships(),
    'cents': member.attribute('amount_cents'),
    'currency': member.attribute('currency'),
    'user': member.relationship('patron').attribute('email'),
    'declined_cinse': member.attribute('declined_since'),
    'status': member.attribute('status'),
    'is_paused': member.attribute('is_paused'),
    # 'user_id': member.relationships()['patron']['data']['id'],
} for member in all_pledges]

print(names_and_membershipss)
