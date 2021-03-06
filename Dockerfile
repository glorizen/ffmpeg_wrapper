FROM node:10.19-buster-slim

RUN apt update && \
  apt-get install -y python3 python3-pip python3-venv mediainfo && \
  apt-get install -y vim curl zip unzip wget less task-spooler libarchive-zip-perl && \
  ln -s /usr/bin/python3 /usr/bin/python && \
  ln -s /usr/bin/pip3 /usr/bin/pip && \
  python -m venv /.venv/ && \
  apt-get install -y ffmpeg && \
  wget -q -O - https://mkvtoolnix.download/gpg-pub-moritzbunkus.txt | apt-key add - && \
  echo 'deb https://mkvtoolnix.download/debian/ buster main' >> /etc/apt/sources.list.d/mkvtoolnix.download.list && \
  echo 'deb-src https://mkvtoolnix.download/debian/ buster main' >> /etc/apt/sources.list.d/mkvtoolnix.download.list && \
  apt update && apt install -y mkvtoolnix && \
  cat <<EOT >> ~/.bashrc
export PS1="\n\[\e[36m\][\[\e[m\]\[\e[36m\]\t\[\e[m\]\[\e[36m\]]\[\e[m\]\[\e[32m\][\[\e[m\]\[\e[32m\]\u\[\e[m\]\[\e[32m\]@\[\e[m\]\[\e[33m\]\h\[\e[m\]\[\e[33m\]]\[\e[m\]\[\e[35m\][\[\e[m\]\[\e[35m\]\w\[\e[m\]\[\e[35m\]]\[\e[m\] \n\\$: "

myget() {
  nohup wget --user "$PUTIO_USERNAME" --password="$PUTIO_PASSWORD" --content-disposition -c $1 &> /dev/null &
}
EOT

ENV dev /code/
ENV PYTHON_FFMPEG $dev/ffmpeg_wrapper/execute_ffmpeg.py
ENV PYTHON_ENCODING_ENV /.venv/
ENV PYTHON_AUTOENCODE $dev/formatter

