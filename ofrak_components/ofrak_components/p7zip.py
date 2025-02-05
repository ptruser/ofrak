import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from subprocess import CalledProcessError

from ofrak import Packer, Unpacker, Resource
from ofrak.component.packer import PackerError
from ofrak.core import (
    GenericBinary,
    File,
    Folder,
    FilesystemRoot,
    format_called_process_error,
    unpack_with_command,
    SpecialFileType,
    MagicMimeIdentifier,
    MagicDescriptionIdentifier,
)
from ofrak_type.range import Range

LOGGER = logging.getLogger(__name__)


@dataclass
class P7zFilesystem(GenericBinary, FilesystemRoot):
    """
    Filesystem stored in a 7z archive.
    """


class P7zUnpacker(Unpacker[None]):
    """
    Unpack (decompress) a 7z file.
    """

    targets = (P7zFilesystem,)
    children = (File, Folder, SpecialFileType)

    async def unpack(self, resource: Resource, config=None):
        p7zip_v = await resource.view_as(P7zFilesystem)
        resource_data = await p7zip_v.resource.get_data()
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(resource_data)
            temp_file.flush()
            with tempfile.TemporaryDirectory() as temp_flush_dir:
                command = ["7z", "x", f"-o{temp_flush_dir}", temp_file.name]
                await unpack_with_command(command)
                await p7zip_v.initialize_from_disk(temp_flush_dir)


class P7zPacker(Packer[None]):
    """
    Pack files into a compressed 7z archive.
    """

    targets = (P7zFilesystem,)

    async def pack(self, resource: Resource, config=None):
        p7zip_v: P7zFilesystem = await resource.view_as(P7zFilesystem)
        temp_flush_dir = await p7zip_v.flush_to_disk()
        temp_flush_dir = os.path.join(temp_flush_dir, ".")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_name = os.path.join(temp_dir, "temp.7z")
            command = ["7z", "a", temp_name, temp_flush_dir]
            try:
                subprocess.run(command, check=True, capture_output=True)
            except CalledProcessError as error:
                raise PackerError(format_called_process_error(error))
            with open(temp_name, "rb") as f:
                new_data = f.read()
            # Passing in the original range effectively replaces the original data with the new data
            resource.queue_patch(Range(0, await resource.get_data_length()), new_data)


MagicMimeIdentifier.register(P7zFilesystem, "application/x-7z-compressed")
MagicDescriptionIdentifier.register(P7zFilesystem, lambda s: s.startswith("7-zip archive"))
