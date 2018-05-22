import os
from metadata import get_metadata
from external import start_external_execution

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
  audio_files = get_audio_files(params)
  sub_files = get_sub_files(params)
  

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
    for filename in sub_files:
      subtitle_command.append(
        "--sub-charset 0:UTF-8 --default-track 0:yes " \
        "--language 0:eng --track-name '0:Styled Subtitle (.ass)' " \
        "'(' '%s' ')'" % (filename))

    subtitle_command = ' '.join([x for x in subtitle_command])
  else:
    subtitle_command = '\b'

  if oc and chapter_file:
    chapter_command = "--chapter-language eng --chapter-charset UTF-8 " \
      "--chapters '%s'" % (chapter_file)
  else:
    chapter_command = '\b'

  if oc:
    source_command = '-A -D -S --no-chapters %s' % (params['source_file'])
  else:
    source_command = '-A -D -S %s' % (params['source_file'])
  
  if not attachments:
    source_command = source_command.replace('-S', '-S -M')

  output_file = '%s_Output.mkv' % (basename)
  command = "mkvmerge --output '{output}' " \
    "--language 0:jpn --track-name '0:Hi10 Encode' " \
    "--default-track 0:yes '(' '{encoded_video}' ')' " \
    "{subtitle_command} {chapter_command} " \
    "{source_command}".format(
      output=output_file,
      encoded_video=video_file,
      subtitle_command=subtitle_command,
      chapter_command=chapter_command,
      source_command=source_command
    )
  
  print(command)
  return output_file


def ffmpeg_audio_mux(params, mux_to_filename):

  audio_files = get_audio_files(params)
  
  audio_input = list()
  audio_mapping = list()
  for index, filename in enumerate(audio_files):
    a_input = '-i %s' % (filename) 
    a_map = '-map {map_index}:a? -c:a copy ' \
      '-metadata:s:a:{ainput_index} language=jpn ' \
      '-metadata:s:a:{ainput_index} title="My Audio Title"'.format(
        map_index=index + 1, ainput_index=index)

    audio_mapping.append(a_map)
    audio_input.append(a_input)
  
  audio_input = ' '.join([x for x in audio_input])
  audio_mapping = ' '.join([x for x in audio_mapping])

  output_file, ext = os.path.splitext(mux_to_filename)
  output_file = output_file + '_ffmux' + ext

  command = 'ffmpeg -i {video_file} {audio_input} -map 0:v? -c:v copy ' \
    '-map 0:s? -c:s copy -map 0:t? {audio_mapping} {output}'.format(
      video_file=mux_to_filename, audio_input=audio_input,
      audio_mapping=audio_mapping, output=output_file
    )
  
  print(command)
  return output_file
