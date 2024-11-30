# pip install pydub
from pydub import AudioSegment
import mutagen
import datetime

from lib.tools.logger import logger


def compress_audio(fname, bitrate):
	try:
		print(
			"compressing audio to: " + str(bitrate) + "; ",
			datetime.datetime.now(), flush=True)
		# без easy: f.tags.getall('TIT2') для названия
		f = mutagen.File(fname, easy=True)
		file_bitrate = f.info.bitrate / 1000
		if file_bitrate < bitrate:
			return fname

		ainfo = {}
		tags_saving = ['title', 'album', 'artist', 'genre', 'year']
		for t in tags_saving:
			try:
				ainfo[t] = f[t][0]
			except Exception:
				ainfo[t] = ''
		sound = AudioSegment.from_file(fname)

		fname_splitted = fname.split('.')
		fname_compressed = '.'.join(fname_splitted[0:-1]) \
			+ '_compressed.' + fname_splitted[-1]

		sound.export(
			fname_compressed,
			format="mp3",
			bitrate=str(bitrate) + 'k',
			# заголовок, исполнитель, альбом, жанр (Podcast), год
			tags=ainfo)
		return fname_compressed

	except Exception as e:
		logger.err(e)
		return fname


# compress_audio("/home/kinton/Downloads/08 Blood in the Cut.flac", int('64'))
