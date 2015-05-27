import subprocess
def blah():
  try:
    subprocess.check_output(['blaasdf'])
  except Exception as e:
    print e
    print str(e)
    print e.__dict__
    print str(e.message)
    em = e.message if e.message else str(e)
    print em
    
blah()
