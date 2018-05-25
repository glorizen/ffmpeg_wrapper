import os
import sys
import time
import subprocess

##################################################################################################
def start_external_execution(external_command, catchphrase=None):

  while '  ' in external_command:
    external_command = external_command.replace('  ', ' ')

  temp_name = 'temp_%s' % (str(time.time()).replace('.', ''))
  dumpfile_name = 'dump_%s' % (str(time.time()).replace('.', ''))

  if catchphrase:
    external_command = external_command + ' &> %s' % (dumpfile_name)

  with open(temp_name, 'w') as f:
    print('_' * 50 + '\n' + '_' * 50 + '\n')
    print('Starting external job...\n[%s]' % (external_command))
    print('_' * 50 + '\n' + '_' * 50 + '\n')
    process = subprocess.Popen(external_command, shell=True, stdout=subprocess.PIPE)
    
    if catchphrase:
      print('Dumping data [%s] to catch errors, if any.' % (dumpfile_name))

    for line in iter(process.stdout.readline, b''):
      line = line.decode('utf8')

      try:
        sys.stdout.write(line)
        f.write(line)
      except:
        pass

  print('_' * 50 + '\n' + '_' * 50 + '\n')

  try:
    os.remove(temp_name)
  except PermissionError:
    pass
  
  process.wait()
  if catchphrase:
    tee_content = open(dumpfile_name, 'r').readlines()

    try:
      os.remove(dumpfile_name)
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
