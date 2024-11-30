import re
from datetime import timezone, datetime

import dateutil.parser
import pytz

from lib.tools.time_tools.timezones import whois_timezone_info


def format_rss_last_date(rss_last_date):
	last_datetime = get_strped_datetime(rss_last_date)

	last_datetime = last_datetime.astimezone(tz=timezone.utc)

	return last_datetime.strftime(
		"%Y-%m-%dT%H:%M:%S%z")  # itunes format: 2021-02-03T07:09:00Z


def prepare_date_time_from_formatted(dt) -> datetime:
	prepared_datetime = get_strped_datetime(dt)

	return prepared_datetime.astimezone(tz=timezone.utc)


def get_strped_datetime(dt) -> datetime:
	original_dt = dt

	# remove empty lines and spaces at start and end
	dt = re.sub(r"^\s*|\s*$|\n", "", dt, 0, re.MULTILINE)

	dt = dt.replace("Lun, ", "") \
		.replace("Ene", "Jan").replace("Abr", "Apr").replace("Ago", "Aug")

	# May == May, Sept -> Sep
	dt = dt.replace("January", "Jan").replace("February", "Feb") \
		.replace("March", "Mar").replace("April", "Apr").replace("June", "Jun") \
		.replace("July", "Jul").replace("August", "Aug").replace("September", "Sep") \
		.replace("Sept", "Sep").replace("October", "Oct").replace("November", "Nov") \
		.replace("December", "Dec")

	# Wen -> Wed
	dt = dt.replace("Wen", "Wed")

	try:
		return dateutil.parser.parse(original_dt, tzinfos=whois_timezone_info)
	except Exception as e:
		try:
			return dateutil.parser.parse(dt, tzinfos=whois_timezone_info)
		except Exception as e:
			pass

	formats = []

	formats.append("%Y-%m-%d")  # 2021-06-02
	formats.append("%Y-%m-%d %H:%M:%S")  # 2021-06-02 15:01:00
	formats.append("%Y-%m-%dT%H:%M:%S%z")  # 2021-06-02T15:01:00+3000

	formats.append("%Y-%m-%dT%H:%M:%S.%f")  # 2021-06-02T15:01:00.123
	formats.append("%Y-%m-%dT%H:%M:%S.%fZ")  # 2021-06-02T15:01:00.123Z

	formats.append("%a, %d %b %Y")  # Wed, 25 Nov 2015
	formats.append("%a, %d %b %Y %H:%M")  # Fri, 19 Feb 2021 03:36
	formats.append("%a, %d %b %Y %H:%M:%S")  # Fri, 19 Feb 2021 03:36:57
	formats.append("%a, %d %b %Y %H:%M %z")  # Fri, 19 Feb 2021 03:36 +3000
	formats.append("%a, %d %b %Y %H:%M:%S %z")  # Fri, 19 Feb 2021 03:36:57 +3000
	formats.append("%a, %d %b %Y %H:%M %Z")  # Fri, 19 Feb 2021 03:36 ZONE
	formats.append("%a, %d %b %Y %H:%M:%S %Z")  # Fri, 19 Feb 2021 03:36:57 ZONE
	formats.append("%a, %dth %B %Y %H:%M:%S %Z")  # Thu, 28th April 2022 7:15:00 GMT

	for fmt in formats:
		try:
			return datetime.strptime(dt, fmt)
		except ValueError:
			pass

	try:
		# rid off time zone
		dt = re.split(r'[+-]\d+', dt)[0]  # +3000 -7
		dt = re.split(' {}'.format("| ".join(pytz.all_timezones)), dt)[0]  # GMT...
		dt = re.split(r' [A-Z]{3}', dt)[0]  # Tue, 23 Jun 2015 17:00:00 PDT

		formats.clear()

		formats.append("%a, %d %b %Y %H:%M:%S")  # Wed, 03 Feb 2021 07:09:00
		formats.append("%a, %d %b %Y %H:%M")  # Wed, 03 Feb 2021 07:09
		formats.append("%d %b %Y %H:%M:%S")  # 03 Feb 2021 07:09:00
		formats.append("%d %b %Y %H:%M")  # 03 Feb 2021 07:09

		formats.append("%a, %d %b %Y")  # Wed, 03 Feb 2021

		for fmt in formats:
			try:
				return datetime.strptime(dt, fmt)
			except ValueError:
				pass

	except Exception:
		pass

	print(
		f"Error mainf.get_strped_datetime no valid {dt} format found original: {original_dt}\n", flush=True)
	# return datetime.now()
	return datetime(1970, 1, 1)
