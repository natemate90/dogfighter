#!/usr/bin/env python3
"""Reads the game's .up pack files (Resource.up, English.up and the like).

A pack starts with a 32-byte header: "UDSP", the version 0x101, then size and
offset of three tables: folders, names, files. All numbers are little-endian
32-bit. Table entries are 24 bytes.

  folder entry: name hash, name offset, 2 unused, file count, offset of its
                first file entry inside the file table
  file entry:   name hash, name offset, flags, unpacked size, stored size,
                offset of the data in the pack

Flag bit 0 marks packed data. Packed data is a row of records:
  0x65 n b0 b1 b2 b3   write the four bytes (n + 3) / 4 times
  0x66 n ...           copy the next n bytes
  0x67 n ...           the same

The game looks for a file as cache\\<path> on disk first, then <path> on disk,
then in the packs. Paths are relative to the game folder and not case-sensitive.
"""
import os
import struct
import sys


class Entry:
    __slots__ = ("folder", "name", "flags", "size", "stored", "offset")

    def __init__(self, folder, name, flags, size, stored, offset):
        self.folder, self.name, self.flags = folder, name, flags
        self.size, self.stored, self.offset = size, stored, offset

    @property
    def path(self):
        return self.folder + "\\" + self.name if self.folder else self.name


class Pack:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:4] != b"UDSP":
                raise ValueError("%s is not a .up pack" % path)
            _, dir_size, dir_at, names_size, names_at, files_size, files_at = struct.unpack_from("<7I", head, 4)
            f.seek(dir_at)
            dirs = f.read(dir_size)
            f.seek(names_at)
            names = f.read(names_size)
            f.seek(files_at)
            files = f.read(files_size)

        def text(at):
            return names[at:names.index(b"\0", at)].decode("latin-1")

        self.entries = []
        for i in range(0, len(dirs) - 23, 24):
            _, name_at, _, _, count, first = struct.unpack_from("<6I", dirs, i)
            folder = text(name_at)
            for j in range(count):
                _, file_at, flags, size, stored, offset = struct.unpack_from("<6I", files, first + 24 * j)
                self.entries.append(Entry(folder, text(file_at), flags, size, stored, offset))

    def read(self, entry):
        with open(self.path, "rb") as f:
            f.seek(entry.offset)
            data = f.read(entry.stored)
        if not entry.flags & 1:
            return data
        out = bytearray()
        at = 0
        while at < len(data):
            op, count = data[at], data[at + 1]
            at += 2
            if op == 0x65:
                out += data[at:at + 4] * ((count + 3) >> 2)
                at += 4
            elif op in (0x66, 0x67):
                out += data[at:at + count]
                at += count
            else:
                raise ValueError("%s: unknown record 0x%02x in %s" % (self.path, op, entry.path))
        if len(out) != entry.size:
            raise ValueError("%s: %s unpacked to %d bytes, expected %d" % (self.path, entry.path, len(out), entry.size))
        return bytes(out)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("list", "extract") or (argv[1] == "extract" and len(argv) < 4):
        sys.exit("usage: up.py list PACK [TEXT]\n       up.py extract PACK FOLDER [TEXT]\n"
                 "TEXT keeps only paths that contain it, e.g. .gti")
    pack = Pack(argv[2])
    wanted = (argv[4] if argv[1] == "extract" and len(argv) > 4 else argv[3] if argv[1] == "list" and len(argv) > 3 else "").lower()
    count = 0
    for entry in pack.entries:
        if wanted not in entry.path.lower():
            continue
        count += 1
        if argv[1] == "list":
            print("%9d  %s" % (entry.size, entry.path))
            continue
        target = os.path.join(argv[3], *entry.path.split("\\"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(pack.read(entry))
    print("%d files" % count, file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
