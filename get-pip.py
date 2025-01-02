import os.path
import pkgutil
import shutil
import sys
import struct
import tempfile

# Pip bootstrap script
if sys.version_info[0] < 3:
    from urllib2 import urlopen
else:
    from urllib.request import urlopen

def download_file(url, target):
    response = urlopen(url)
    with open(target, 'wb') as f:
        shutil.copyfileobj(response, f)

def main():
    url = "https://bootstrap.pypa.io/get-pip.py"
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        download_file(url, tmp_file.name)
        exec(open(tmp_file.name).read())

if __name__ == "__main__":
    main()
