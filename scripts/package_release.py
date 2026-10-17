"""Create a repository ZIP containing the same files inspected by the release scan."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZipFile
from check_release import ROOT,selected_files,main as check

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if check():raise SystemExit('Release scan failed')
    files=list(selected_files())
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(args.out,'w',ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file,'redcommerce/'+file.relative_to(ROOT).as_posix())
    print(json.dumps({'zip':args.out.name,'files':len(files),'bytes':args.out.stat().st_size,
        'sha256':hashlib.sha256(args.out.read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':main()
