import subprocess
import os
import sqlite3 as sql
import file_util
from multiprocessing.pool import ThreadPool

jxl_lossless_thresshold = 256000
curdir = file_util.get_curdir()
inputdir = "\\inputs"
outputdir = "\\outputs"
tempdir = "\\tempdir"
tooldir = "\\tools"
concurrent_worker_count = 10
recompress = False

default_method = "pingo"
save_to_db = True
db = sql.connect("history.db")

db.execute(
    "CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,filename TEXT,before_size INTEGER,before_crc INTEGER,after_size INTEGER,after_crc INTEGER)"
)


def insert_to_history(file):
    if is_archive(file.fileloc) and not isoptimized(file):
        db.execute(
            'INSERT INTO history (filename,before_size,before_crc,after_size,after_crc) values("{filename}","{before_size}","{before_crc}","{after_size}","{after_crc}")'.format(
                filename=file.filename,
                before_size=file.inputsize,
                before_crc=file.inputcrc,
                after_size=file.outputsize,
                after_crc=file.outputcrc,
            )
        )
        db.commit()


def isoptimized(file):
    count = db.execute(
        "SELECT count(*) FROM history WHERE after_size={after_size} AND after_crc={after_crc}".format(
            after_size=file.inputsize, after_crc=file.inputcrc
        )
    )
    result = count.fetchone()[0]
    if result == 0:
        return False
    else:
        return True


class inputfile:
    filename = None
    fileloc = None
    filedest = None
    type = None
    inputsize = None
    outputsize = None
    was_archived = None
    optimized = False
    inputcrc = None
    outputcrc = None

    def __init__(
        self,
        filename,
        fileloc,
        filetmploc,
        filedest,
        type,
        inputsize,
        outputsize,
        was_archived,
        optimized,
        inputcrc,
    ):
        self.filename = filename
        self.fileloc = fileloc
        self.filetmploc = filetmploc
        self.filedest = filedest
        self.type = type
        self.inputsize = inputsize
        self.outputsize = outputsize
        self.was_archived = was_archived
        self.optimized = optimized
        self.inputcrc = inputcrc


def split_list(source_list, wanted_parts=1):
    length = len(source_list)
    return [
        source_list[i * length // wanted_parts : (i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]


def main():
    file_util.clear_folder(curdir + outputdir)
    file_util.clear_folder(curdir + tempdir)
    file_util.create_directory(curdir + inputdir)
    file_util.create_directory(curdir + outputdir)
    file_util.create_directory(curdir + tempdir)
    file_util.copy_dirtree(curdir + inputdir, curdir + outputdir)

    tmparray = []
    files = file_util.get_file_list(curdir + inputdir)
    for file in files:
        dest = file.replace(inputdir, outputdir)
        tmpdir = file.replace(inputdir, tempdir).replace(
            dest.split(outputdir, 1)[-1], "\\" + str(files.index(file))
        )
        tmpfile = inputfile(
            file_util.get_filename(file),
            file,
            tmpdir,
            dest,
            default_method,
            file_util.get_filesize(file),
            0,
            is_archive(file),
            False,
            file_util.crc32(file),
        )
        tmparray.append(tmpfile)
    tmparray_chunks = split_list(tmparray, concurrent_worker_count)
    pool = ThreadPool(concurrent_worker_count)
    pool.map(ignite, tmparray_chunks)

    file_util.clear_folder(curdir + tempdir)


def scan_folder(folder):
    tmparray = []
    files = file_util.get_file_list(folder)
    for file in files:
        dest = file.replace(inputdir, outputdir)
        tmpdir = file.replace(inputdir, tempdir).replace(
            dest.split(outputdir, 1)[-1], "\\" + str(files.index(file))
        )
        tmpfile = inputfile(
            file_util.get_filename(file),
            file,
            tmpdir,
            dest,
            default_method,
            file_util.get_filesize(file),
            0,
            is_archive(file),
            False,
            file_util.crc32(file),
        )
        tmparray.append(tmpfile)
    ignite(tmparray)


def type_to_target(type):
    match type:
        case "pingo":
            return ".webp"
        case "cwebp":
            return ".webp"
        case "cjxl":
            return ".jxl"


def ignite(file_array):
    for file in file_array:
        engine(file)


def check_file(file):
    if (
        not is_smaller(file)
        or file_util.get_filesize(
            "{}".format(
                file.fileloc.replace(
                    file_util.get_fileext(file.fileloc), type_to_target(file.type)
                ),
            )
        )
        == 0
    ):
        file_util.remove_file(
            "{}".format(
                file.fileloc.replace(
                    file_util.get_fileext(file.fileloc), type_to_target(file.type)
                )
            )
        )
        print(
            "[E]["
            + file.type
            + "]"
            + file.fileloc.replace(
                file_util.get_fileext(file.fileloc), type_to_target(file.type)
            )
            + " is not found or file size is bigger than the original file size."
        )
        if file.type == "pingo":
            file.type = "cwebp"
        elif file.type == "cwebp":
            file.type = "cjxl"
        engine(file)


def is_smaller(file):
    """Compares sizes of input and output
    input/100*10<input-output

    Args:
        file (obj): Dosya objesi

    Returns:
        Bool: True: inputsize > outputsize | False: inputsize <= outputsize
    """

    if file.inputsize / 100 * 20 <= file.inputsize - file.outputsize:
        print(
            file.filename, file.inputsize / 100 * 20, file.inputsize - file.outputsize
        )
        return True
    else:
        return False


def get_target_size(file):
    return int(file.inputsize / 2)


def engine(file):
    if file.inputsize == 0:
        print("[E]Dosya boyutu 0:{}".format(file.fileloc))
    elif recompress:
        file.type = "cwebp"
    elif (
        file_util.get_fileext(file.fileloc) == ".webp"
        or file_util.get_fileext(file.fileloc) == ".jxl"
    ) and not recompress:
        file_util.move_file(file.fileloc, file.filedest)
    else:
        if file.was_archived:
            if file_util.check_zipfile(file.fileloc):
                file_util.unzipfolder(file.fileloc, file.filetmploc)
                scan_folder(file.filetmploc)
                file_util.zipfolder(file.filedest, file.filetmploc + "\\")
                os.rename(file.filedest + ".zip", file.filedest.removesuffix(".zip"))
                file.outputcrc = file_util.crc32(file.filedest)
        else:
            ext = file_util.get_fileext(file.fileloc)
            match file.type:
                case "pingo":
                    subprocess.run(
                        '{}\\pingo.exe -webp-lossy=50 -s9 "{}"'.format(
                            curdir,
                            file.fileloc,
                        ),
                        shell=False,
                        capture_output=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    file.outputsize = file_util.get_filesize(
                        "{}".format(
                            file.fileloc.replace(
                                file_util.get_fileext(file.fileloc),
                                type_to_target(file.type),
                            ),
                        )
                    )

                    check_file(file)

                    if (
                        ext == ".jpg"
                        or ext == ".jpeg"
                        or ext == ".png"
                        or ext == ".gif"
                    ):
                        file_util.remove_file(file.fileloc)
                case "cjxl":
                    if file.inputsize >= jxl_lossless_thresshold:
                        args = "-d 3"
                    else:
                        args = ""

                    subprocess.run(
                        '{dir}\\cjxl.exe {args} "{input}" "{output}"'.format(
                            dir=curdir,
                            args=args,
                            input=file.fileloc,
                            output=file.filedest.replace(
                                file_util.get_fileext(file.filedest), ".jxl"
                            ),
                        ),
                        shell=False,
                        capture_output=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    file.outputsize = file_util.get_filesize(
                        "{}".format(
                            file.fileloc.replace(
                                file_util.get_fileext(file.fileloc),
                                type_to_target(file.type),
                            ),
                        )
                    )

                    if (
                        ext == ".jpg"
                        or ext == ".jpeg"
                        or ext == ".png"
                        or ext == ".gif"
                        or ext == ".webp"
                    ):
                        file_util.remove_file(file.fileloc)

                case "cwebp":
                    subprocess.run(
                        '{}\\cwebp.exe -q 50 -af -m 6 -sharp_yuv "{}" -o "{}"'.format(
                            curdir,
                            file.fileloc,
                            file.filedest.replace(
                                file_util.get_fileext(file.filedest), ".webp"
                            ),
                        ),
                        shell=False,
                        capture_output=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    file.outputsize = file_util.get_filesize(
                        "{}".format(
                            file.fileloc.replace(
                                file_util.get_fileext(file.fileloc),
                                type_to_target(file.type),
                            ),
                        )
                    )

                    check_file(file)
                    if (
                        ext == ".jpg"
                        or ext == ".jpeg"
                        or ext == ".png"
                        or ext == ".gif"
                    ):
                        file_util.remove_file(file.fileloc)

    return file.outputsize


def is_archive(file):
    return bool(str(file_util.get_fileext(file)).lower() in (".cbz", ".zip"))


main()
