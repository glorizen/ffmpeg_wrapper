import os
from external import start_external_execution

##################################################################################################
def redo_audio_ffmpeg(params, filename):

  if not os.path.isfile(filename):
    print('File does not exist: %s' % (filename))
    exit(0)
  
  if not params['all_tracks']['a']:
    print('No audio stream found for [%s]. ' \
      'Exiting ffmpeg audio redone.' % (filename))
    exit(0)

  if params['all_tracks']['a']:
    audio_indices = params['all_tracks']['a']
    basename, extension = os.path.splitext(filename)
    output_name = basename + '_ffredone' + extension

    audio_command = list()
    for audio_number, index in enumerate(audio_indices):
      bitrate = params['audio_channels'][audio_number] * 40000
      audio_command.append('-map 0:{map_index} -c:a libopus ' \
        '-vbr on -compression_level 10 -b:a {bitrate}'.format(
          map_index=index, bitrate=bitrate))
      
    audio_command = ' '.join([x for x in audio_command])

    ffmpeg_command = 'ffmpeg -i {filename} -map 0:v -c:v copy ' \
      '{audio_command} -map 0:s? -c:s copy -map 0:t? {output_name}'.format(
        filename=filename,
        audio_command=audio_command,
        output_name=output_name
      )
      
    start_external_execution(ffmpeg_command)

    if not os.path.isfile(output_name):
      print('Expected output from ffmpeg does not exist: %s' % (output_name))
      exit(0)
    else:
      input_size = os.path.getsize(filename)
      output_size = os.path.getsize(output_name)

      min_size = input_size - (1024 * 1024 * 1)
      max_size = input_size + (1024 * 1024 * 2)

      if min_size < output_size < max_size:
        print('Removing file: %s (%.2f MB)' % (
          filename, input_size / 1024 / 1024))
        os.remove(filename)
      
        print('Renaming: [%s] -> [%s]' % (output_name, filename))
        os.rename(output_name, filename)
        output_name = filename
      else:
        print('Output filesize from ffmpeg is unexpected.\n' \
          'Expected filesze: [%.2f - %.2f]\n' \
          '%s: (%.2f)' % (min_size, max_size,
            output_name, output_size))
        exit(0)

  return output_name
