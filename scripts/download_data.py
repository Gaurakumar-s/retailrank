"""Download only the events file from the original Retailrocket Kaggle dataset."""
from pathlib import Path
import hashlib,urllib.request,zipfile
root=Path(__file__).resolve().parents[1];target=root/'data';target.mkdir(exist_ok=True)
url='https://www.kaggle.com/api/v1/datasets/download/retailrocket/ecommerce-dataset/events.csv'
archive=target/'events.zip'
with urllib.request.urlopen(url,timeout=120) as response,archive.open('wb') as out:
    while chunk:=response.read(1024*1024):out.write(chunk)
with zipfile.ZipFile(archive) as z:
    name=next(n for n in z.namelist() if n.endswith('events.csv'))
    data=z.read(name)
    expected='3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7'
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Dataset checksum changed; inspect the new source before training.')
    (target/'events.csv').write_bytes(data)
print(target/'events.csv')
