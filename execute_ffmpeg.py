import os
import sys
import time
import json
import argparse
import subprocess
from datetime import timedelta

import pysubs
import chameleon
from subedit import delay_subtitle
from external import start_external_execution
from metadata import get_metadata, get_ffprobe_metadata

from chapters import handle_chapter_writing
from avs import (
  source_from_avscript,get_trim_times, get_custom_commands)
from muxer import (
  add_chapter_file,
  attach_fonts, merge_video,
  mux_episode, ffmpeg_audio_mux,
  muxing_with_audio)

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

  if params['config'] and not os.path.isfile(params['config']):
      raise FileNotFoundError('Given config file does not exist: %s' % (params['config']))
  
  params['config'] = json.load(open(params['config'], 'r')) if params['config'] else list()
  if os.path.basename(params['in']) in params['config']:
    params['config'] = params['config'][os.path.basename(params['in'])]
  else:
    params['config'] = None

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
  parser.add_argument('-nohup', type=str, default=str(), help='starts process in background ' \
    'and redirects stdout, stderr to <NOHUP>. ' \
    'Also puts the job to background using nohup.')
  parser.add_argument('-rs', type=str, help='resizes output video. ' \
    'e.g. 1280:720 will give you 720p video. 1280:-1 will give you width of 1280 and height with ' \
    'respective aspect ratio. Same will apply for given height like -1:720')
  parser.add_argument('-dest', type=str, help='creates output file to given destination ' \
    'folder name. Files will be created there to begin with rather than moving them to the folder ' \
    'after completion.')
  parser.add_argument('-trim', type=int, help='processes given trimmed section only ' \
    'while ignoring rest of the video.')
  parser.add_argument('-subtrim', action='store_true', help='trims subtitles using pysubs.' \
    'trim will occur if input is an avscript (.avs) file with Trim commands.')
  parser.add_argument('-fake', type=str, help='adds fake metadata for streams to detected source. ' \
    'e.g. s:2 will add subtitle stream with track id 2. ' \
    'e.g. a:1,s:2,a:3 will add two audio streams at 1 & 3 track id and ' \
    'a subtitle stream at track id 2.')
  parser.add_argument('-track', type=int, help='processes given track id stream only ' \
    'while ignoring rest of the streams.')

  parser.add_argument('-fr', type=float, help='assumes the frame rate for the source file to <FR>.')
  parser.add_argument('-r', type=float, help='converts the frame rate for the output file to <R>.')
  parser.add_argument('-hevc', action='store_true', help='enables HEVC encoding rather than x264.')
  parser.add_argument('-aac', action='store_true', help='enables AAC audio encoding rather than OPUS.')
  
  parser.add_argument('-prompt', action='store_true', 
    help='prompts user to confirm before writing to disk.')
  parser.add_argument('-x', action='store_true', 
    help='executes the bash script, if created any, at the end.')

  parser.add_argument('-nthread', action='store_true', help='disables multithreading of ffmpegs. ' \
    'Otherwise each trimmed section will get a ffmpeg process in concurrency.')
  parser.add_argument('-vn', action='store_true', help='disables video encoding.')
  parser.add_argument('-an', action='store_true', help='disables audio encoding.')
  parser.add_argument('-sn', action='store_true', help='disables subtitle encoding / copying.')
  parser.add_argument('-tn', action='store_true', help='disables attachments processing from source.')
  parser.add_argument('-cn', action='store_true', help='disables chapters muxing from source.')
  parser.add_argument('-cc', action='store_true', help='creates chapter file from trims.')
  parser.add_argument('-mx', action='store_true', help='muxes streams at the end by mkvmerge and / or ffmpeg.')
  parser.add_argument('-hi', action='store_true', help='uses ffmpeg-hi that has non-free libs.')
  parser.add_argument('-map_ch', action='store_true', help='attaches default chapter file.')

  parser.add_argument('-op', type=str, help='specify opening file for .mkv OC.')
  parser.add_argument('-ed', type=str, help='specify ending file for .mkv OC.')

  parser.add_argument('-delay', type=int, help='this option will enable subtitle delay. ' \
    '<DELAY> can be negative as well.')
  parser.add_argument('-attach', type=str, help='this option will attach fonts to input file. ' \
    '<ATTACH> can be a path to directory or a font file.')
  parser.add_argument('-dframe', type=str, help='draws frame number on video using filter graph.')
  parser.add_argument('-config', type=str, help='path to json config file.')

  params = parser.parse_args().__dict__
  params = process_params(params)

  return params

##################################################################################################
def get_source(input_file):

  basename = os.path.basename(input_file)
  input_source = source_from_avscript(input_file)

  if not input_source:
    input_source = [x for x in os.listdir(params['input_dir']) 
      if basename[:-4] == x[:-4] and x.endswith(('.mkv', '.mp4', '.avi', '.ts'))]

    input_source = ''.join(input_source) if len(input_source) == 1 else \
      ''.join([x for x in input_source if x.endswith('.mkv')])

    if not input_source:
      raise FileNotFoundError('Could not detect input source from ' \
        'either filedisk or avscript file: %s' % input_file)

  return os.path.join(os.path.dirname(params['in']), input_source)

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
def get_fake_tracks(params):

  fake_streams = dict()
  taken_ids = [stream_id for id_list in params.get('all_tracks').values()
      for stream_id in id_list if isinstance(id_list, list) and len(id_list) >= 1]

  if params.get('fake'):
    tracks = params['fake'].split(',')

    if not tracks:
      return dict()

    for track in tracks:
      details = track.split(':')

      if not details:
        continue

      stream_type = details[0]
      stream_id = None

      for item in details:
        key = item.split('=')[0]
        value = item.split('=')[1] if len(
          item.split('=')) > 1 else None

        if 'id' in key:
          stream_id = int(value)
      
      if stream_id is None:
        available_id = [x for x in range(1, 20) if x not in taken_ids][0]
        stream_id = available_id
        taken_ids.append(available_id)

      if fake_streams.get(stream_type):
        fake_streams[stream_type].append(stream_id)
      else:
        fake_streams[stream_type] = [stream_id]

  return fake_streams

##################################################################################################
def get_ffmpeg_command(params, times, command_num=0, is_out=str(), track_id=-1):

  frame_cut = None
  if params.get('cuts') and params['cuts']['original'].get('frames'):

    original = params['cuts']['original']
    if times in original['timestamps']:
      index = original['timestamps'].index(times)
      frame_cut = original['frames'][index]

  if frame_cut:
    start_frame = frame_cut[0]
    end_frame = frame_cut[1] + 1

  if times:
    start = '%.3f' % (times[0]); end = '%.3f' % (times[1])
    start_format = str(timedelta(seconds=int(start.split('.')[0]), milliseconds=int(start.split('.')[1])))
    end_format = str(timedelta(seconds=int(end.split('.')[0]), milliseconds=int(end.split('.')[1])))

    # if params['source_delay']:
    #   keyframe_delay = -1 * int(params['source_delay'])
    #   seconds, millisecs = [int(x) for x in end.split('.')]
    #   delayed_end = ((seconds * 1000) + millisecs) + keyframe_delay
    #   delayed_end = '%.3f' % (delayed_end / 1000)
    #   delayed_end_format = str(timedelta(seconds=int(delayed_end.split('.')[0]),
    #                            milliseconds=int(delayed_end.split('.')[1])))
    #   keyframes = '-force_key_frames %s' % (delayed_end_format)
    # else:
    #   keyframes = '-force_key_frames %s' % (end_format)

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
  
  video_filters = str()
  
  if frame_cut:
    video_filters += '[0:v]trim=start_frame={start}:' \
      'end_frame={end},setpts=PTS-STARTPTS[part];'.format(
        start=start_frame, end=end_frame)
  
  if params.get('r'):
    # default for ffmpeg. chooses to be CRF or VFR
    # depending upon muxer. might result in frame
    # duplication or frame drop.
    vsync = '-vsync -1'
  else:
    # let each frame pass through. no drop / duplication.
    # shouldn't be used when forcing output frame rate
    # with -r option in ffmpeg.
    vsync = '-vsync 0'

  filters = list()

  if params['rs']:
    filters.append('scale={width}:{height}'.format(
      width=params['rs'][0], height=params['rs'][1]))

  if params['dframe']:
    filters.append(
      'drawtext=fontfile=' + params['dframe'] + ':'\
      'text=\'%{frame_num}\':start_number=0:x=(w-(tw*1.1)):y=h-(1.2*lh):' \
      'fontcolor=black:fontsize=24:box=1:boxcolor=white:boxborderw=5')

  if params['rs'] and frame_cut:
    video_filters += '[part]{complex}[out];'.format(complex=','.join(filters))
  elif params['rs'] and not frame_cut:
    video_filters += '[0:v]{complex}[out];'.format(complex=','.join(filters))
  
  if video_filters:
    video_filters = video_filters.strip(';')
    video_filters = '-filter_complex "%s"' % (video_filters)

  if params['vn']:
    video_encoding = '-vn'
  else:

    if video_filters:
      filter_output = video_filters.split('[')[-1].split(']')[0]
      video_filters = '%s -map [%s]' % (video_filters, filter_output)
    else:
      video_filters = '-map 0:v'

    if params['hevc']:
      video_encoding = '{vfilters} -c:v libx265 ' \
        '-preset slower -pix_fmt yuv420p10le -x265-params crf={crf}:aq-mode={aq_mode}:' \
        'aq-strength={aq_strength}:subme=5'.format(
          vfilters=video_filters, crf=params['crf'],
          aq_mode=params['aqm'], aq_strength=params['aqs'])
    else:
      video_encoding = '{vfilters} -c:v libx264 ' \
        '-preset veryslow -pix_fmt yuv420p10le -crf {crf} -aq-mode {aq_mode} ' \
        '-aq-strength {aq_strength}'.format(
          vfilters=video_filters, crf=params['crf'],
          aq_mode=params['aqm'], aq_strength=params['aqs'])

    if params.get('r'):
      # video_encoding += ' -r %.3f' % (params['frame_rate'])
      video_encoding += ' -r %.3f' % (params.get('r'))

  if params['an']:
    audio_encoding = '-an'
  else:

    if times:
      audio_cut = '-ss {start} -to {end}'.format(
        start=start_format, end=end_format)
    else:
      audio_cut = str()

    if params.get('aac'):
      audio_encoder = '%s -c:a libfdk_aac -vbr 4' % (audio_cut)
    else:
      if track_id != -1:
        channels = params['audio_channels'][params['all_tracks']['a'].index(track_id)]
      else:
        channels = params['audio_channels'][-1]
      
      if channels > 2:
        audio_encoder = '{audio_cut} -c:a libopus -af ' \
          'aformat=channel_layouts="7.1|5.1|stereo" ' \
          '-b:a {bitrate} -vbr on -compression_level 10'.format(
            audio_cut=audio_cut, bitrate=80000 * (channels / 2))
      else:
        audio_encoder = '{audio_cut} -c:a libopus -b:a {bitrate} ' \
          '-vbr on -compression_level 10'.format(
          audio_cut=audio_cut, bitrate=80000 * (channels / 2))

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
  
  if params['source_delay']:
    negative_delay = -1 * float(int(params['source_delay']) / 1000)
  else:
    negative_delay = 0
  
  if times and not temp_name.endswith('ass'):
    ffmpeg_command = 'nice -n 15 {ffmpeg} -itsoffset {offset} -i {input} ' \
      '{vsync} {video} {audio} {subtitle} {attachments} {chapter} ' \
      '{output} {threading}'.format(
        ffmpeg=ffmpeg_version, offset='%.3f' % (negative_delay),
        input=params['source_file'], vsync=vsync,
        video=video_encoding, audio=audio_encoding,
        subtitle=subtitle_transcoding,
        attachments=attachments, chapter=chapter_attachment,
        output=temp_name, threading=threading)
  else:
    ffmpeg_command = 'nice -n 15 {ffmpeg} -itsoffset {offset} -i {input} ' \
      '{vsync} {video} {audio} {subtitle} {attachments} {chapter} ' \
      '{output} {threading}'.format(
        ffmpeg=ffmpeg_version, offset='%.3f' % (negative_delay),
        input=params['source_file'], vsync=vsync,
        video=video_encoding, audio=audio_encoding,
        subtitle=subtitle_transcoding, attachments=attachments,
        chapter=chapter_attachment, output=temp_name,
        threading=threading)

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
def handle_subtitle_extraction(params):

  if params.get('sn') or (params.get('track') is not None and
      params.get('track') not in params['all_tracks']['s']):
    return

  for track in params.get('all_tracks').get('s'):
    if params.get('track') is not None and params['track'] != track:
      continue

    index = params.get('all_tracks')['s'].index(track)
    extension = 'srt' if 'subrip' in \
      params['all_codecs']['s'][index] else 'ass'

    output_name = params.get('in').split('.')[:-1]
    output_name = '.'.join(output_name) + '_Subtitle_final_%d.%s' % (track, extension)
    output_name = os.path.join(params.get('orig_dir'), output_name)

    mkvextract_command = 'mkvextract tracks "{source}" "{track_id}:{output}"'.format(
      source=os.path.join(params.get('orig_dir'), params.get('source_file')),
      track_id=track, output=output_name
    )

    start_external_execution(mkvextract_command)
    print('#' * 50 + '\n' + 'Subtitle file copied: %s' % (output_name))

    if params['source_delay']:
      sub_delay = -1 * int(params['source_delay'])
      delay_subtitle(output_name, sub_delay, True)

  if not params.get('subtrim'):
    print('\n'); exit(0)

##################################################################################################
def handle_subtitle_trimming(params, subtitle_filename):

  if not len(times_list) >= 1:
    return
  
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
  time_per_frame = ('%.4f' % (1 / float(params['frame_rate'])))[:-1]
  for (index, times) in enumerate(subtitle_times):
    if index > 0:
      # if index == len(subtitle_times) - 1:
      shift_offset = str(float(time_per_frame) * index)
      shift += times[0] - subtitle_times[index - 1][1] - pysubs.misc.Time(
	'00:00:0' + shift_offset)
      # else:
      #   shift += times[0] - subtitle_times[index - 1][1]

      shifting_time = [-x for x in shift.to_times()]

    elif index == 0:
      shift += subtitle_times[index][0] - pysubs.misc.Time('00:00:00.000')
      shifting_time = [-x for x in shift.to_times()]

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
def process_encoding_settings(params):

  if not params.get('crf'):
    
    if params.get('rs') and len(params['rs']) == 2:
      resulting_height = int(params['rs'][1])
    else:
      try:
        resulting_height = params['dim'][1]
      except:
        resulting_height = 720

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
def handle_muxing(params, options, must_end=False):

  if params['an'] and params['sn'] and params['tn']:
    # use mkvmerge to merge video parts.
    if options.get('temp') and len(options.get('temp')) > 1:
      merge_video(params, options.get('temp'), options.get('output'))
      exit(0)
    elif must_end:
      print('No temp files to be appended. Exiting normally.')
      exit(0)

  elif params['an'] and not(params['vn'] or params['sn'] or
    params['tn']):
    # use mkvmerge to merge video, subs, attachments and chapters.
    mux_episode(params, audio=False)
    exit(0)
  
  elif params['an'] and params['sn'] and not params['tn']:
    # use mkvmerge to merge video, attachments and chapters.
    mux_episode(params, audio=False, subs=False)
    exit(0)
  
  elif params['an'] and params['tn'] and not params['sn']:
    # use mkvmerge to merge video, subs and chapters.
    mux_episode(params, audio=False, attachments=False)
    exit(0)
  
  elif params['sn'] and params['tn'] and not params['an']:
    # use mkvmerge to merge video and chapters.
    # then use ffmpeg to merge audio with output of above mux.
    mux_result = mux_episode(params, audio=False,
      subs=False, attachments=False)
    muxing_with_audio(params, mux_result)
    exit(0)

  elif params['tn'] and not params['sn'] and not params['an']:
    # use mkvmerge to merge video, subs and chapters.
    # then use ffmpeg to merge audio with output of above mux.
    mux_result = mux_episode(params, audio=False,
      attachments=False)
    muxing_with_audio(params, mux_result)
    exit(0)
  
  else:
    # use mkvmerge to merge video, subs, attachemnts (fonts) and chapters.
    # then use ffmpeg to merge audio with output of above mux.
    mux_result = mux_episode(params, audio=False)
    muxing_with_audio(params, mux_result)
    exit(0)

##################################################################################################
if __name__ == '__main__':
  
  params = get_params()
  times_list = list()

  if params.get('delay'):
    delay_subtitle(params['in'], params.get('delay'))
    exit(0)
  
  if params.get('attach'):
    command = attach_fonts(params['in'], params.get('attach'))
    start_external_execution(command)
    exit(0)

  if not params['in'].endswith('.avs'):
    params['avs'] = False
    print('Not an avscript. [Skipping custom commands processing from the given input]')
    params['source_file'] = params['in']

    if params['config'] and params['config'].get('trims'):
      params['frame_rate'] = params['fr'] if params['fr'] else get_frame_rate(params['in'])
      params['source_delay'] = get_metadata(params, params['in']).get('delay')
      times_list = get_trim_times(params, params['in'], params['frame_rate'])
    else:
      params['source_delay'] = 0

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

    times_list = get_trim_times(params, params['in'], params['frame_rate'])
    params['source_delay'] = get_metadata(
      params, params['source_file']).get('delay')

  metadata = get_ffprobe_metadata(params, params['source_file'])
  tracks = metadata['tracks']
  params['all_tracks'] = metadata['tracks']
  params['all_codecs'] = metadata['codecs']

  params['fake_tracks'] = get_fake_tracks(params)
  params['dim'] = metadata['dim']
  params['audio_channels'] = metadata['audio_channels']
  params['orig_in'] = params['in']
  params['in'] = os.path.basename(params['in'])

  params = process_encoding_settings(params)
  print('Source:', params['source_file'])
  print(params)
  print('#' * 50)

  ssh = get_ssh_commands(params)
  handle_chapter_writing(params)

  if params.get('mx'):
    handle_muxing(params, dict())

  handle_subtitle_extraction(params)

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
      python_command = 'python3 %s %s -track %d %s -nthread -x' % (__file__, params['orig_in'], 
        track_id, audio_options)
      start_external_execution(python_command)

    exit(0)

  # elif len(tracks['s']) > 0 and params.get('track') is None and not params.get('sn'):
  #   for track_id in tracks['s']:
  #     python_command = 'python3 %s %s -track %d -nthread -x' % (__file__, params['in'],
  #       track_id)
  #     start_external_execution(python_command)

  #   if not params.get('subtrim'):
  #     exit(0);

  if params.get('track') is not None:
    
    if params['track'] in tracks['v']:
      params['an'], params['sn'], params['tn'] = (True, True, True)
    elif params['track'] in tracks['a']:
      params['vn'], params['sn'], params['tn'] = (True, True, True)
    # elif params['track'] in tracks['s']:
    #   params['vn'], params['an'], params['tn'] = (True, True, True)

  if params['vn'] and params['sn'] and params['tn'] and not params['an']:
    audio_ext = 'aac' if params.get('aac') else 'opus'

    if params.get('track') is not None:
      out_name = '%s_Audio_%d.%s' % (params['in'][:-4], params['track'], audio_ext)
    else:
      out_name = '%s_Audio_%d.%s' % (params['in'][:-4], tracks['a'][0], audio_ext)
  
  # elif params['vn'] and params['an'] and params['tn'] and not params['sn']:
    
  #   if params.get('track') is not None:
  #     out_name = '%s_Subtitle_final_%d.ass' % (params['in'][:-4], params['track'])
  #   else:
  #     out_name = '%s_Subtitle_final_%d.ass' % (params['in'][:-4], tracks['s'][0])
  
  elif not params['vn'] and params['sn'] and params['an'] and params['tn']:
    out_name = '%s_Encoded.mkv' % (params['in'][:-4])
  
  elif not params['vn'] and not params['sn'] and not params['an']:
    out_name = '%s_Encoded.mkv' % (params['in'][:-4])
  
  else:
    out_name = '%s_Encoded_%s.mkv' % (params['in'][:-4], str(time.time()).replace('.', ''))

  if params['dest']:
    out_name = '"%s"' % (os.path.join(params['dest'], out_name))

  if params.get('subtrim'):
    fake_subtitle_tracks = params['fake_tracks']['s'] if params.get('fake_tracks') \
      and params['fake_tracks'].get('s') else list()

    tracks['s'].extend(fake_subtitle_tracks)
    for track_id in tracks['s']:
      if params.get('track') is not None and params['track'] != track_id:
        continue

      index = tracks['s'].index(track_id)
      try:
        extension = 'srt' if 'subrip' in \
          params['all_codecs']['s'][index] else 'ass'
      except IndexError:
        if track_id in params['fake_tracks']['s']:
          extension = 'ass'
        else:
          raise IndexError

      subtitle_filename = '%s_Subtitle_final_%d.%s' % (
        params['in'][:-4], track_id, extension)
      handle_subtitle_trimming(params, subtitle_filename)

    exit(0)

  bash_commands.append(ssh['login']) if ssh['login'] else str()
  bash_commands.append(ssh['chdir']) if ssh['chdir'] else str()

  if len(times_list) == 1 or not times_list:
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

      if out_name.endswith('ass'):
        break

  bash_commands.extend(wait_commands)

  if params.get('mx'):
    handle_muxing(params, {
      'temp': temp_filenames,
      'output': out_name
    }, must_end=True)

  if len(times_list) > 1 and not params['trim'] and not out_name.endswith('ass'):

    # if not params.get('vn'):
    #   bash_commands.append('%s %s %s -an -sn -tn -mx & PID00=$!' % (
    #     sys.executable, os.path.realpath(__file__), params.get('orig_in')))
    #   bash_commands.append('wait $PID00')

    if params.get('vn'):
      bash_commands.append('ffmpeg -v fatal -f concat -i %s -map :v? -c:v copy -map :a? -c:a copy ' \
                           '-map :s? -c:s copy -map 0:t? %s & PID%02d=$!' % (
                            concat_filename, out_name, len(times_list) + 1))
    
      bash_commands.append('wait $PID%02d' % (len(times_list) + 1))
    
    if len(temp_filenames) > 1 and params.get('vn'):
      bash_commands.extend(['rm %s & echo Deleted File: %s' % (x, x) for x in temp_filenames])

  bash_commands.append('rm %s' % (concat_filename)) if len(times_list) > 1 else None
  bash_commands.append('rm %s' % (bash_filename))
  bash_commands.append(ssh['logout']) if ssh['logout'] else str()

  if params['prompt']:
    handle_display(bash_commands, bash_filename, concat_commands, concat_filename)
    handle_prompt()

  print(os.path.abspath(os.path.curdir))
  if len(times_list) > 1:
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
