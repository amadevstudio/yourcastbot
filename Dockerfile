FROM python:3.11.3 as base
WORKDIR /yourcastbot
COPY . .

RUN apt -y update
RUN apt -y install ffmpeg # audio processing

RUN python -m pip install wheel
RUN python -m pip install cython
RUN pip install -r requirements.txt
# RUN pip-upgrade --skip-virtualenv-check

FROM base as dev
CMD ["python", "autoreload.py", "python", "main.py"]
