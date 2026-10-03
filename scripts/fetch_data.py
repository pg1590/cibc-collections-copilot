"""Download the public synthetic release and verify/extract its ZIP safely."""
import argparse
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
API='https://huggingface.co/api/datasets/nuxsh/maple-collections-hackathon?blobs=true'


def fetch():
    root=ROOT/'data';root.mkdir(exist_ok=True)
    with urllib.request.urlopen(API,timeout=60) as r: metadata=json.load(r)
    revision=metadata['sha'];filename='maple_collections_release.zip'
    item=next(x for x in metadata['siblings'] if x['rfilename']==filename)
    checksum=item.get('lfs',{}).get('sha256')
    url=f'https://huggingface.co/datasets/nuxsh/maple-collections-hackathon/resolve/{revision}/{filename}'
    target=root/filename
    if not target.exists():
        print('Downloading',url,flush=True)
        with urllib.request.urlopen(url,timeout=180) as response,target.open('wb') as out:
            while chunk:=response.read(8*1024*1024):out.write(chunk)
    digest=hashlib.file_digest(target.open('rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else sha256(target)
    if checksum and digest!=checksum:raise ValueError('Release checksum mismatch; move the incomplete ZIP aside and rerun.')
    destination=root.resolve()
    with zipfile.ZipFile(target) as z:
        for info in z.infolist():
            if not (destination/info.filename).resolve().is_relative_to(destination):raise ValueError('Unsafe archive path')
            if (info.external_attr >>16)&0o170000==0o120000:raise ValueError('Archive symlink rejected')
        z.extractall(destination)  # ZIP CRC checked by extractall.
    (root/'release-provenance.json').write_text(json.dumps({'revision':revision,'sha256':digest,'url':url,'verified_against_publisher':bool(checksum)},indent=2))
    print('Release extracted; provenance in data/release-provenance.json')


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()


if __name__=='__main__':fetch()
