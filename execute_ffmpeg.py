import os
import sys
import time
import argparse
import subprocess
from datetime import timedelta

import pysubs
from frame_rate import source_from_avscript

CH_TEMPLATE_STRING = \
'''<?xml version="1.0"?>
<!-- <!DOCTYPE Chapters SYSTEM "matroskachapters.dtd"> -->
<Chapters>
  <EditionEntry>
    <EditionFlagDefault>${edition['default']}</EditionFlagDefault>
    <EditionFlagOrdered>${edition['oc']}</EditionFlagOrdered>
    <EditionUID>12345600</EditionUID>
    <EditionFlagHidden>0</EditionFlagHidden>
    <ChapterAtom tal:repeat="atom atoms">
      <ChapterUID>${atom['uid']}</ChapterUID>
      <ChapterTimeStart>${atom['start']}</ChapterTimeStart>
      <ChapterTimeEnd>${atom['end']}</ChapterTimeEnd>
      <ChapterSegmentUID format="hex" tal:condition="'suid' in atom">${atom['suid']}</ChapterSegmentUID>
      <ChapterFlagHidden>${atom['hidden']}</ChapterFlagHidden>
      <ChapterFlagEnabled>${atom['enabled']}</ChapterFlagEnabled>
      <ChapterDisplay>
        <ChapterString>${atom['ch-string']}</ChapterString>
        <ChapterCountry>us</ChapterCountry>
        <ChapterLanguage>eng</ChapterLanguage>
      </ChapterDisplay>
    </ChapterAtom>
  </EditionEntry>
</Chapters>'''
##################################################################################################
class FolderNotFoundError(Exception):
  pass

##################################################################################################
def process_params(params):

  if params.get('rs') and len(params['rs'].split(':')) == 2:
    params['rs'] = params['rs'].split(':')
    params['rs'] = [x.replace('0', '-1') if len(x) == 1 else x for x in params['rs']]
  
  params['input_dir'] = os.path.dirname(os.path.abspath(params['in']))
  params['orig_dir'] = os.path.abspath(os.path.curdir)

  if params['dest']:
    dest_path = os.path.abspath(params['dest'])
    if not os.path.exists(dest_path):
      raise FolderNotFoundError('Destination Folder doesn\'t exist: %s' % (dest_path))
    
    if not os.path.isfile(params['in']):
      raise FileNotFoundError('Given input file does not exist: %s' % (params['in']))

  return params
    
##################################################################################################
def get_params():
  
  parser = argparse.ArgumentParser()
  parser.add_argument('in', type=str, help='input .avs filename to parse.')
  parser.add_argument('-crf', type=float, help='crf value to use in video encoder.')
  parser.add_argument('-aqm', type=int, help='aq-mode to use in video encoder.')
  parser.add_argument('-aqs', type=float, help='aq-strength to use in video encoder.')
  
  parser.add_argument('-node', default=-1, type=int, 
    help='computing node that will be sshed into and then used for encoding.')
  parser.add_argument('-nohup', type=str, default=str(), help='filename which will contain stdout, stderr. ' \
    'Also puts the job to background using nohup.')

  parser.add_argument('-rs', type=str, help='this option will resize output video. ' \
    'e.g. 1280:720 will give you 720p video. 1280:-1 will give you width of 1280 and height with ' \
    'respective aspect ratio. Same will apply for given height like -1:720')
  
  parser.add_argument('-dest', type=str, help='this option will create output file to given destination ' \
    'folder name. Files will be created there to begin with rather than moving them to the folder ' \
    'after completion.')

  parser.add_argument('-trim', type=int, help='this option will process given trimmed section only ' \
    'while ignoring rest of the video.')

  parser.add_argument('-subtrim', action='store_true', help='this option will trim subtitles using pysubs.')

  parser.add_argument('-track', type=int, help='this option will process given track id stream only ' \
    'while ignoring rest of the streams.')

  parser.add_argument('-fr', type=float, help='this option will assume the frame rate for the source file.')
  parser.add_argument('-hevc', action='store_true', help='this option enables HEVC encoding rather than x264.')
  parser.add_argument('-aac', action='store_true', help='this option enables AAC audio encoding rather than OPUS.')
  
  parser.add_argument('-prompt', action='store_true', 
    help='this option will prompt user to confirm before writing to disk.')
  parser.add_argument('-x', action='store_true', 
    help='this option will execute the bash script, if created any, at the end.')

  parser.add_argument('-nthread', action='store_true', help='this option will enable multithreading of ffmpegs.')
  parser.add_argument('-vn', action='store_true', help='this option will disable video encoding.')
  parser.add_argument('-an', action='store_true', help='this option will disable audio encoding.')
  parser.add_argument('-sn', action='store_true', help='this option will disable subtitle encoding.')
  parser.add_argument('-tn', action='store_true', help='this option will disable attachments.')
  parser.add_argument('-cc', action='store_true', help='this option will create chapter file from trims.')
  parser.add_argument('-mx', type=str, help='this option muxes streams at the end by mkvmerge.')
  parser.add_argument('-hi', action='store_true', help='this option will use ffmpeg-hi that has non-free libs.')
  parser.add_argument('-map_ch', action='store_true', help='this option will attach default chapter file.')

  parser.add_argument('-op', type=str, help='specify opening file for .mkv OC.')
  parser.add_argument('-ed', type=str, help='specify ending file for .mkv OC.')

  params = parser.parse_args().__dict__
  params = process_params(params)

  return params

##################################################################################################
def get_source(input_file):

  basename = os.path.basename(input_file)
  input_source = [x for x in os.listdir(params['input_dir']) 
    if basename[:-4] == x[:-4] and x.endswith(('.mkv', '.mp4', '.avi', '.ts'))]

  input_source = ''.join(input_source) if len(input_source) == 1 else \
    ''.join([x for x in input_source if x.endswith('.mkv')])

  if not input_source:
    input_source = source_from_avscript(input_file)
    if not input_source:
      raise FileNotFoundError('Could not detect input source from avscript file: %s' % input_file)

  return os.path.join(os.path.dirname(params['in']), input_source)

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
def get_trim_times(input_file, frame_rate):

  trims_list = list()
  times_list = list()

  curr_dir = os.path.abspath(os.path.curdir)
  os.chdir(params['input_dir'])
  
  trims = ''.join([x for x in open(os.path.basename(input_file)).readlines() 
    if not x.startswith('#') and 'trim(' in x.lower()]).replace(' ', '').replace('\n', '').split('++')
  
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
  return times_list

##################################################################################################
def get_frame_rate(filename):
  
  if not os.path.isfile(filename):
    raise FileNotFoundError('File does not exist: %s' % (filename))

  probe_command = r'ffprobe -v error -select_streams v -show_entries ' \
  'stream=r_frame_rate:stream_tags=DURATION,NUMBER_OF_FRAMES ' \
  '-of default=noprint_wrappers=1 %s' % (os.path.basename(filename))

  # info_command = r'mediainfo --Inform="Video;%FrameRate%"' 
  # info_command = '%s %s' % (info_command, filename)

  curr_dir = os.path.abspath(os.path.curdir)
  os.chdir(params['input_dir'])

  result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
  result = result.replace('\r', '').strip('\n')
  os.chdir(curr_dir)
  
  filtered = dict()

  for expression in result.strip('\n').split('\n'):
    key = expression.split('=')[0].lower()
    value = expression.split('=')[1]

    if 'r_frame_rate' in key:
      numerator = int(value.split('/')[0])
      denominator = int(value.split('/')[1])
      value = round(numerator / denominator, 3)

    if 'tag:number_of_frames' in key:
      value = int(value)

    if 'tag:duration' in key:
      seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(value.split('.')[0].split(":"))))
      new_time = (seconds + float('0.' + value.split('.')[1])) if len(value.split('.')) > 1 else seconds
      value = new_time

    filtered[key] = value

  if 'tag:number_of_frames' in filtered.keys() and 'tag:duration' in filtered.keys():
    temp = str(filtered['tag:number_of_frames'] / filtered['tag:duration'])
    return float(temp[: 1 + temp.find('.') + 3])

  else:
    return filtered['r_frame_rate']
  
##################################################################################################
def get_ffprobe_metadata(filename):
  
  metadata = dict()

  curr_dir = os.path.abspath(os.path.curdir)
  os.chdir(params['input_dir'])

  tracks = dict()
  for stream_type in ['v', 'a', 's']:
    probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams %s -show_entries ' \
      'stream=index %s' % (stream_type, os.path.basename(filename))
    result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
    tracks[stream_type] = [int(x.replace('\r', '').split('=')[1]) for x in result.split('\n') if x]

  metadata['tracks'] = tracks

  probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams v -show_entries ' \
    'stream=width,height %s' % (os.path.basename(filename))

  result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
  metadata['dim'] = [int(x.replace('\r', '').split('=')[1]) for x in result.split('\n') if x]

  probe_command = 'ffprobe -v fatal -of flat=s=_ -select_streams a -show_entries ' \
    'stream=channels %s' % (os.path.basename(filename))

  result = subprocess.Popen(probe_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')
  metadata['audio_channels'] = [int(x.replace('\r', '').split('=')[1]) for x in result.split('\n') if x]

  os.chdir(curr_dir)
  return metadata

##################################################################################################
def get_ffmpeg_command(params, times, command_num=0, is_out=str(), track_id=-1):

  if times:
    start = '%.3f' % (times[0]); end = '%.3f' % (times[1])
    start_format = str(timedelta(seconds=int(start.split('.')[0]), milliseconds=int(start.split('.')[1])))
    end_format = str(timedelta(seconds=int(end.split('.')[0]), milliseconds=int(end.split('.')[1])))

  if params['vn'] and params['sn'] and params['tn'] and not params['an']:
    audio_ext = 'aac' if params.get('aac') else 'opus'
    temp_name = '%s_%02d.%s' % (params['in'][:-4], command_num + 1, audio_ext)
  elif params['vn'] and params['an'] and params['tn'] and not params['sn']:
    subtitle_ext = 'ass'
    temp_name = '%s_%02d.%s' % (params['in'][:-4], command_num + 1, subtitle_ext)
  else:
    temp_name = '%s_%02d.%s' % (params['in'][:-4], command_num + 1, params['source_file'][-3:])
    
  if is_out:
    temp_name = is_out

  if params['dest']:
    temp_name = '"%s"' % (os.path.join(params['dest'], temp_name))
    
  if params['rs']:
    video_scaling = '-vf scale=%s:%s' % (params['rs'][0], params['rs'][1])
  else:
    video_scaling = str()

  if params['vn']:
    video_encoding = '-vn'
  else:
    if params['hevc']:
      video_encoding = '-map 0:v -c:v libx265 -preset slower -x265-params crf=%s:aq-mode=%s:' \
        'aq-strength=%s:subme=5' % (params['crf'], params['aqm'], params['aqs'])
    else:
      video_encoding = '-map 0:v -c:v libx264 -preset veryslow -crf %s -aq-mode %s -aq-strength %s' % (
        params['crf'], params['aqm'], params['aqs'])

    if params.get('frame_rate'):
      video_encoding += ' -r %.3f' % (params['frame_rate'])

  if params['an']:
    audio_encoding = '-an'
  else:
    if params.get('aac'):
      audio_encoder = '-c:a libfdk_aac -vbr 4'
    else:
      if track_id != -1:
        channels = params['audio_channels'][params['all_tracks']['a'].index(track_id)]
        audio_encoder = '-c:a libopus -b:a %d -vbr on -compression_level 10' % (
          80000 * (channels / 2))
      else:
        channels = params['audio_channels'][-1]
        audio_encoder = '-c:a libopus -b:a %d -vbr on -compression_level 10' % (
          80000 * (channels / 2))

    if track_id is not -1:
      audio_encoding = '-map 0:%d %s' % (track_id, audio_encoder)
    else:
      audio_encoding = '-map 0:a %s' % (audio_encoder)
    
  if params['sn']:
    subtitle_transcoding = '-sn'
  else:
    if track_id is not -1:
      subtitle_transcoding = '-map 0:%d -c:s copy' % (track_id)
    else:
      subtitle_transcoding = '-map 0:s -c:s copy'
    
  if params['tn']:
    attachments = str()
  else:
    attachments = '-map 0:t'
    
  if params['map_ch']:
    chapter_attachment = str()
  else:
    chapter_attachment = '-map_chapters -1'
    
  if not params['hi']:
    ffmpeg_version = 'ffmpeg'
  else:
    ffmpeg_version = 'ffmpeg-hi'

  if not params['nthread']:
    PID = 'PID%02d' % (command_num + 1)
    threading = '& %s=$!' % (PID)
  else:
    threading = str()
    PID = str()
  
  if times and not temp_name.endswith('ass'):
    ffmpeg_command = '%s -i %s -vsync -1 -ss %s -to %s %s %s %s %s %s %s %s %s' % (ffmpeg_version, 
      params['source_file'], start_format, end_format, video_encoding, audio_encoding, 
      subtitle_transcoding, attachments, chapter_attachment, video_scaling, temp_name, threading)
  else:
    ffmpeg_command = '%s -i %s %s %s %s %s %s %s %s %s' % (ffmpeg_version, params['source_file'], 
      video_encoding, audio_encoding, subtitle_transcoding, attachments, chapter_attachment, 
      video_scaling, temp_name, threading)

  return {
    'command': ffmpeg_command,
    'temp_name': temp_name,
    'pid': PID,
  }

##################################################################################################
def get_ssh_commands(params):
  
  if params['node'] != -1:
    curr_dir = '/'.join([x.replace('state', 'export').replace('partition1', '') 
      for x in os.getcwd().split('/')])

    start_ssh = 'ssh compute-0-%s << EOF' % params['node']
    change_dir = 'cd %s' % (curr_dir)
    exit_ssh = 'EOF\nexit'
  else:
    start_ssh = str(); change_dir = str(); exit_ssh = str()

  return {
    'login': start_ssh,
    'chdir': change_dir,
    'logout': exit_ssh
  }

##################################################################################################
def get_metadata(filename):

  if not os.path.isfile(filename):
    print('File does not exist: %s' % (filename))
    return None

  info_command = r'mediainfo --Inform="General;%Duration/String3%\n%UniqueID%"' 
  info_command = '%s %s' % (info_command, filename)

  result = subprocess.Popen(info_command, shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8')

  metadata = dict()
  metadata['duration'], suid = [x.replace('\r', '') for x in result.split('\n') if len(x) > 2]
  metadata['suid'] = "{0:X}".format(int(suid))
  metadata['name'] = filename
  
  return metadata

##################################################################################################
def get_names_and_order(times_list, params):

  has_op = True; has_ed = True; fixed_names = list()

  if params.get('avs_chapters'):
    fixed_names = params['avs_chapters']['names']
    times_list = params['avs_chapters']['times']

    if 'opening' in [x.lower() for x in fixed_names]:
      has_op = False
    if 'ending' in [x.lower() for x in fixed_names]:
      has_ed = False

  if len(times_list) == 1 and (params['op'] and params['ed']):
    names = ['Opening', 'Episode', 'Ending']
    order = [params['op'], times_list[0], params['ed']]
    
  elif len(times_list) == 1 and (params['op'] and not params['ed']):
    if fixed_names and times_list[0][0] > 50:
      names = ['Opening']; names.extend(fixed_names)
      order = [params['op']]; order.extend(times_list)
    else:
      names = ['Opening', 'Episode']
      order = [params['op'], times_list[0]]
    
  elif len(times_list) == 1 and (not params['op'] and params['ed']):
    names = ['Episode', 'Ending']
    order = [times_list[0], params['ed']]

  elif len(times_list) == 1 and (not params['op'] and not params['ed']):
    names = ['Episode']
    order = times_list

  elif len(times_list) == 2 and (params['op'] and params['ed']):
    if times_list[0][0] == 0 and (times_list[0][1] - times_list[0][0] <= 600):
      names = ['Intro', 'Opening', 'Episode', 'Ending']
      order = [times_list[0], params['op'], times_list[1], params['ed']]
    else:
      names = ['Opening', 'Episode', 'Ending', 'Preview']      
      new_times = list(); offset = times_list[0][0]
      new_times.append((times_list[0][0] - offset, times_list[0][1] - offset))
      new_times.append((times_list[1][0] - offset, times_list[1][1] - offset))

      order = [params['op'], new_times[0] , params['ed'], new_times[1]]
  
  elif len(times_list) == 2 and (params['op'] and not params['ed']):
    if fixed_names and times_list[0][0] < 50:
      names = fixed_names
      order = times_list
    elif fixed_names and times_list[0][0] > 50:
      names = ['Opening']; names.extend(fixed_names)
      order = [params['op']]; order.extend(times_list)
    elif times_list[0][0] == 0 and (times_list[0][1] - times_list[0][0] <= 600):
      names = ['Intro', 'Opening', 'Episode']
      order = [times_list[0], params['op'], times_list[1]]
    elif times_list[0][0] == 0 and (times_list[0][1] - times_list[0][0] >= 600):
      names = ['Episode', 'Opening', 'Preview']
      order = [times_list[0], params['op'], times_list[1]]
    else:
      names = ['Opening', 'Episode', 'Preview']
      order = [params['op'], times_list[0], times_list[1]]

  elif len(times_list) == 2 and (not params['op'] and params['ed']):
    if times_list[0][0] == 0 and (times_list[0][1] - times_list[0][0] <= 600):
      names = ['Intro', 'Episode', 'Ending']
      order = [times_list[0], times_list[1], params['ed']]
    else:
      names = ['Episode', 'Ending', 'Preview']
      order = [times_list[0], params['ed'], times_list[1]]

  elif len(times_list) == 2 and (not params['op'] and not params['ed']):
    if times_list[0][0] == 0 and (times_list[0][1] - times_list[0][0] <= 600):
      names = ['Intro', 'Episode']
      order = times_list
    else:
      names = ['Episode', 'Preview']
      order = times_list

  elif len(times_list) == 3 and (params['op'] and params['ed']):
    if fixed_names:
      names = list(); order = list();
      is_op = True

      for index, times in enumerate(times_list):

        if index == 0 and times[0] > 50:
          names.append('Opening')
          order.append(params['op'])
          is_op = False

        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Opening' if is_op else 'Ending')
          order.append(times_list[index]); order.append(params['op'] if is_op else params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index]);
          order.append(times_list[index]);

    else:
      names = ['Intro', 'Opening', 'Episode', 'Ending', 'Outro']
      order = [times_list[0], params['op'], times_list[1], params['ed'], times_list[2]]

  elif len(times_list) == 3 and (params['op'] and not params['ed']):
    if fixed_names and times_list[0][0] > 50:
      names = ['Opening']; names.extend(fixed_names)
      order = [params['op']]; order.extend(times_list)
    else:
      names = ['Intro', 'Opening', 'Episode', 'Outro']
      order = [times_list[0], params['op'], times_list[1], times_list[2]]

  elif len(times_list) == 3 and (not params['op'] and params['ed']):
    if fixed_names and times_list[2][0] - times_list[1][1] > 50:
      names = fixed_names[:2]; names.append('Ending'); names.extend(fixed_names[2:])
      order = times_list[:2]; order.append(params['ed']); order.extend(times_list[2:])
    else:
      names = ['Intro', 'Episode', 'Ending', 'Outro']
      order = [times_list[0], times_list[1], params['ed'], times_list[2]]

  elif len(times_list) == 3 and (not params['op'] and not params['ed']):
    if fixed_names:
      names = fixed_names
      order = times_list
    else:
      names = ['Intro', 'Episode', 'Outro']
      order = times_list

  elif len(times_list) == 4 and (params['op'] and params['ed']):
    if fixed_names:
      names = list(); order = list();
      is_op = True
      
      for index, times in enumerate(times_list):

        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Opening' if is_op else 'Ending')
          order.append(times_list[index]); order.append(params['op'] if is_op else params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index]);
          order.append(times_list[index]);

  elif len(times_list) == 4 and (params['op'] and not params['ed']):
    if fixed_names and times_list[0][0] > 50:
      names = ['Opening']; names.extend(fixed_names)
      order = [params['op']]; order.extend(times_list)
    elif fixed_names and times_list[0][0] < 50 and (times_list[1][0] - times_list[0][1]) > 50:
      names = fixed_names[:1]; names.append('Opening'); names.extend(fixed_names[1:])
      order = times_list[:1]; order.append(params['op']); order.extend(times_list[1:])
    elif fixed_names and times_list[0][0] < 50 and (times_list[1][0] - times_list[0][1]) < 1 \
      and (times_list[2][0] - times_list[1][1]) > 50:
      names = fixed_names[:2]; names.append('Opening'); names.extend(fixed_names[2:])
      order = times_list[:2]; order.append(params['op']); order.extend(times_list[2:])

  elif len(times_list) == 4 and (not params['op'] and not params['ed']):
    if fixed_names:
      names = fixed_names
      order = times_list

  elif len(times_list) == 5 and (params['op'] and params['ed']):
    if fixed_names:
      names = list(); order = list();
      is_op = True
      
      for index, times in enumerate(times_list):

        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Opening' if is_op else 'Ending')
          order.append(times_list[index]); order.append(params['op'] if is_op else params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index]);
          order.append(times_list[index]);

  elif len(times_list) == 5 and (params['op'] and not params['ed']):
    if fixed_names and times_list[1][0] - times_list[0][1] > 50:
      names = fixed_names[:1]; names.append('Opening'); names.extend(fixed_names[1:])
      order = times_list[:1]; order.append(params['op']); order.extend(times_list[1:])

  elif len(times_list) == 5 and (not params['op'] and params['ed']):
    names = list()
    order = list()

#    if fixed_names and times_list[4][0] - times_list[3][1] > 50:
 #     names = fixed_name[:4]; names.append('Ending'); names.extend(fixed_names[4:])
  #    order = times_list[:4]; order.append(params['ed']); order.extend(times_list[4:])

    if fixed_names:
      for index, times in enumerate(times_list):
        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Ending')
          order.append(times_list[index]); order.append(params['ed'])

        else:
          names.append(fixed_names[index])
          order.append(times_list[index])

  return names, order

##################################################################################################
def get_chapter_content(times_list, params):
  
  import chameleon

  edition = {
    'default': 1, 
    'oc': 1 if params['op'] or params['ed'] else 0, 
    'uid': str(time.time()).replace('.', '')
  }

  if params.get('avs_chapters'):
    frames = params['avs_chapters']['frames']
    params['avs_chapters']['times'] = list()
    
    for frame in frames:
      start = float('%.3f' % (frame[0] / params['frame_rate']))
      end = float('%.3f' % (frame[1] / params['frame_rate']))
      params['avs_chapters']['times'].append((start, end))


  atoms = list()
  names, order = get_names_and_order(times_list, params)
  last_timestamp = None
  
  for num, item in enumerate(order):

    atom = dict()
    atom['uid'] = str(time.time() + num).replace('.', '')
    atom['hidden'] = 0; atom['enabled'] = 1

    if isinstance(item, dict):
      atom['start'] = '%02d:%02d:%02d.%09d' % (0, 0, 0, 0)  
      # atom['end'] = ':'.join(item['duration'].split(':')[:-1]) + ':' + 
      #   str(float(item['duration'].split(':')[-1]) - 1.25)
      atom['end'] = item['duration']
      atom['suid'] = item['suid']

    elif isinstance(item, (tuple, list)):
      continuous = False

      try:
        if abs(order[num - 1][1] - item[0]) < 1:
          continuous = True
      except:
        pass

      print(item, end=' -> ')
      if 'episode' in names[num].lower() and 'intro' not in names:
        item = (float('%.3f' % (item[0] - item[0])), float('%.3f' % (item[1] - item[0])))

      if last_timestamp:
        diff = item[1] - item[0]

        if not continuous:
          calculated_start = last_timestamp + 1 / params['frame_rate']
        else:
          calculated_start = last_timestamp
        calculated_end = calculated_start + diff - (1 / params['frame_rate'])

        item = (float('%.3f' % (calculated_start)), float('%.3f' % (calculated_end)))

      # try:
      #   if isinstance(order[num + 1], dict):
      #     item = (item[0], float('%.3f' % (item[1] - (2 / params['frame_rate']))))
      # except:
      #   pass
      
      print(item)
      offset = 1 if continuous else 0
      # offset = 0

      atom['start'] = str(timedelta(seconds=int(str(item[0]).split('.')[0]), 
        milliseconds=int(str(item[0]).split('.')[1].ljust(3, '0'))))
      atom['end'] = str(timedelta(seconds=int(str(item[1]).split('.')[0]), 
        milliseconds=int(str(item[1]).split('.')[1].ljust(3, '0')) - offset))
      
      last_timestamp = item[1]

    atom['ch-string'] = names[num]
    atoms.append(atom)

  template = chameleon.PageTemplate(CH_TEMPLATE_STRING)
  request = {'edition': edition, 'atoms': atoms}
  response = template(**request)
  
  return response

##################################################################################################
def get_chapter_mux_command(params):

  input_name = os.path.abspath(params['encoded']).replace('/cygdrive/c/', 'C:/')
  basename, ext = os.path.splitext(input_name)
  output_name = '%s_FINAL%s' % (basename, ext)
  chapter_name = os.path.abspath(params['chapter']['filename']).replace('/cygdrive/c/', 'C:/')

  command = "mkvmerge --ui-language en --output '%s' --no-track-tags --no-global-tags " \
    "'(' '%s' ')' --chapter-language eng --chapter-charset UTF-8 --chapters '%s'" % (output_name,
      input_name, chapter_name)

  return command

##################################################################################################
def handle_display(bash_commands, bash_filename, concat_commands, concat_filename):
  
  if bash_commands:
    print('#' * 50 + '\nbash commands: [%s]' % (bash_filename))
    for i in bash_commands:
      print(i)

  if concat_commands:
    print('#' * 50 + '\nconcate file contents: [%s]' % (concat_filename))
    for i in concat_commands:
      print(i)

##################################################################################################
def handle_prompt():
  
  choice = input('\nContinuing will write these files to disk [y/n]: ')
  if choice.lower() != 'y':
    print('Program interrupted by user.')
    exit(0)

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

  os.remove(temp_name)

##################################################################################################
def handle_execution(params, bash_filename):

  if params['node'] != -1 and not params['nohup']:
    if params['dest']:
      params['nohup'] = os.path.join(params['dest'], os.path.splitext(params['in'])[0] + '.log')
    else:
      params['nohup'] = os.path.splitext(params['in'])[0] + '.log'

  if params['nohup']:
    command = 'nohup bash %s &> %s&' % (bash_filename, params['nohup'])
  else:
    command = 'bash %s' % (bash_filename)
  start_external_execution(command)

##################################################################################################
def add_external_commands(ffmpeg_obj, flag_str='bctw'):

  global concat_commands, bash_commands, wait_commands, temp_filenames

  if 'c' in flag_str:
    concat_commands.append('file %s' % (ffmpeg_obj['temp_name']))

  if 't' in flag_str:
    temp_filenames.append(ffmpeg_obj['temp_name'])

  if 'b' in flag_str:
    bash_commands.append(ffmpeg_obj['command'])

  if 'w' in flag_str:
    wait_commands.append('wait $%s' % (ffmpeg_obj['pid'])) if ffmpeg_obj['pid'] else str()

##################################################################################################
def handle_chapter_writing(params):

  if not params.get('cc'):
    return

  params['op'] = get_metadata(params['op']) if params.get('op') else None
  params['ed'] = get_metadata(params['ed']) if params.get('ed') else None
  
  params['chapter'] = {
    'content': get_chapter_content(times_list, params),
    'filename': '%s_chapter.xml' % (params['in'][:-4])
  }

  f = open(params['chapter']['filename'], 'w')
  f.write(params['chapter']['content'])
  f.close()

  print('#' * 50 + '\n' + 'Chapter file written: %s' % (params['chapter']['filename']))
  print('\n'); exit(0)

##################################################################################################
def process_encoding_settings(params):

  if not params.get('crf'):
    
    if params.get('rs') and len(params['rs']) == 2:
      resulting_height = int(params['rs'][1])
    else:
      resulting_height = params['dim'][1]

    if resulting_height > 900 and resulting_height <= 1100:
      crf = 23
    elif resulting_height > 700 and resulting_height <= 900:
      crf = 21
    elif resulting_height > 500 and resulting_height <= 700:
      crf = 19
    elif resulting_height > 300 and resulting_height <= 500:
      crf = 18

    if params.get('hevc'):
      crf -= 2

    params['crf'] = crf

  if not params.get('aqm'):
    params['aqm'] = 3
  if not params.get('aqs'):
    params['aqs'] = 1.00 if not params.get('hevc') else 0.8

  return params

##################################################################################################
def handle_subtitle_trimming(params, subtitle_filename):

  print('#' * 50)
  print('Trimming [%s] using [%s]' % (subtitle_filename, params['in']))

  subtitle_times = list()
  for times in times_list:
    start_time = str(timedelta(seconds=int(str(times[0]).split('.')[0]), 
        milliseconds=int(str(times[0]).split('.')[1].ljust(3, '0'))))
    
    end_time = str(timedelta(seconds=int(str(times[1]).split('.')[0]),
                             milliseconds=int(str(times[1]).split('.')[1].ljust(3, '0'))))
  
    subtitle_times.append((pysubs.misc.Time(start_time), pysubs.misc.Time(end_time)))

  subs = pysubs.SSAFile()
  subs.from_file(subtitle_filename, encoding='utf8')

  new_subs = pysubs.SSAFile()
  new_subs.info = subs.info.copy()
  new_subs.styles = subs.styles.copy()
  new_subs.fonts = subs.fonts.copy()

  shift = pysubs.misc.Time('00:00:00.000')
  for (index, times) in enumerate(subtitle_times):
    if index > 0:
      if index == len(subtitle_times) - 1:
        time_per_frame = ('%.4f' % (1 / float(params['frame_rate'])))[:-1]
        shift_offset = str(float(time_per_frame) * 1)
        shift += times[0] - subtitle_times[index - 1][1] + pysubs.misc.Time(
          '00:00:0' + shift_offset)
      else:
        shift += times[0] - subtitle_times[index - 1][1]

      shifting_time = [-x for x in shift.to_times()]

    elif index == 0:
      shift += subtitle_times[index][0] - pysubs.misc.Time('00:00:00.000')
      shifting_time = [-x for x in shift.to_times()]

    line_prints = 0
    for line in subs:
      new_line = None

      if line.start >= times[0] and line.end <= times[1]:
        new_line = line.copy()

      if line.start < times[0] < line.end:
        new_line = line.copy()
        new_line.start = times[0]

      if line.start < times[1] < line.end:
        new_line = line.copy()
        new_line.end = times[1]

      if line.start < times[0] < times[1] < line.end:
        new_line = line.copy()
        new_line.start = times[0]
        new_line.end = times[1]

      if shift > pysubs.misc.Time('00:00:00.000') and new_line:        
        new_line.shift(
          s=shifting_time[2], ms=shifting_time[3],
          m=shifting_time[1], h=shifting_time[0])
      
      if new_line:
        new_subs.events.append(new_line)

  new_subs.save(subtitle_filename)
  print('Trimmed file written to: [%s]' % (subtitle_filename))
  print('#' * 50)

##################################################################################################
if __name__ == '__main__':
  
  params = get_params()
  times_list = list()

  if not params['in'].endswith('.avs'):
    params['avs'] = False
    print('Not an avscript. [Skipping custom commands processing from the given input]')
    params['source_file'] = params['in']
  else:
    params['avs'] = True
    commands = get_custom_commands(params['in'])
    
    if commands.get('input'):
      params['source_file'] = os.path.join(os.path.dirname(params['in']), commands['input'])
    else:
      params['source_file'] = get_source(params['in'])

    params['avs_chapters'] = commands.get('avs_chapters')

    if params.get('fr'):
      params['frame_rate'] = params['fr']
    else:
      if commands.get('frame_rate'):
        params['frame_rate'] = float(commands['frame_rate'])
      else:
        params['frame_rate'] = get_frame_rate(params['source_file'])

    times_list = get_trim_times(params['in'], params['frame_rate'])

  metadata = get_ffprobe_metadata(params['source_file'])
  tracks = metadata['tracks']
  params['all_tracks'] = metadata['tracks']
  params['dim'] = metadata['dim']
  params['audio_channels'] = metadata['audio_channels']
  params['in'] = os.path.basename(params['in'])

  params = process_encoding_settings(params)
  print('Source:', params['source_file'])
  print(params)
  print('#' * 50)

  ssh = get_ssh_commands(params)
  handle_chapter_writing(params)

  bash_commands = list() 
  wait_commands = list()
  concat_commands = list()
  temp_filenames = list()

  if params['rs']:
    bash_filename = '%s_%s_%s.sh' % (params['in'][:-4], params['rs'][0], params['rs'][1])
    concat_filename = '%s_%s_%s.txt' % (params['in'][:-4], params['rs'][0], params['rs'][1])
  
  else:
    bash_filename = '%s.sh' % (params['in'][:-4])
    concat_filename = '%s.txt' % (params['in'][:-4])

  if len(tracks['a']) > 1 and not params.get('track') and not params.get('an'):
    for track_id in tracks['a']:
      audio_options = '-hi -aac' if params.get('aac') else str()
      python_command = 'python3 %s %s -track %d %s -nthread -x' % (__file__, params['in'], 
        track_id, audio_options)
      start_external_execution(python_command)

    exit(0)

  elif len(tracks['s']) > 0 and params.get('track') is None and not params.get('sn'):
    for track_id in tracks['s']:
      python_command = 'python3 %s %s -track %d -nthread -x' % (__file__, params['in'],
        track_id)
      start_external_execution(python_command)

  if params.get('track') is not None:
    
    if params['track'] in tracks['v']:
      params['an'], params['sn'], params['tn'] = (True, True, True)
    elif params['track'] in tracks['a']:
      params['vn'], params['sn'], params['tn'] = (True, True, True)
    elif params['track'] in tracks['s']:
      params['vn'], params['an'], params['tn'] = (True, True, True)

  if params['vn'] and params['sn'] and params['tn'] and not params['an']:
    audio_ext = 'aac' if params.get('aac') else 'opus'

    if params.get('track') is not None:
      out_name = '%s_Audio_%d.%s' % (params['in'][:-4], params['track'], audio_ext)
    else:
      out_name = '%s_Audio_%d.%s' % (params['in'][:-4], tracks['a'][0], audio_ext)
  
  elif params['vn'] and params['an'] and params['tn'] and not params['sn']:
    
    if params.get('track') is not None:
      out_name = '%s_Subtitle_final_%d.ass' % (params['in'][:-4], params['track'])
    else:
      out_name = '%s_Subtitle_final_%d.ass' % (params['in'][:-4], tracks['s'][0])
  
  elif not params['vn'] and params['sn'] and params['an'] and params['tn']:
    out_name = '%s_Encoded.mkv' % (params['in'][:-4])
  
  elif not params['vn'] and not params['sn'] and not params['an']:
    out_name = '%s_Encoded.mkv' % (params['in'][:-4])
  
  else:
    out_name = '%s_Encoded_%s.mkv' % (params['in'][:-4], str(time.time()).replace('.', ''))

  if params['dest']:
    out_name = '"%s"' % (os.path.join(params['dest'], out_name))

  if params.get('subtrim'):
    for track_id in tracks['s']:
      subtitle_filename = '%s_Subtitle_final_%d.ass' % (params['in'][:-4], track_id)
      handle_subtitle_trimming(params, subtitle_filename)
    
    exit(0)

  bash_commands.append(ssh['login']) if ssh['login'] else str()
  bash_commands.append(ssh['chdir']) if ssh['chdir'] else str()

  if (params['avs'] and not times_list) or not params['avs'] or len(times_list) == 1:
    times = times_list[0] if len(times_list) == 1 else list()
    
    if params.get('track') is not None:
      ffmpeg = get_ffmpeg_command(params, times, is_out=out_name, track_id=params['track'])
    
    else:
      ffmpeg = get_ffmpeg_command(params, times, is_out=out_name)
    
    add_external_commands(ffmpeg, 'bw')
    
  else:
    for num, times in enumerate(times_list):
      
      if params.get('track') is not None and not out_name.endswith('ass'):
        ffmpeg = get_ffmpeg_command(params, times, num, track_id=params['track'])
      
      elif params.get('track') is not None and out_name.endswith('ass'):
        ffmpeg = get_ffmpeg_command(params, times, num, track_id=params['track'], is_out=out_name)

      elif out_name.endswith('ass'):
        ffmpeg = get_ffmpeg_command(params, times, num, is_out=out_name)

      else:
        ffmpeg = get_ffmpeg_command(params, times, num)
      
      if params.get('trim') and params['trim'] == num + 1:
        add_external_commands(ffmpeg, 'bw')
      
      elif not params.get('trim'):
        add_external_commands(ffmpeg)
        
        # if params['vn'] and params['an'] and not params['sn']:
          # start = '%.3f' % (times[0]); end = '%.3f' % (times[1])
          # start_format = str(timedelta(seconds=int(start.split('.')[0]), milliseconds=int(start.split('.')[1])))
          # end_format = str(timedelta(seconds=int(end.split('.')[0]), milliseconds=int(end.split('.')[1])))
          # dialogue_line = 'Dialogue: 0,{0:s},{0:s},Default,,0000,0000,0000,,'.format(end_format[:-3])
          # time_append_command = 'echo "%s" >> %s' % (dialogue_line, ffmpeg['temp_name'])
          # add_external_commands({'command': time_append_command}, 'b')

      if out_name.endswith('ass'):
        break

  bash_commands.extend(wait_commands)

  if params['avs'] and len(times_list) > 1 and not params['trim'] and not out_name.endswith('ass'):
    bash_commands.append('ffmpeg -v fatal -f concat -i %s -map :v? -c:v copy -map :a? -c:a copy ' \
      '-map :s? -c:s copy -map 0:t? %s & PID%02d=$!' % (concat_filename, out_name, len(times_list) + 1))
    
    bash_commands.append('wait $PID%02d' % (len(times_list) + 1))
    bash_commands.extend(['rm %s & echo Deleted File: %s' % (x, x) for x in temp_filenames])

  bash_commands.append('rm %s' % (concat_filename)) if len(times_list) > 1 else None
  bash_commands.append('rm %s' % (bash_filename))
  bash_commands.append(ssh['logout']) if ssh['logout'] else str()

  if params['mx']:

    video_name = str(); audio_name = str(); sub_name = str();

    if 'v' in params['mx']:
      video_string = '-i %s_Encoded.mkv' % (params['in'][:-4])
    
    if 'a' in params['mx']:
      audio_string = '-i %s_Audio_%d.aac' % (params['in'][:-4], tracks['a'][0])
    
    if 's' in params['mx']:
      sub_string = '-i %s_Subtitle_final_%d.aac' % (params['in'][:-4], tracks['s'][0])
    
    if 'c' in params['mx']:
      ch_string = '-map_chapters -1'

    command = 'ffmpeg %s %s %s -map 0:v? -c:v copy -map 1:a? -c:a copy -map 2:s? -c:s copy ' \
      '-map 3:t? %s test000.mkv' % (video_string, audio_string, sub_string, ch_string)

    bash_commands.append(command)

  if params['prompt']:
    handle_display(bash_commands, bash_filename, concat_commands, concat_filename)
    handle_prompt()

  print(os.path.abspath(os.path.curdir))
  if params['avs'] and len(times_list) > 1:
    open(concat_filename, 'w').writelines([x + '\n' for x in concat_commands])
    
  open(bash_filename, 'w').writelines([x + '\n' for x in bash_commands])

  if params['x']:
    handle_execution(params, bash_filename)
    
    print('=' * 60)
    print('Removed script: %s' % (bash_filename))
    print('Removed concate file: %s' % (concat_filename)) if len(times_list) > 1 else None
    print('=' * 60 + '\n')

  else:
    print('Bash script created, but not executed: %s' % (bash_filename))
