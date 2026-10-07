"""Portable package integrity, path safety and Windows filename regressions."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from data_packages import SCHEMA, extract_checked


def archive(path, entries):
    with tarfile.open(path,'w:gz') as output:
        for name,data,kind in entries:
            entry=tarfile.TarInfo(name)
            if kind=='link':entry.type=tarfile.SYMTYPE;entry.linkname='../outside'
            else:entry.size=len(data)
            output.addfile(entry,io.BytesIO(data) if kind!='link' else None)


class PackageTest(unittest.TestCase):
    def test_valid_case_sensitive_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'data';target.mkdir();path=root/'archive.tar.gz'
            data=b'public data';name='tcga/TCGA-KIRC/count_matrix.tsv'
            package={'schema_version':SCHEMA,'files':{name:hashlib.sha256(data).hexdigest()}}
            archive(path,[('package.json',json.dumps(package).encode(),'file'),(name,data,'file')])
            self.assertEqual(extract_checked(path,target),package)
            self.assertEqual((target/name).read_bytes(),data)

    def test_unsafe_paths_links_duplicates_and_size(self):
        cases=[('../outside','file'),('/outside','file'),('C:/outside','file'),('a\\outside','file'),('a/CON.txt','file'),('a/file.','file'),('a/link','link')]
        for name,kind in cases:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);target=root/'data';target.mkdir();path=root/'archive.tar.gz'
                archive(path,[(name,b'x',kind)])
                with self.assertRaises(ValueError):extract_checked(path,target)
                self.assertFalse((root/'outside').exists())
        for entries in [[('a.txt',b'x','file'),('A.txt',b'y','file')],[('large',b'x'*256,'file')]]:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);target=root/'data';target.mkdir();path=root/'archive.tar.gz';archive(path,entries)
                with self.assertRaises(ValueError):extract_checked(path,target,max_bytes=128)

    def test_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'data';target.mkdir();path=root/'archive.tar.gz'
            package={'schema_version':SCHEMA,'files':{'data.tsv':hashlib.sha256(b'original').hexdigest()}}
            archive(path,[('package.json',json.dumps(package).encode(),'file'),('data.tsv',b'changed','file')])
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):extract_checked(path,target)


if __name__=='__main__':unittest.main()
