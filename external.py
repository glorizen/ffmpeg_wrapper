import os
import sys
import time
import subprocess

##################################################################################################
def start_external_execution(external_command):
  temp_name = 'temp_%s' % (str(time.time()).replace('.', ''))
  f = open(temp_name, 'w')

  print('_' * 50 + '\n' + '_' * 50 + '\n')
  print('Starting external job...\n[%s]' % (external_command))
  print('_' * 50 + '\n' + '_' * 50 + '\n')
  process = subprocess.Popen(external_command, shell=True, stdout=subprocess.PIPE)
  
  for c in iter(lambda: process.stdout.read(1), b''):
    try:
      sys.stdout.write(c)
      f.write(c)
    except:
      pass

  try:
    os.remove(temp_name)
  except PermissionError:
    pass
