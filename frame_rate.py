import os
import argparse
import subprocess

from avs import source_from_avscript

#################################################################################
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