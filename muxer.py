import os
from metadata import (
  get_metadata, get_lang_and_title,
  get_codec_name)
from external import start_external_execution

ATTACHMENT_SIZE_RANGE = 15

def get_font_details(font_file):

  if not(font_file.lower().endswith('ttf') or \
    font_file.lower().endswith('otf')):
    print('Font format is not supported: %s' % (font_file))
    return
  
  MIME = str()
  if font_file.lower().endswith('ttf'):
    MIME = 'application/x-truetype-font'
  elif font_file.lower().endswith('otf'):
    MIME = 'application/vnd.ms-opentype'
  
  details = {
    'name': os.path.basename(font_file),
    'MIME': MIME,
    'file': font_file
  }

  return details

def get_fonts(attach_path):
    
  if not os.path.exists(attach_path):
    print('Could not find attachment file / folder: %s' % (attach_path))
    return
  
  fonts = list()

  if os.path.isfile(attach_path):
    font_file = attach_path
    details = get_font_details(font_file)
    fonts.append(details)

  elif os.path.isdir(attach_path):
    for font_file in os.listdir(attach_path):
      details = get_font_details(os.path.join(attach_path, font_file))
      fonts.append(details)

  font_strings = list()
  for font_item in fonts:
    font_strings.append(
      '--attachment-name \'{name}\' ' \
      '--attachment-mime-type {MIME} ' \
      '--attach-file \'{file}\''.format(**font_item)
    )
  
  return font_strings

def attach_fonts(target_file, attach_path):

  if not os.path.isfile(target_file):
    print('Target file could not be detected: %s' % (target_file))
    return

  filename, ext = os.path.splitext(target_file)
  output_name = filename + '_attached' + ext
  fonts = get_fonts(attach_path)

  mmg_command = 'mkvmerge --output {output_name} -M ' \
    "'(' '{input_name}' ')' {fonts}".format(
      output_name=output_name, input_name=target_file,
      fonts=' '.join(fonts))
  
  return mmg_command

def merge_video(params, temp_filenames, output_filename):
  mmg_command = 'mkvmerge -o %s ' % (output_filename)
  for index, temp_filename in enumerate(temp_filenames):
    temp_video_delay = get_metadata(
      params, temp_filename).get('delay')

    if index > 0:
      mmg_command += '--sync 0:%s + %s ' % (temp_video_delay,
        temp_filename)
    else:
      mmg_command += '%s ' % (temp_filename)

  if params.get('prompt'):
    print(mmg_command)
  else:
    start_external_execution(mmg_command)

    if os.path.isfile(output_filename):
      for filename in temp_filenames:
        print('Deleting: %s' % (os.path.abspath(filename)))
        os.remove(filename)

def get_audio_files(params):

  basename = os.path.splitext(params['in'])[0]

  audio_tracks = params['all_tracks']['a']
  if params['fake_tracks'].get('a'):
    audio_tracks.extend(params['fake_tracks']['a'])

  audio_files = ['%s_Audio_%d.opus' % (basename, audio_id)
    for audio_id in audio_tracks]
  
  return audio_files

def get_sub_files(params):

  basename = os.path.splitext(params['in'])[0]

  sub_tracks = params['all_tracks']['s']
  if params['fake_tracks'].get('s'):
    sub_tracks.extend(params['fake_tracks']['s'])

  sub_files = ['%s_Subtitle_final_%d.ass' % (basename, sub_id)
    for sub_id in sub_tracks]
  
  return sub_files

def mux_episode(params, audio=False, subs=True, attachments=True):

  basename = os.path.splitext(params['in'])[0]
  video_file = '%s_Encoded.mkv' % (basename)

  if not os.path.isfile(video_file):
    print('Encoded video file does not exist: %s' % (video_file))
    exit(0)
  
  expected_size = os.path.getsize(video_file)

  sub_files = get_sub_files(params)
  video_codec = get_codec_name(params, video_file)
  video_codec = video_codec.upper()
  video_codec = video_codec.replace('H264', 'H.264')

  get_lang_and_title(params, params['source_file'])

  oc = False
  if params.get('cuts'):
    timestamps = params['cuts']['original']['timestamps']

    for i in range(len(timestamps) - 1):
      current = timestamps[i]
      ahead = timestamps[i + 1]

      if ahead[0] - current[1] > 20:
        oc = True
        break

  if oc:
    chapter_file = '%s_chapter.xml' % (basename)
    if not os.path.isfile(chapter_file):
      print('Looks like muxing needs an external chapter file: %s' % (
        chapter_file))
      exit(0)

  if subs:
    subtitle_command = list()
    is_default = True
    has_defaulted = False
    for sub_number, filename in enumerate(sub_files):

      if not os.path.isfile(filename):
        continue

      try:
        sub_lang = params['languages']['s'][sub_number]
      except:
        sub_lang = 'eng'

      try:
        sub_name = params['titles']['s'][sub_number]
      except:
        sub_name = 'Styled Subtitle (.ass)'
      
      if not has_defaulted and sub_lang in ['eng', 'enm']:
        is_default = True
        has_defaulted = True
      else:
        is_default = False

      subtitle_command.append(
        "--sub-charset 0:UTF-8 --default-track 0:{is_default} " \
        "--language 0:{subtitle_language} --track-name '0:{subtitle_name}' " \
        "'(' '{filename}' ')'".format(
          is_default='yes' if is_default else 'no',
          subtitle_language=sub_lang, subtitle_name=sub_name,
          filename=filename))
      
      expected_size += os.path.getsize(filename)

    subtitle_command = ' '.join([x for x in subtitle_command])
  else:
    subtitle_command = '\b'

  if oc and chapter_file:
    chapter_command = "--chapter-language eng --chapter-charset UTF-8 " \
      "--chapters '%s'" % (chapter_file)

    expected_size += os.path.getsize(chapter_file)
  else:
    chapter_command = '\b'

  if oc:
    source_command = '-A -D -S --no-chapters %s' % (params['source_file'])
  else:
    source_command = '-A -D -S %s' % (params['source_file'])
  
  min_size = expected_size - (1024 * 1024 * 0.25)
  max_size = expected_size + (1024 * 1024 * ATTACHMENT_SIZE_RANGE)

  if not attachments:
    source_command = source_command.replace('-S', '-S -M')
    min_size -= 1024 * 1024 * ATTACHMENT_SIZE_RANGE
    min_size = 0 if min_size < 0 else min_size

  output_file = '%s_Output.mkv' % (basename)
  command = "mkvmerge --output '{output}' " \
    "--language 0:jpn --track-name '0:{video_name}' " \
    "--default-track 0:yes '(' '{encoded_video}' ')' " \
    "{subtitle_command} {chapter_command} " \
    "{source_command}".format(
      output=output_file,
      video_name='Hi10 Encode (%s)' % (video_codec),
      encoded_video=video_file,
      subtitle_command=subtitle_command,
      chapter_command=chapter_command,
      source_command=source_command
    )
  
  start_external_execution(command)

  if os.path.isfile(output_file):
    real_size = os.path.getsize(output_file)

    print('min: %.2f MB' % (min_size / 1024 / 1024))
    print('max: %.2f MB' % (max_size / 1024 / 1024))
    print('real: %.2f MB' % (real_size / 1024 / 1024))
    input('haro')

    if min_size < real_size < max_size:
      pass
    else:
      print('Output filesize from mkvmerge is not within expectations.\n' \
        'Expectations: [%.2f MB - %.2f MB]\n' \
        '%s: (%.2f MB)\n' % (min_size / 1024 / 1024,
          max_size / 1024 / 1024, output_file,
          real_size / 1024 / 1024))
      exit(0)
  else:
    print('Expected output file from mkvmerge does not ' \
      'exist: %s\n' % (output_file))
    exit(0)

  return output_file

def ffmpeg_audio_mux(params, mux_to_filename):

  expected_size = os.path.getsize(mux_to_filename)
  audio_files = get_audio_files(params)
  
  audio_input = list()
  audio_mapping = list()
  is_default = True
  has_defaulted = False
  for index, filename in enumerate(audio_files):

    if not os.path.isfile(filename):
      continue

    try:
      audio_channels = params['audio_channels'][index]
      audio_channels = '(%d channeled)' % (audio_channels)
    except:
      audio_channels = '\b'

    if filename.endswith(('.opus', '.ogg')):
      audio_name = 'OPUS Audio'
    elif filename.endswith('.eac3'):
      audio_name = 'EAC3 Audio'
    elif filename.endswith('.aac'):
      audio_name = 'AAC Audio'
    elif filename.endswith('.flac'):
      audio_name = 'FLAC Audio'
    
    audio_name = '%s %s' % (audio_name, audio_channels)
    
    try:
      audio_lang = params['languages']['a'][index]
    except:
      audio_lang = 'jpn'
    
    if not has_defaulted and audio_lang in ['jpn', 'ja']:
      is_default = True
      has_defaulted = True
    else:
      is_default = False

    a_input = '-i %s' % (filename) 
    a_map = '-map {map_index}:a? -c:a copy ' \
      '-metadata:s:a:{ainput_index} language={audio_lang} ' \
      '-metadata:s:a:{ainput_index} title="{audio_name}" ' \
      '-disposition:a:{ainput_index} {is_default}'.format(
        map_index=index + 1, ainput_index=index,
        audio_lang=audio_lang, audio_name=audio_name,
        is_default='default' if is_default else 'none')

    audio_mapping.append(a_map)
    audio_input.append(a_input)
    expected_size += os.path.getsize(filename)
  
  audio_input = ' '.join([x for x in audio_input])
  audio_mapping = ' '.join([x for x in audio_mapping])

  output_file, ext = os.path.splitext(mux_to_filename)
  output_file = output_file + '_ffmux' + ext

  if not audio_input:
    print('No audio input was used. Exiting ffmpeg muxing module.')
    return

  command = 'ffmpeg -i {video_file} {audio_input} -map 0:v? -c:v copy ' \
    '{audio_mapping} -map 0:s? -c:s copy -map 0:t? {output}'.format(
      video_file=mux_to_filename, audio_input=audio_input,
      audio_mapping=audio_mapping, output=output_file
    )
  
  start_external_execution(command)

  real_size = os.path.getsize(output_file)
  min_size = expected_size - (1024 * 1024 * 0.25)
  max_size = expected_size + (1024 * 1024 * 1)

  if os.path.isfile(output_file):
    if  min_size < real_size < max_size:

      print('Removing file: %s (%.2f MB)' % (
        mux_to_filename,
        os.path.getsize(mux_to_filename) / 1024 / 1024))
      
      os.remove(mux_to_filename)
      
      print('Renaming: [%s] -> [%s]' % (output_file, mux_to_filename))
      print('Final Output: %s (%.2f MB)\n' % (mux_to_filename,
        real_size / 1024 / 1024))
      os.rename(output_file, mux_to_filename)
    else:
      print('Output filesize from ffmpeg is not within ' \
        'expectations.\nExpected Range: [%.2f MB - %.2f MB]\n' \
        '%s: (%.2f MB)\n' % (
          min_size / 1024 / 1024, max_size / 1024 / 1024,
          output_file, real_size / 1024 / 1024))
      exit(0)
  else:
    print('Expected output file from ffmpeg does not ' \
      'exist: %s' % (output_file))
    exit(0)

  return {
    'output': output_file,
    'size': expected_size
  }
