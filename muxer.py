import os
from execute_ffmpeg import get_metadata
from execute_ffmpeg import start_external_execution

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
    temp_video_delay = get_metadata(temp_filename).get('delay')

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

def mux_episode(params, audio=False, subs=True, attachments=True):
  print(params)
  return str()


def ffmpeg_audio_mux(params, mux_to_filename):
  pass
