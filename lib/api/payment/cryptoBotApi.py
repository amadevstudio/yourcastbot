import requests
import json
import hashlib
import hmac

class CryptoBotApi:

	DEFAULT_API_OPTIONS = {
		"proto": "https",
		"api_path": "api",

		"token_header_name": "Crypto-Pay-API-Token"
	}
	MAINNET_API_OPTIONS = {
		"host": "pay.crypt.bot"
	}
	TESTNET_API_OPTIONS = {
		"host": "testnet-pay.crypt.bot"
	}

	ASSETS = {
		"BTC": "Bitcoin",
		"TON": "Toncoin",
		"ETH": "Etherium",
		"USDT": "Tether",
		"USDC": "USD Coin",
		"BNB": "Binance Coin"
	}
	AVAILABLE_ASSETS = ["BTC", "TON", "USDT", "USDC"]

	PAID_BUTTONS_NAMES = {
		"VIEW_ITEM": "viewItem",
		"OPEN_CHANNEL": "openChannel",
		"OPEN_BOT": "openBot",
		"CALLBACK": "callback",
	}

	UPDATE_TYPES = ["invoice_paid"]

	def __init__(self, token, net="mainnet"):
		self.__token = token

		if net == "testnet":
			host = self.TESTNET_API_OPTIONS["host"]
		else:
			host = self.MAINNET_API_OPTIONS["host"]

		self.__apiPath = "{proto}://{host}/api".format(
			proto=self.DEFAULT_API_OPTIONS["proto"], host=host)

	# Requester
	def __makeRequest(self, method, params={}):
		url = f"{self.__apiPath}/{method}"
		headers = {self.DEFAULT_API_OPTIONS["token_header_name"]: self.__token}

		for paramName in list(params):
			if params[paramName] is None:
				del params[paramName]

		answer = requests.get(url, headers=headers, params=params)

		data = answer.json()

		if not data["ok"]:
			message = {}
			message["error"] = "API call failed"
			if data["error"]:
				message["api_error"] = data["error"]

			raise LookupError(json.dumps(message))

		return data["result"]

	# Api methods
	def getMe(self):
		return self.__makeRequest("getMe")

	def getBalance(self):
		return self.__makeRequest("getBalance")

	def getExchangeRates(self):
		results = self.__makeRequest("getExchangeRates")
		ratesObject = {}
		for rate in results:
			if rate["is_valid"]:
				if rate["source"] not in ratesObject:
					ratesObject[rate["source"]] = {}
				ratesObject[rate["source"]][rate["target"]] = rate["rate"]
		return ratesObject

	def getExchangeRate(self, asset):
		exchangeRates = self.getExchangeRates()
		return exchangeRates.get(asset, None)

	def getCurrencies(self):
		return self.__makeRequest("getCurrencies")

	def getInvoices(
		self, asset=None, invoice_ids=None,  # separated by comma
		status=None,  # active, paid, default: all statuses
		offset=None, count=None
	):
		params = {
			"asset": asset, "invoice_ids": invoice_ids,
			"status": status, "offset": offset, "count": count
		}
		return self.__makeRequest("getInvoices", params)

	def createInvoice(
		self, asset, amount,
		description=None, paid_btn_name=None, paid_btn_url=None, payload=None,
		allow_comments=None, allow_anonymous=None
	):
		params = {
			"asset": asset, "amount": amount,
			"description": description, "paid_btn_name": paid_btn_name,
			"paid_btn_url": paid_btn_url, "payload": payload,
			"allow_comments": allow_comments, "allow_anonymous": allow_anonymous
		}

		return self.__makeRequest("createInvoice", params)

	def isDataSignatureCorrect(self, body_string, signature):
		cryptoBotApiSha256 = hashlib.sha256(self.__token.encode()).digest()
		code = hmac.new(
			cryptoBotApiSha256, body_string.encode(),
			hashlib.sha256).hexdigest()

		return code == signature
