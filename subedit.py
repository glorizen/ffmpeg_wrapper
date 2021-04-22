import os
import pysrt
import pysubs
from exceptions import FileNotFoundError

def delay_subtitle(subtitle_filename, delay, overwrite=False):

  if not(os.path.isfile(subtitle_filename) and delay != 0):
    return

  subs = pysubs.SSAFile()
  subs.from_file(subtitle_filename, encoding='utf8')

  new_subs = pysubs.SSAFile()
  new_subs.info = subs.info.copy()
  new_subs.styles = subs.styles.copy()
  new_subs.fonts = subs.fonts.copy()

  print('Processing sub file: %s' % (subtitle_filename))
  for line in subs:
    new_line = line.copy()
    new_line.shift(ms=delay)
    new_subs.events.append(new_line)

  if not overwrite:
    filename, ext = os.path.splitext(subtitle_filename)
    filename += '_edited'
    new_subs.save(filename + ext)
  
  else:
    new_subs.save(subtitle_filename)


def convert_to_ssa(subtitle_filename):

  if not os.path.isfile(subtitle_filename):
    raise FileNotFoundError('%s does not exist.' % (subtitle_filename))

  subs = pysrt.open(subtitle_filename)
  ssa_subs = pysubs.SSAFile()
  output_filename = os.path.splitext(subtitle_filename)[0] + '.ass'
  print('Converting: %s -> %s' % (subtitle_filename, output_filename))

  for line in subs:
    event = pysubs.SSAEvent()
    event.text = line.text.replace('\n', '\\N') \
      .replace('<i>', '').replace('</i>', '')

    event.start = pysubs.Time('%02d:%02d:%02d.%3d' % (
      line.start.hours, line.start.minutes,
      line.start.seconds, line.start.milliseconds))
    event.end = pysubs.Time('%02d:%02d:%02d.%3d' % (
      line.end.hours, line.end.minutes,
      line.end.seconds, line.end.milliseconds))

    ssa_subs.events.append(event)

  ssa_subs.info['PlayResX'] = '1280'
  ssa_subs.info['PlayResY'] = '720'
  ssa_subs.styles['Default'].fontsize = 40.0

  ssa_subs.save(output_filename)

