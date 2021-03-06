#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import zipfile
import logging
from pymongo import MongoClient
import gridfs
import StringIO
import hashlib
from utils import Config, get_type

try:
    import magic
except ImportError:
    pass

JOBNAME = 'ZIP2MONGODB'
FILE_CHUNK_SIZE = 16 * 1024


def get_chunks(data):
    """Read file contents in chunks (generator)."""

    fd = StringIO.StringIO(data)
    while True:
        chunk = fd.read(FILE_CHUNK_SIZE)
        if not chunk:
            break
        yield chunk
    fd.close()


# create logger

logger = logging.getLogger(JOBNAME)
logger.setLevel(logging.DEBUG)

# create console handler with a higher log level

logch = logging.StreamHandler()
logch.setLevel(logging.DEBUG)

# create formatter and add it to the handlers

formatter = \
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                      )
logch.setFormatter(formatter)

# add the handlers to the logger

logger.addHandler(logch)

# Connect to MongoDB

client = MongoClient(host=Config().database.dbhost,
                     port=Config().database.dbport)
db = client.vxcage
fs = gridfs.GridFS(db)

logging.basicConfig(format='%(levelname) -10s %(asctime)s %(message)s',
                    level=logging.DEBUG)

for zfilename in sys.argv[1:]:
    logging.info('[%s] Opening' % zfilename)
    archive = zipfile.ZipFile(zfilename)
    zipname = os.path.splitext(os.path.basename(zfilename))[0]
    archive.setpassword('infected')
    
    numOfFiles = len(archive.namelist())
    
    for (index, sampleEntry) in enumerate(archive.namelist()):
        logging.info('[%s] [%s] Got entry (%s/%s)' % (zipname, sampleEntry,
                     index + 1, numOfFiles))
        sample = archive.open(sampleEntry, 'r')
    
        sampleData = sample.read()
    
        logging.debug('[%s] [%s] Generating hashes' % (zipname,
                      sampleEntry))
        md5 = hashlib.md5(sampleData).hexdigest()
        sha1 = hashlib.sha1(sampleData).hexdigest()
        sha256 = hashlib.sha256(sampleData).hexdigest()
        sha512 = hashlib.sha512(sampleData).hexdigest()
        filetype = get_type(sampleData)
    
        logging.debug('[%s] [%s] Quering database for already existing file (hash=%s)'
                       % (zipname, sampleEntry, sha256))
        existing = db.fs.files.find_one({'sha256': sha256})
    
        upload_sample = True
        if existing:
            logging.info('[%s] [%s] Sample already exists' % (zipname,
                         sampleEntry))
            logging.info('[%s] [%s] Verifying contents' % (zipname,
                         sampleEntry))
            if not md5 == existing['md5']:
                logging.warning('[%s] [%s] Checksum not matching'
                                % (zipname, sampleEntry))
                upload_sample = True
            else:
                logging.info('[%s] [%s] Checksum matching' % (zipname,
                             sampleEntry))
                upload_sample = False
        else:
            upload_sample = True
    
        if upload_sample:
            logging.debug('[%s] [%s] Uploading sample' % (zipname,
                          sampleEntry))
            new = fs.new_file(filename=sampleEntry, sha1=sha1,
                              sha256=sha256, sha512=sha512,
                              filetype=filetype)
            for chunk in get_chunks(sampleData):
                logging.debug('[%s] [%s] writing chunk' % (zipname,
                              sampleEntry))
                new.write(chunk)
            new.close()
            logging.info('[%s] [%s] Uploaded sample' % (zipname,
                         sampleEntry))
        logging.debug('[%s] [%s] Reclaiming memory' % (zipname,
                      sampleEntry))
        sample.close()
    
        del sample
        del sampleData
    
    logging.info('[%s] Closing' % zipname)
    archive.close()
    logging.info('[%s] Removing %s' % (zipname,zfilename))
    os.remove(zfilename)

