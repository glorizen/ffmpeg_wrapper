import os
import sys
import time
import subprocess

##################################################################################################
def start_external_execution(external_command, catchphrase=None):

  while '  ' in external_command:
    external_command = external_command.replace('  ', ' ')

  temp_name = 'temp_%s' % (str(time.time()).replace('.', ''))

  if catchphrase:
    tempfile = open(temp_name, 'a')
  else:
    tempfile = open(temp_name, 'w')
     
  print('_' * 50 + '\n' + '_' * 50 + '\n')
  print('Starting external job...\n[%s]' % (external_command))
  print('_' * 50 + '\n' + '_' * 50 + '\n')
  
  if catchphrase:
    process = subprocess.Popen(external_command, shell=True,
      stdout=tempfile, stderr=tempfile)
    print('Dumping data [%s] to catch errors, if any.' % (temp_name))
    process.wait()

  else:
    process = subprocess.Popen(external_command, shell=True,
      stdout=subprocess.PIPE)

    for line in iter(process.stdout.readline, b''):
      line = line.decode('utf8')

      try:
        sys.stdout.write(line)
        tempfile.write(line)
      except:
        pass

    try:
      os.remove(temp_name)
    except PermissionError:
      pass

  print('_' * 50 + '\n' + '_' * 50 + '\n')

  if catchphrase:
    tee_content = open(temp_name, 'r').readlines()
    try:
      os.remove(temp_name)
    except PermissionError:
      pass

    for line in tee_content:
      flags = list()
      for word in catchphrase:
        if word in line:
          flags.append(True)
        else:
          flags.append(False)
      
      if False not in flags:
        return True
