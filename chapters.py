import os
import time
import chameleon
from datetime import timedelta
from metadata import get_metadata


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
def get_names_and_order(times_list, params):

  fixed_names = list()

  if params.get('avs_chapters'):
    fixed_names = params['avs_chapters']['names']
    times_list = params['avs_chapters']['times']

  if params.get('config') and params['config'].get('names'):
    fixed_names = [x.capitalize() for x in params['config']['names']]

  print('Original Timings:', times_list)
  
  diff = 0
  applied = 1
  new_times_list = list()

  for index, times in enumerate(times_list):
    offset = '%.3f' % ((1 / params['frame_rate']) * applied)
    offset = float(offset)

    if index == len(times_list) - 1:
      offset = 0

    if index < len(times_list) -1 and \
      times_list[index + 1][0] - times_list[index][1] < 5: 
      offset = 0
    
    if index == 0 and times_list[index][1] < 10 * 60:
      offset = 0

    if offset > 0:
      applied +=1

    new_times = (float('%.3f' % (times[0] - diff)),
      float('%.3f' % (times[1] - offset)))

    if index < len(times_list) - 1 and \
        times_list[index + 1][0] - times_list[index][1] < 5:
      diff = times[1] - new_times[1]
    else:
      diff = 0
    
    new_times_list.append(new_times)
  
  print('+Chapter Timings:', new_times_list)
  print('#' * 50)

  times_list = new_times_list
  if len(times_list) == 1 and (params['op'] and params['ed']):
    names = ['Opening', 'Episode', 'Ending']
    offset = times_list[0][0]
    times_list[0] = (times_list[0][0] - offset, times_list[0][1] - offset)
    order = [params['op'], times_list[0], params['ed']]
    
  elif len(times_list) == 1 and (params['op'] and not params['ed']):
    if fixed_names and times_list[0][0] > 50:
      offset = times_list[0][0]
      names = ['Opening']; names.extend(fixed_names)
      order = [params['op']]
      for _time in times_list:
        order.append((_time[0] - offset, _time[1] - offset))
    else:
      offset = times_list[0][0]
      names = ['Opening', 'Episode']
      order = [params['op'], (times_list[0][0] - offset, times_list[0][1] - offset)]
    
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
      offset = times_list[0][0]
      names = ['Opening']; names.extend(fixed_names)
      order = [params['op']]; order.extend([(x[0] - offset, x[1] - offset) for x in times_list])
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

  elif len(times_list) in [3, 4] and (params['op'] or params['ed']):
    if fixed_names:
      names = list(); order = list()
      offset = 0
      is_op = True if params['op'] else False

      for index, times in enumerate(times_list.copy()):

        if offset:
          times = (times[0] - offset, times[1] - offset)

        if index == 0 and times[0] > 50:
          names.append('Opening')
          order.append(params['op'])

          offset = times_list[0][0]      
          times_list = [(x[0] - offset, x[1] - offset) for x in times_list]
          is_op = False

        if index < len(times_list) - 1 and times_list[index + 1][0] - times_list[index][1] > 50:
          names.append(fixed_names[index]); names.append('Opening' if is_op else 'Ending')
          order.append(times_list[index]); order.append(params['op'] if is_op else params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index])
          order.append(times_list[index])

    else:
      names = ['Intro', 'Opening', 'Episode', 'Ending', 'Outro']
      order = [times_list[0], params['op'], times_list[1], params['ed'], times_list[2]]

  elif len(times_list) == 3 and (params['op'] and not params['ed']):
    
    if fixed_names:
      offset = times_list[0][0]      
      times_list = [(x[0] - offset, x[1] - offset) for x in times_list]

      if times_list[0][0] > 50:
        names = ['Opening']; names.extend(fixed_names)
        order = [params['op']]; order.extend(times_list)
      elif fixed_names and times_list[2][0] - times_list[1][1] > 50:
        names = fixed_names[:2]; names.append('Opening'); names.extend(fixed_names[2:])
        order = times_list[:2]; order.append(params['op']); order.extend(times_list[2:])
      
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
      names = list(); order = list()
      is_op = True
      
      for index, times in enumerate(times_list):

        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Opening' if is_op else 'Ending')
          order.append(times_list[index]); order.append(params['op'] if is_op else params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index])
          order.append(times_list[index])

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

  elif len(times_list) == 4 and (not params['op'] and params['ed']):
    if fixed_names:
      names = list(); order = list()
      is_op = True
      
      for index, times in enumerate(times_list):

        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Ending')
          order.append(times_list[index]); order.append(params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index])
          order.append(times_list[index])

  elif len(times_list) == 4 and (not params['op'] and not params['ed']):
    if fixed_names:
      names = fixed_names
      order = times_list

  elif len(times_list) >= 5 and (params['op'] and params['ed']):
    if fixed_names:
      names = list(); order = list()
      is_op = True

      offset = 0
      for index, times in enumerate(times_list):

        if index == 0 and times_list[index][0] > 50:
          names.append('Opening')
          order.append(params['op'])
          offset = times_list[index][0]
          is_op = False

        if offset > 0:
          times_list[index] = tuple([x - offset for x in times_list[index]])
      
        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Opening' if is_op else 'Ending')
          order.append(times_list[index]); order.append(params['op'] if is_op else params['ed'])
          is_op = False

        else:
          names.append(fixed_names[index])
          order.append(times_list[index])

  elif len(times_list) == 5 and (params['op'] and not params['ed']):
    if fixed_names and times_list[1][0] - times_list[0][1] > 50:
      names = fixed_names[:1]; names.append('Opening'); names.extend(fixed_names[1:])
      order = times_list[:1]; order.append(params['op']); order.extend(times_list[1:])

  elif len(times_list) == 5 and (not params['op'] and params['ed']):
    names = list()
    order = list()

  # if fixed_names and times_list[4][0] - times_list[3][1] > 50:
  #   names = fixed_name[:4]; names.append('Ending'); names.extend(fixed_names[4:])
  #   order = times_list[:4]; order.append(params['ed']); order.extend(times_list[4:])

    if fixed_names:
      for index, times in enumerate(times_list):
        if index < len(times_list) - 1 and times_list[index + 1][0] - times[1] > 50:
          names.append(fixed_names[index]); names.append('Ending')
          order.append(times_list[index]); order.append(params['ed'])

        else:
          names.append(fixed_names[index])
          order.append(times_list[index])


  elif len(times_list) == 5 or len(times_list) == 6 and \
    (not params['op'] and not params['ed']):
    if fixed_names:
      names = list(); order = list()
      
      for index, times in enumerate(times_list):
        names.append(fixed_names[index])
        order.append(times_list[index])


  return names, order

##################################################################################################
def get_chapter_content(times_list, params):

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
      atom['end'] = item['duration']
      atom['suid'] = item['suid']

    elif isinstance(item, (tuple, list)):
      item = tuple([float('%.03f' % (value)) for value in item])

      if num > 0:
        if isinstance(order[num - 1], dict) or \
          abs(order[num - 1][1] - item[0]) > 1:
          continuous = False
        else:
          continuous = True
          continuity_offset = item[0] - order[num - 1][1]

      print(item, end=' -> ')

      if last_timestamp:
        diff = item[1] - item[0]

        if not continuous:
          if num <= 2:
            calculated_start = last_timestamp + 1 / params['frame_rate']
          elif num > 2:
            calculated_start = last_timestamp + 2 / params['frame_rate']

          calculated_end = calculated_start + diff
        else:
          calculated_start = last_timestamp
          calculated_end = calculated_start + diff + continuity_offset

        item = (float('%.3f' % (calculated_start)), float('%.3f' % (calculated_end)))

      print(item)
      atom['start'] = str(timedelta(seconds=int(str(item[0]).split('.')[0]), 
        milliseconds=int(str(item[0]).split('.')[1].ljust(3, '0'))))

      atom['end'] = str(timedelta(seconds=int(str(item[1]).split('.')[0]), 
        milliseconds=int(str(item[1]).split('.')[1].ljust(3, '0'))))
      
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
def handle_chapter_writing(params):

  if not params.get('cc'):
    return

  config_trims = params.get('config', dict()).get('trims', list())
  if params['config'] and not config_trims:
    print('No OC parts detected. Skipping chapter creation.')
    exit(0)

  if not params['op'] and params.get('config') and params['config'].get('op'):
    params['op'] = get_metadata(params, params['config']['op'])
  if not params['ed'] and params.get('config') and params['config'].get('ed'):
    params['ed'] = get_metadata(params, params['config']['ed'])

  params['op'] = get_metadata(params, params['op']) \
    if isinstance(params.get('op'), str) else params['op']
  params['ed'] = get_metadata(params, params['ed']) \
    if isinstance(params.get('ed'), str) else params['ed']

  # if params['source_delay']:
  #   chapter_delay = -1 * int(params['source_delay'])
  #   new_times = list()
  #   for part in times_list:
  #     new_part = list()
  #     for timestamp in part:
  #       if timestamp > 0:
  #         timestamp = '%.3f' % (timestamp)
  #         seconds, millisecs = [int(x) for x in timestamp.split('.')]
  #         timestamp = (seconds * 1000) + millisecs
  #         timestamp += chapter_delay
  #         timestamp = float('%.3f' % (timestamp / 1000))

  #       new_part.append(timestamp)
  #     new_times.append(tuple(new_part))
  # times_list = new_times

  params['chapter'] = {
    'content': get_chapter_content(
      params['cuts']['original']['timestamps'], params),
    'filename': '%s_chapter.xml' % (params['in'][:-4])
  }

  f = open(params['chapter']['filename'], 'w')
  f.write(params['chapter']['content'])
  f.close()

  print('#' * 50 + '\n' + 'Chapter file written: %s' % (params['chapter']['filename']))
  print('\n'); exit(0)
