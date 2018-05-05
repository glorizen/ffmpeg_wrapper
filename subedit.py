import os
import pysubs

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
  