import os
import sys
import time
import subprocess

##################################################################################################
def start_external_execution(external_command):

  temp_name = 'temp_%s' % (str(time.time()).replace('.', ''))

  with open(temp_name, 'w') as f:
    print('_' * 50 + '\n' + '_' * 50 + '\n')
    print('Starting external job...\n[%s]' % (external_command))
    print('_' * 50 + '\n' + '_' * 50 + '\n')
    process = subprocess.Popen(external_command, shell=True, stdout=subprocess.PIPE)
    
    for line in iter(process.stdout.readline, b''):
      try:
        sys.stdout.write(line.decode('utf8'))
        f.write(line.decode('utf8'))
      except:
        pass
  
  print('_' * 50 + '\n' + '_' * 50 + '\n')

  try:
    os.remove(temp_name)
  except PermissionError:
    pass
