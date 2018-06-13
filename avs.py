import os

class UndefinedVariableError(Exception):
  pass

##################################################################################################
def source_from_avscript(filename):

  # raise exception if avscript file doesn't exist.
  if not os.path.isfile(filename):
    raise FileNotFoundError('File does not exist: %s' % (os.path.abspath(filename)))

  # get all lines from avscript. strip new lines and carriage returns.
  lines = [x.strip('\r').strip('\n').lower() for x in open(filename, 'r').readlines()]
  defined = dict()

  # iterate through each fetched line (enumerate to track line num being read)
  for line_no, line in enumerate(lines):
    
    # split line on '=' basis and if splitted items are 2, it means, most likely, that 
    # a variable was defined in that line. put that variable and its value in a dict.
    tokens = [temp.strip(' ') for temp in line.split('=')]
    if len(tokens) == 2:
      defined[tokens[0]] = tokens[1]

    # if a line contains video decoder (FFVideoSource, DirectShowSource etc.) then proceed.
    # ignore line having 'ffaudio' because it will probably have same source as video.
    # proceed with video decoder line and get the part inside FFVideoSource(==>something + ".mkv"<==)
    if 'source(' in line and 'ffaudio' not in line:
      avs_input = line.split('source(')[1].split(',')[0].strip(')')
      
      # if a variable is used, then try to guess if extension was included or not.
      # + sign and " shows that an extension was added like: source + ".mp4"
      #   read the part before +
      # otherwise, assume variable was used without extension (variable had extension in itself)
      if '+' in avs_input and '"' in avs_input and not avs_input.startswith('"'):
        varname = avs_input.split('+')[0].strip(' ')
      else:
        varname = avs_input
      
      # if variable used was defined previously in avscript, then
      #   use the value of variable and remove " from the value. (value is most likely source filename)
      if varname in defined:
        source_filename = defined[varname].replace('"', '')
      # if variable started / ended with ", it is not a variable. 
      # But probably source file in string form. hence, remove " from string to get source filename.
      elif varname.startswith('"') and varname.endswith('"'):
        source_filename = varname.lstrip('"').rstrip('"')
      # otherwise, unknown variable is used in video decoder parameter.
      else:
        raise UndefinedVariableError(
          'Undefined variable: "%s"\n  File "%s", line %d, in text\n  %s' \
          '' % (varname, filename, line_no, line))

      # if the value (OF VARIABLE) used in video decoder parameter doesn't have its extension,
      # then it's included in source + ".mkv" format. read the part after + in the targeted line.
      if not source_filename.endswith(('.mkv', '.mp4', '.ts')):
        extension = avs_input.split('+')[1].replace('"', '').strip(' ')
        source_filename += extension

  return source_filename

##################################################################################################
def parse_avs_chapters(avs_content):
  
  avs_chap_string = ''.join([x.strip('##!!') for x in avs_content 
    if x.startswith('##!!') and '>' in x and '<' in x])

  if not avs_chap_string:
    return None

  filtered_chaps = [x.strip('>').strip('<').strip(' ').strip('\n') 
    for x in avs_chap_string.split(',')] if avs_chap_string else None

  avs_chapters = dict()
  avs_chapters['names'] = list(); avs_chapters['frames'] = list()

  for chapter in filtered_chaps:
    name = chapter.split('[')[0]
    start = int(chapter.split('[')[1].split(':')[0].strip(' '))
    end = int(chapter.split('[')[1].split(':')[1].split(']')[0].strip(' '))
    avs_chapters['names'].append(name)
    avs_chapters['frames'].append((start, end))

  return avs_chapters

##################################################################################################
def get_custom_commands(input_file):

  commands_dict = dict()
  avsfile = open(input_file)
  file_content = avsfile.readlines()
  avsfile.close()

  commands = ','.join([x.strip('##>') for x in file_content if x.startswith('##>')]).split(',')
  
  for command in commands:
    if not command or len(command) < 3:
      continue
  
    option, value = command.split('=')
    commands_dict[option] = value.strip('\r').strip('\n')

  avs_chapters = parse_avs_chapters(file_content)
  
  if avs_chapters:
    commands_dict['avs_chapters'] = avs_chapters

  return commands_dict

##################################################################################################
def get_trim_times(params, input_file, frame_rate):

  trims_list = list()
  times_list = list()

  curr_dir = os.path.abspath(os.path.curdir)
  os.chdir(params['input_dir'])
  
  trims = ''.join([x for x in open(os.path.basename(input_file)).readlines() 
    if not x.startswith('#') and 'trim(' in x.lower()]).replace(
        ' ', '').replace('\n', '').split('++')
  
  os.chdir(curr_dir)

  for tm in trims:
    if not tm:
      continue

    start_frame = int(tm.split(',')[0].lower().replace('trim(', ''))
    start_time = float('%.3f' % (start_frame / frame_rate))

    end_frame = int(tm.split(',')[1].lower().replace(')', ''))
    end_time = float('%.3f' % (end_frame / frame_rate))

    trims_list.append((start_frame, end_frame))
    times_list.append((start_time, end_time))

  print('Trimmed Frames:', trims_list)
  print('Trimmed timestamps:', times_list)

  if not params.get('cuts'):
    params['cuts'] = {'original': {}}
  
  params['cuts']['original']['frames'] = trims_list
  params['cuts']['original']['timestamps'] = times_list
  return times_list
