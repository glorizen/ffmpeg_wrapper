import os

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

    mmg_command = 'mkvmerge.exe --output {output_name} -M ' \
      "'(' '{input_name}' ')' {fonts}".format(
        output_name=output_name, input_name=target_file,
        fonts=' '.join(fonts))
    
    return mmg_command
