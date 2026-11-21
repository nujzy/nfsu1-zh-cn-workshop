"""Install a locally built Chinese language pack into a separate NFSU 1.4 copy."""

import argparse
from pathlib import Path
import shutil
import stat
import struct
import tempfile


LANGUAGE_TABLE = 0x6EE650
LANGUAGE_ENTRY = struct.Struct("<4I")
KOREAN_FONT_IDS = {0x833A8678, 0xDCA5485A}


def file_backed_sections(image):
    """Return (virtual address, size, file offset) for the PE32 section mappings."""
    if len(image) < 64 or image[:2] != b"MZ":
        raise ValueError("Speed.exe is missing its DOS header")
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    if pe < 64 or pe + 24 > len(image) or image[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Speed.exe is missing its PE header")

    machine, count = struct.unpack_from("<HH", image, pe + 4)
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    opt = pe + 24
    sections = opt + optional_size
    if machine != 0x014C or not count or optional_size < 32 or sections + count * 40 > len(image):
        raise ValueError("Speed.exe does not have the expected x86 section layout")
    if struct.unpack_from("<H", image, opt)[0] != 0x010B:
        raise ValueError("Speed.exe is not PE32")

    image_base = struct.unpack_from("<I", image, opt + 28)[0]
    result = []
    for index in range(count):
        size, rva, raw_size, raw_offset = struct.unpack_from("<4I", image, sections + 40 * index + 8)
        if raw_size and raw_offset + raw_size > len(image):
            raise ValueError("A PE section points outside Speed.exe")
        result.append((image_base + rva, min(size or raw_size, raw_size), raw_offset))
    return result


def mapped_offset(sections, address, size):
    offsets = [
        file_offset + address - start
        for start, length, file_offset in sections
        if start <= address and address + size <= start + length
    ]
    if len(offsets) != 1:
        raise ValueError(f"Expected a file-backed PE mapping at 0x{address:08X}")
    return offsets[0]


def patch_language_table(image):
    """Redirect the default language to Chinese text and the Korean font page."""
    sections = file_backed_sections(image)
    table = mapped_offset(sections, LANGUAGE_TABLE, 10 * LANGUAGE_ENTRY.size + 4)
    rows = [LANGUAGE_ENTRY.unpack_from(image, table + i * LANGUAGE_ENTRY.size) for i in range(10)]
    terminator = struct.unpack_from("<I", image, table + 10 * LANGUAGE_ENTRY.size)[0]
    if [row[0] for row in rows] != list(range(10)) or terminator != 0xFFFFFFFF:
        raise ValueError("This Speed.exe does not contain the supported PC 1.4 language table")

    for i, name in ((0, b"ENGLISH"), (7, b"KOREAN"), (8, b"CHINESE")):
        _, name_address, path_address, fonts = rows[i]
        for address, expected in (
            (name_address, name + b"\0"),
            (path_address, b"LANGUAGES\\" + name + b".BIN\0"),
        ):
            offset = mapped_offset(sections, address, len(expected))
            if image[offset:offset + len(expected)].upper() != expected:
                raise ValueError(f"Unexpected original language entry for {name.decode('ascii')}")
        mapped_offset(sections, fonts, 16)

    korean_fonts = rows[7][3]
    font_ids = struct.unpack_from("<4I", image, mapped_offset(sections, korean_fonts, 16))
    if not KOREAN_FONT_IDS.issubset(font_ids):
        raise ValueError("The original Korean font page does not match this pack")

    result = bytearray(image)
    struct.pack_into("<II", result, table + 8, rows[8][2], korean_fonts)
    return result


def read_pack(pack):
    language = (pack / "CHINESE.BIN").read_bytes()
    textures = (pack / "LANGUAGETEXTURES.BIN").read_bytes()
    if len(language) < 28 or language[:4] != b"\0\x90\x03\0" or b"FNTF" not in language:
        raise ValueError("CHINESE.BIN is not a built Underground language table")
    if not all(name in language.lower() for name in (
        b"conduitmditc_tt14i_korean\0", b"conduitmditc_tt21i_korean\0",
    )):
        raise ValueError("CHINESE.BIN does not use the expected Korean font slot")
    if len(textures) < 0xEC or textures[:4] != b"\0\0\x30\xb3":
        raise ValueError("LANGUAGETEXTURES.BIN is not an Underground texture pack")

    directory_size = struct.unpack_from("<I", textures, 0xE8)[0]
    directory_end = 0xEC + directory_size
    if directory_size % 20 or directory_end > len(textures):
        raise ValueError("Invalid texture pack directory")
    entries = struct.iter_unpack("<5I", textures[0xEC:directory_end])
    font_ids = {
        texture_id for texture_id, offset, size, _, _ in entries
        if offset >= directory_end and size >= 16 and offset + size <= len(textures)
        and textures[offset:offset + 4] == b"JDLZ"
    }
    if not KOREAN_FONT_IDS.issubset(font_ids):
        raise ValueError("The built texture pack is missing its Korean font pages")
    return language, textures


def game_files(game):
    languages = game / "Languages"
    executable = game / "Speed.exe"
    language = languages / "Chinese.bin"
    textures = languages / "LanguageTextures.bin"
    for path, expected_type in (
        (languages, stat.S_ISDIR), (executable, stat.S_ISREG),
        (language, stat.S_ISREG), (textures, stat.S_ISREG),
    ):
        info = path.lstat()
        if (not expected_type(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Expected a regular game path at {path}")
    return executable, language, textures


def install(game, pack, output):
    game = game.resolve(strict=True)
    output_parent = output.parent.resolve(strict=True)
    output = output_parent / output.name
    if output.exists() or output.is_symlink():
        raise ValueError(f"The output already exists: {output}")
    if output == game or game in output.parents:
        raise ValueError("The output must be outside the input game directory")

    executable, _, _ = game_files(game)
    patched = patch_language_table(executable.read_bytes())
    language, textures = read_pack(pack)

    # Use a sibling staging directory so a failed copy leaves the intended destination free.
    with tempfile.TemporaryDirectory(prefix=".nfsu1-language-", dir=output_parent) as temporary:
        staged = Path(temporary) / "game"
        shutil.copytree(game, staged, symlinks=True)
        staged_executable, staged_language, staged_textures = game_files(staged)
        staged_executable.write_bytes(patched)
        staged_language.write_bytes(language)
        staged_textures.write_bytes(textures)
        if output.exists() or output.is_symlink():
            raise ValueError(f"The output already exists: {output}")
        staged.rename(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="Original, compatible PC 1.4 game installation")
    parser.add_argument("pack", type=Path, help="Directory containing the two locally built BIN files")
    parser.add_argument("--output", type=Path, required=True, help="New directory for the localized copy")
    args = parser.parse_args()
    try:
        output = install(args.game, args.pack, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(f"Localized copy: {output}")


if __name__ == "__main__":
    main()
