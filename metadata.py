import os
import subprocess

def get_ffprobe_metadata(params, filename):
  
  metadata = dict()

  curr_dir = os.path.abspath(os.path.curdir)
  os.chdir(params['input_dir'])

  if filename.endswith('.xml'):
    media_json = dict()
    xmlfile = open(filename, 'r')
    xml_lines = xmlfile.readlines()
    xmlfile.close()

    options = [
      {'name': 'video', 'token': 'v', 'status': False},
      {'name': 'audio', 'token': 'a', 'status': False},
      {'name': 'text', 'token': 's', 'status': False}
    ]

    for line in xml_lines:
      line = line.strip().strip('\n')
      if 'track type=' in line:
      
        for category in options:
          if category['name'] in line.lower():
            token = category['token']
            category['status'] = True

            if media_json.get(token):
              media_json[token].append({})
            else:
              media_json[token] = list()
              media_json[token].append({})

        
      if '/track' in line:
        for category in options:
          if category['status'] == True:
            category['status'] = False
        
      if '</' not in line and '>' not in line:
        continue
      
      try:
        key = line.split('</')[1].strip('>')
        value = line.split('</')[0].split('>')[1]
      except:
        key = str()
        value = str()

      if value:
        try:
          value = int(value)
        except ValueError:
          try:
            value = float(value)
          except ValueError:
            pass

      if key and value:
        for category in options:
          if category['status']:
            token = category['token']
            media_json[token][-1][key] = value

    tracks = dict()
    codecs = dict()
    channels = list()
    dimensions = list()

    for category in media_json:
      tracks[category] = list()
      codecs[category] = list()

      for item in media_json[category]:
        if category == 'v':
          dimensions.append(item.get('Width'))
          dimensions.append(item.get('Height'))

        for key, value in item.items():
          if key == 'ID':
            tracks[category].append(value - 1)
          
          if key == 'Format':
            codecs[category].append(value.lower())
          
          if key == 'Channels':
            channels.append(value)

    metadata = {
      'tracks': tracks,
      'codecs': codecs,
      'audio_channels': channels,
      'dim': dimensions
    }

    return metadata

  tracks = dict()
  for stream_type in ['v', 'a', 's']:
    probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams %s -show_entries ' \
      'stream=index %s' % (stream_type, os.path.basename(filename))
    result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
    tracks[stream_type] = [int(x.replace('\r', '').split('=')[1]) for x in result.split('\n') if x]

  codecs = dict()
  for stream_type in ['v', 'a', 's']:
    probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams %s -show_entries ' \
      'stream=codec_name %s' % (stream_type, os.path.basename(filename))
    result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
    codecs[stream_type] = [x.replace('\r', '').split('=')[1].strip('"')
      for x in result.split('\n') if x]

  metadata['tracks'] = tracks
  metadata['codecs'] = codecs

  probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams v -show_entries ' \
    'stream=width,height %s' % (os.path.basename(filename))

  result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
  metadata['dim'] = [int(x.replace('\r', '').split('=')[1]) for x in result.split('\n') if x]

  probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams a -show_entries ' \
    'stream=channels %s' % (os.path.basename(filename))

  result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
  metadata['audio_channels'] = [int(x.replace('\r', '').split('=')[1]) for x in result.split('\n') if x]

  os.chdir(curr_dir)
  return metadata

def get_duration(filename):
  
  if not os.path.isfile(filename):
    print('File does not exist: %s' % (filename))
    return None
  
  info_command = r'mediainfo --Inform="Video;%Duration%"' 
  info_command = '%s %s' % (info_command, filename)

  result = subprocess.Popen(info_command, shell=True,
    stdout=subprocess.PIPE).stdout.read() \
    .decode('utf-8')
  
  return int(result.split('.')[0])

def get_codec_name(params, filename):

  if not os.path.isfile(filename):
    print('File does not exist: %s' % (filename))
    return None
  
  for stream_type in ['v']:

    probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams %s ' \
      '-show_entries stream=codec_name %s' % (
        stream_type, os.path.basename(filename))

    result = subprocess.Popen(probe_command, shell=True,
      stdout=subprocess.PIPE).stdout.read().decode('utf-8')
    result = [x.replace('\r', str()) for x in result.split('\n') if x]

    for item in result:
      if 'codec_name=' in item:
        codec_name = item.split('codec_name=')[1].strip() \
          .replace('"', str())
        return codec_name

def get_lang_and_title(params, filename):

  if not os.path.isfile(filename):
    print('File does not exist: %s' % (filename))
    return None
  
  params['languages'] = dict()
  params['titles'] = dict()
  for stream_type in ['v', 'a', 's']:
    params['languages'][stream_type] = list()
    params['titles'][stream_type] = list()

    probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams %s -show_entries ' \
      'stream_tags=title -show_entries stream_tags=language %s' % (
        stream_type, filename)

    result = subprocess.Popen(probe_command, shell=True,
      stdout=subprocess.PIPE).stdout.read().decode('utf-8')
    result = [x.replace('\r', str()) for x in result.split('\n') if x]

    for item in result:
      if 'title=' in item:
        title = item.split('title=')[1].strip().replace('"', str())
        params['titles'][stream_type].append(title)
      
      if 'language=' in item:
        lang = item.split('language=')[1].strip().replace('"', str())
        params['languages'][stream_type].append(lang)

def get_metadata(params, filename):

  if not os.path.isfile(filename):
    print('File does not exist: %s' % (filename))
    exit(0)

  info_command = r'mediainfo --Inform="General;%Duration/String3%\n%UniqueID%"' 
  info_command = '%s %s' % (info_command, filename)

  result = subprocess.Popen(info_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')

  video_info_command = r'mediainfo --Inform="Video;%Duration/String3%\n%Delay%"' 
  video_info_command = '%s %s' % (video_info_command, filename)

  video_result = subprocess.Popen(video_info_command, shell=True,
    stdout=subprocess.PIPE).stdout.read().decode(
    'utf-8').replace('\r', '').strip()

  metadata = dict()
  suid = None

  if len(result.split('\n')) >=2:
    filtered_result = [x.replace('\r', '') for x in result.split('\n') if len(x) >= 1]
    if len(filtered_result) >= 2:
      metadata['duration'], suid = [x.replace('\r', '') for x in result.split('\n') if len(x) >= 1]
    else:
      metadata['duration'] = [x.replace('\r', '') for x in result.split('\n') if len(x) >= 1]

  if suid:
    metadata['suid'] = "{0:X}".format(int(suid))

    while len(metadata['suid']) < 32:
      metadata['suid'] = '0%s' % (metadata['suid'])

  metadata['name'] = filename
  metadata['duration'] = video_result.split('\n')[0]

  if len(video_result.split('\n')) > 1:
    metadata['delay'] = video_result.split('\n')[1]
                                                                                  
  return metadata
#  metadata = dict()
#  metadata['duration'], suid = [x.replace('\r', '') for x in result.split('\n') if len(x) > 0]
#  metadata['suid'] = "{0:X}".format(int(suid))

#  while len(metadata['suid']) < 32:
#    metadata['suid'] = '0%s' % (metadata['suid'])

#  metadata['name'] = filename

#  metadata['duration'] = video_result.split('\n')[0]
#  metadata['delay'] = video_result.split('\n')[1]
  
#  return metadata
