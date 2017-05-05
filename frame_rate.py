import os
import argparse
import subprocess

#################################################################################
class UndefinedVariableError(Exception):
  pass

class MediaInfoError(Exception):
  pass

class NotAvscriptError(Exception):
  pass

#################################################################################
def get_params():

  parser = argparse.ArgumentParser()
  parser.add_argument('path', type=str, help='path to filename or a folder.')
  params = parser.parse_args().__dict__

  return params

#################################################################################
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
        raise UndefinedVariable('Undefined variable: "%s"\n  File "%s", line %d, in text\n  %s' \
          '' % (varname, filename, line_no, line))

      # if the value (OF VARIABLE) used in video decoder parameter doesn't have its extension,
      # then it's included in source + ".mkv" format. read the part after + in the targeted line.
      if not source_filename.endswith(('.mkv', '.mp4', '.ts')):
        extension = avs_input.split('+')[1].replace('"', '').strip(' ')
        source_filename += extension

  return source_filename

#################################################################################
def get_frame_rate(filename):
  
  # mediainfo command.
  info_command = r'mediainfo --Inform="Video;%FrameRate%"' 
  info_command = '%s %s' % (info_command, filename)

  # put it in a subprocess and try to read the result.
  # raise error if result is unexpected.
  result = subprocess.Popen(info_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
  try:
    result = float(result.replace('\r', '').strip('\n'))
  except:
    raise MediaInfoError('Failed to find frame rate from source file.\n'
      '  [Source: %s][Query: %s]' % (filename, info_command))
  
  return result

#################################################################################
def add_frame_rate(filename, frame_rate):

  # prepare write statement and write it to avscript.
  to_write = '##>frame_rate=%.3f' % (frame_rate)
  
  f = open(filename, 'a')
  f.write('\n%s\n' % (to_write))
  f.close()

  print('FrameRate added to avscript: [Avscript: %s][FrameRate: %s]' % (filename, frame_rate), end='')
  
#################################################################################
def handle_avscript(scriptname):

  # if not .avs extension then raise error.
  if not scriptname.endswith('.avs'):
    raise NotAvscriptError('Expected an avscript file: %s' % (scriptname))

  # parse avscript to get source.
  # raise error if parsed source does not exist.
  source = source_from_avscript(scriptname)
  if not os.path.exists(os.path.join(os.path.dirname(scriptname), source)):
    raise FileNotFoundError('Source detected from script does not exist.\n' \
      '  [Source: %s][Avscript: %s]' % (source, scriptname))
  
  # get frame rate (using mediainfo) of the source.
  # finally write the frame rate to avscript (in commented form).
  frame_rate = get_frame_rate(source)
  add_frame_rate(scriptname, frame_rate)
  print('[Source: %s]' % (source))

#################################################################################
def main():
  params = get_params()

  # if user specified a folder path...
  # get all .avs files from the path, display them and proceed to handle them.
  if os.path.isdir(os.path.abspath(params['path'])):
    avscripts = [x for x in os.listdir(params['path']) if x.endswith(('.avs'))]
    
    for num, temp in enumerate(avscripts):
      print('[%02d] %s' % (num + 1, temp))

    choice = input('Do you wish to continue [y|n]: ')
    if choice.lower() != 'y':
      print('User exited the program.'); exit(0)
    else:
      print('#' * 50)

    for scriptname in avscripts:
      handle_avscript(scriptname)

  # if user specified a file path...
  # put that filepath to avs handler.
  else:
    scriptname = params['path']
    handle_avscript(scriptname)
    
#################################################################################
if __name__ == '__main__':
  main()