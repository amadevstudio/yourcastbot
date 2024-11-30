import copy


class Serializable(object):
	def deepcopy2dict(self):
		return obj2dict(copy.deepcopy(self))


class Dict2obj(object):
	def __init__(self, d):
		for a, b in d.items():
			if isinstance(b, (list, tuple)):
				setattr(self, a, [Dict2obj(x) if isinstance(x, dict) else x for x in b])
			else:
				setattr(self, a, Dict2obj(b) if isinstance(b, dict) else b)

	def deepcopy(self):
		return copy.deepcopy(self)

	def deepcopy2dict(self):
		return obj2dict(copy.deepcopy(self))

	def encodedStr(self):
		return str(self.deepcopy2dict()).encode('utf-8')


def obj2dict(obj):
	if not hasattr(obj, "__dict__"):
		return obj
	new_subdic = vars(obj)
	for key, value in new_subdic.items():
		new_subdic[key] = obj2dict(value)
	return new_subdic
