# Copyright (C) 2017 Red Hat, Inc., Bryn M. Reeves <bmr@redhat.com>
#
# command.py - Boom BLS bootloader command interface
#
# This file is part of the boom project.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions
# of the GNU General Public License v.2.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
import boom
from boom import Selection, _parse_btrfs_subvol
from boom.osprofile import *
from boom.report import *
from boom.bootloader import *

import sys
from os.path import basename
from argparse import ArgumentParser


#
# Reporting object types
#

class BoomReportObj(object):
    """BoomReportObj()
        The universal object type used for all reports generated by
        the Boom CLI. Individual fields map to one of the contained
        objects via the ``BoomReportObjType`` object's ``data_fn``
        method. It is an error to attempt to report an object that
        is undefined: the BoomReportObj used for a report must
        contain values for each object type that the specified list
        of fields will attempt to access. FIXME: OR IS IT?!?!?!

        This allows a single report to include fields from both a
        ``BootEntry`` object and an attached ``OsProfile``.
    """
    be = None
    osp = None

    def __init__(self, boot_entry=None, os_profile=None):
        """__init__(self, boot_entry, os_profile) -> BoomReportObj

            Construct a new BoomReportObj object containing the
            specified BootEntry and or OsProfile objects.

            :returns: a new BoomReportObj.
            :returntype: ``BoomReportObj``
        """
        self.be = boot_entry
        self.osp = os_profile


BR_ENTRY = 1
BR_PROFILE = 2
BR_PARAMS = 4

_report_obj_types = [
    BoomReportObjType(
        BR_ENTRY, "Boot loader entries", "entry_", lambda o: o.be),
    BoomReportObjType(
        BR_PROFILE, "OS profiles", "profile_", lambda o: o.osp),
    BoomReportObjType(
        BR_PARAMS, "Boot parameters", "param_", lambda o: o.be.bp)
]

#
# Reporting field definitions
#

#: fields derived from OsProfile data.
_profile_fields = [
    BoomFieldType(
        BR_PROFILE, "osid", "OsID", "OS identifier", 7,
        REP_SHA, lambda f, d: f.report_sha(d.os_id)),
    BoomFieldType(
        BR_PROFILE, "osname", "Name", "OS name", 24,
        REP_STR, lambda f, d: f.report_str(d.name)),
    BoomFieldType(
        BR_PROFILE, "osshortname", "OsShortName", "OS short name", 12,
        REP_STR, lambda f, d: f.report_str(d.short_name)),
    BoomFieldType(
        BR_PROFILE, "osversion", "OsVersion", "OS version", 10,
        REP_STR, lambda f, d: f.report_str(d.version)),
    BoomFieldType(
        BR_PROFILE, "osversion_id", "VersionID", "Version identifier", 10,
        REP_STR, lambda f, d: f.report_str(d.version_id)),
    BoomFieldType(
        BR_PROFILE, "unamepattern", "UnamePattern", "UTS name pattern", 12,
        REP_STR, lambda f, d: f.report_str(d.uname_pattern)),
    BoomFieldType(
        BR_PROFILE, "kernelpattern", "KernPattern", "Kernel image pattern", 13,
        REP_STR, lambda f, d: f.report_str(d.kernel_pattern)),
    BoomFieldType(
        BR_PROFILE, "initrdpattern", "InitrdPattern", "Initrd pattern", 13,
        REP_STR, lambda f, d: f.report_str(d.initramfs_pattern)),
    BoomFieldType(
        BR_PROFILE, "lvm2opts", "LVM2Opts", "LVM2 options", 12,
        REP_STR, lambda f, d: f.report_str(d.root_opts_lvm2)),
    BoomFieldType(
        BR_PROFILE, "btrfsopts", "BTRFSOpts", "BTRFS options", 13,
        REP_STR, lambda f, d: f.report_str(d.root_opts_btrfs)),
    BoomFieldType(
        BR_PROFILE, "options", "Options", "Kernel options", 24,
        REP_STR, lambda f, d: f.report_str(d.options))
]

_default_profile_fields = "osid,osname,osversion"
_verbose_profile_fields = _default_profile_fields + ",unamepattern,options"

#: fields derived from BootEntry data.
_entry_fields = [
    BoomFieldType(
        BR_ENTRY, "bootid", "BootID", "Boot identifier", 7,
        REP_SHA, lambda f, d: f.report_sha(d.boot_id)),
    BoomFieldType(
        BR_ENTRY, "title", "Title", "Entry title", 24,
        REP_STR, lambda f, d: f.report_str(d.title)),
    BoomFieldType(
        BR_ENTRY, "options", "Options", "Kernel options", 24,
        REP_STR, lambda f, d: f.report_str(d.options)),
    BoomFieldType(
        BR_ENTRY, "kernel", "Kernel", "Kernel image", 32,
        REP_STR, lambda f, d: f.report_str(d.linux)),
    BoomFieldType(
        BR_ENTRY, "initramfs", "Initramfs", "Initramfs image", 40,
        REP_STR, lambda f, d: f.report_str(d.initrd)),
    BoomFieldType(
        BR_ENTRY, "machineid", "Machine ID", "Machine identifier", 12,
        REP_SHA, lambda f, d: f.report_sha(d.machine_id))
]

#: fields derived from BootParams data
_params_fields = [
    BoomFieldType(
        BR_PARAMS, "version", "Version", "Kernel version", 24,
        REP_STR, lambda f, d: f.report_str(d.version)),
    BoomFieldType(
        BR_PARAMS, "rootdev", "RootDevice", "Root device", 10,
        REP_STR, lambda f, d: f.report_str(d.root_device)),
    BoomFieldType(
        BR_PARAMS, "rootlv", "RootLV", "Root logical volume", 6,
        REP_STR, lambda f, d: f.report_str(d.lvm_root_lv or "")),
    BoomFieldType(
        BR_PARAMS, "subvolpath", "SubvolPath", "BTRFS subvolume path", 10,
        REP_STR, lambda f, d: f.report_str(d.btrfs_subvol_path or "")),
    BoomFieldType(
        BR_PARAMS, "subvolid", "SubvolID", "BTRFS subvolume ID", 8,
        REP_NUM, lambda f, d: f.report_str(d.btrfs_subvol_id or ""))
]

_default_entry_fields = "bootid,version,osid,osname,osversion"
_verbose_entry_fields = "bootid,version,kernel,initramfs,options,machineid"


def _subvol_from_arg(subvol):
    if not subvol:
        return (None, None)
    subvol = _parse_btrfs_subvol(subvol)
    if subvol.startswith('/'):
        btrfs_subvol_path = subvol
        btrfs_subvol_id = None
    else:
        btrfs_subvol_path = None
        btrfs_subvol_id = subvol
    return (btrfs_subvol_path, btrfs_subvol_id)


#
# Command driven API: BootEntry and OsProfile management and reporting.
#

#
# BootEntry manipulation
#

def create_entry(title, version, machine_id, root_device, lvm_root_lv=None,
                 btrfs_subvol_path=None, btrfs_subvol_id=None, osprofile=None):
    """create_entry(title, version, machine_id, root_device, lvm_root_lv,
       btrfs_subvol_path, btrfs_subvol_id, osprofile) -> ``BootEntry``

        Create the specified boot entry in the configured loader directory.
        An error is raised if a matching entry already exists.

        :param title: the title of the new entry.
        :param version: the version string for the new entry.
        :param root_device: the root device path for the new entry.
        :param lvm_root_lv: an optional LVM2 root logical volume.
        :param btrfs_subvol_path: an optional BTRFS subvolume path.
        :param btrfs_subvol_id: an optional BTRFS subvolume id.
        :param osprofile: The ``OsProfile`` for this entry.
        :returns: a ``BootEntry`` object corresponding to the new entry.
        :returntype: ``BootEntry``
        :raises: ``ValueError`` if either required values are missing or
                 a duplicate entry exists, or``OsError`` if an error
                 occurs while writing the entry file.
    """
    if not title:
        raise ValueError("Entry title cannot be empty.")

    if not version:
        raise ValueError("Entry version cannot be empty.")

    if not machine_id:
        raise ValueError("Entry machine_id cannot be empty.")

    if not root_device:
        raise ValueError("Entry requires a root_device.")

    if not osprofile:
        raise ValueError("Cannot create entry without OsProfile.")

    btrfs = any([btrfs_subvol_path, btrfs_subvol_id])

    bp = BootParams(version, root_device, lvm_root_lv=lvm_root_lv,
                    btrfs_subvol_path=btrfs_subvol_path,
                    btrfs_subvol_id=btrfs_subvol_id)

    be = BootEntry(title=title, machine_id=machine_id,
                   osprofile=osprofile, boot_params=bp)
    if find_entries(Selection(boot_id=be.boot_id)):
        raise ValueError("Entry already exists (boot_id=%s)." % be.boot_id)

    be.write_entry()

    return be


def delete_entries(selection=None):
    """delete_entries(boot_id, title, version,
                      machine_id, root_device, lvm_root_lv,
                      btrfs_subvol_path, btrfs_subvol_id) -> int

        Delete the specified boot entry or entries from the configured
        loader directory. If ``boot_id`` is used, or of the criteria
        specified match exactly one entry, a single entry is removed.
        If ``boot_id`` is not used, and more than one matching entry
        is present, all matching entries will be removed.

        Selection criteria may also be expressed via a BoomSelection
        object passed to the call using the ``selection`` parameter.

        On success the number of entries removed is returned.

        :param boot_id: ``boot_id`` to match.
        :param title: title string to match.
        :param version: version to match.
        :param root_device: root device path to match.
        :param lvm_root_lv: LVM2 root logical volume to match.
        :param btrfs_subvol_path: BTRFS subvolume path to match.
        :param btrfs_subvol_id: BTRFS subvolume id to match.
        :param selection: A BoomSelection object giving selection
                          criteria for the operation.
        :returns: the number of entries removed.
        :returntype: ``int``
    """
    bes = find_entries(selection=selection)

    if not bes:
        raise IndexError("No matching entry found.")

    deleted = 0
    for be in bes:
        be.delete_entry()
        deleted += 1

    return deleted


def clone_entry(selection=None, title=None, version=None, machine_id=None,
                root_device=None, lvm_root_lv=None, btrfs_subvol_path=None,
                btrfs_subvol_id=None, osprofile=None):
    """clone_entry(selection, title, version, machine_id, root_device,
       lvm_root_lv, btrfs_subvol_path, btrfs_subvol_id, osprofile)
       -> ``BootEntry``

        Create the specified boot entry in the configured loader directory
        by cloning all un-set parameters from the boot entry selected by
        the ``selection`` argument.

        An error is raised if a matching entry already exists.

        :param selection: criteria matching the entry to clone.
        :param title: the title of the new entry.
        :param version: the version string for the new entry.
        :param root_device: the root device path for the new entry.
        :param lvm_root_lv: an optional LVM2 root logical volume.
        :param btrfs_subvol_path: an optional BTRFS subvolume path.
        :param btrfs_subvol_id: an optional BTRFS subvolume id.
        :param osprofile: The ``OsProfile`` for this entry.
        :returns: a ``BootEntry`` object corresponding to the new entry.
        :returntype: ``BootEntry``
        :raises: ``ValueError`` if either required values are missing or
                 a duplicate entry exists, or``OsError`` if an error
                 occurs while writing the entry file.
    """
    if not selection.boot_id:
        raise ValueError("clone requires boot_id")
        return 1

    all_args = (title, version, machine_id, root_device, lvm_root_lv,
                btrfs_subvol_path, btrfs_subvol_id, osprofile)

    if not any(all_args):
        raise ValueError("clone requires one or more of:\ntitle, version, "
                         "machine_id, root_device, lvm_root_lv, "
                         "btrfs_subvol_path, btrfs_subvol_id, osprofile")
        return 1

    bes = find_entries(selection)
    if len(bes) > 1:
        raise ValueError("clone criteria must match exactly one entry")
        return 1

    be = bes[0]

    title = title if title else be.title
    version = version if version else be.version
    machine_id = machine_id if machine_id else be.machine_id
    root_device = root_device if root_device else be.bp.root_device
    lvm_root_lv = lvm_root_lv if lvm_root_lv else be.bp.lvm_root_lv
    btrfs_subvol_path = (btrfs_subvol_path if btrfs_subvol_path
                         else be.bp.btrfs_subvol_path)
    btrfs_subvol_id = (btrfs_subvol_id if btrfs_subvol_id
                       else be.bp.btrfs_subvol_id)
    osprofile = osprofile if osprofile else be._osp

    bp = BootParams(version, root_device, lvm_root_lv=lvm_root_lv,
                    btrfs_subvol_path=btrfs_subvol_path,
                    btrfs_subvol_id=btrfs_subvol_id)

    clone_be = BootEntry(title=title, machine_id=machine_id,
                         osprofile=osprofile, boot_params=bp)
    if find_entries(Selection(boot_id=clone_be.boot_id)):
        raise ValueError("Entry already exists (boot_id=%s)." %
                         clone_be.boot_id)

    clone_be.write_entry()

    return be

def list_entries(selection=None):
    """list_entries(boot_id, title, version,
                    machine_id, root_device, lvm_root_lv,
                    btrfs_subvol_path, btrfs_subvol_id) -> list

        Return a list of ``boom.bootloader.BootEntry`` objects matching
        the given criteria.

        Selection criteria may also be expressed via a BoomSelection
        object passed to the call using the ``selection`` parameter.

        :param boot_id: ``boot_id`` to match.
        :param title: the title of the new entry.
        :param version: the version string for the new entry.
        :param root_device: the root device path for the new entry.
        :param lvm_root_lv: an optional LVM2 root logical volume.
        :param btrfs_subvol_path: an optional BTRFS subvolume path.
        :param btrfs_subvol_id: an optional BTRFS subvolume id.
        :param osprofile: The ``OsProfile`` for this entry.
        :param selection: A BoomSelection object giving selection
                          criteria for the operation.
        :returns: A list of matching BootEntry objects.
        :returntype: list
    """
    bes = find_entries(selection=selection)

    return bes


def print_entries(selection=None, output_fields=None, opts=None):
    """print_entries(boot_id, title, version,
                    machine_id, root_device, lvm_root_lv,
                    btrfs_subvol_path, btrfs_subvol_id) -> list

        Format a set of ``boom.bootloader.BootEntry`` objects matching
        the given criteria, and output them as a report to the file
        given in ``out_file``, or ``sys.stdout`` if ``out_file`` is
        unset.

        Selection criteria may also be expressed via a Selection
        object passed to the call using the ``selection`` parameter.

        :param boot_id: ``boot_id`` to match.
        :param title: the title of the new entry.
        :param version: the version string for the new entry.
        :param root_device: the root device path for the new entry.
        :param lvm_root_lv: an optional LVM2 root logical volume.
        :param btrfs_subvol_path: an optional BTRFS subvolume path.
        :param btrfs_subvol_id: an optional BTRFS subvolume id.
        :param opts: output formatting and control options.
        :param fields: a table of ``BoomFieldType`` field descriptors.
        :param selection: A BoomSelection object giving selection
                          criteria for the operation.
        :returns: the ``boot_id`` of the new entry.
        :returntype: str
    """
    opts = opts if opts else BoomReportOpts()

    if not output_fields:
        output_fields = _default_entry_fields
    elif output_fields.startswith('+'):
        output_fields = _default_entry_fields + ',' + output_fields[1:]

    bes = find_entries(selection=selection)

    br = BoomReport(_report_obj_types, _entry_fields + _profile_fields +
                    _params_fields, output_fields, opts, None, None)
    for be in bes:
        br.report_object(BoomReportObj(be, be._osp))

    return br.report_output()

#
# OsProfile manipulation
#

def list_profiles(selection=None):
    """list_profiles(os_id, name, short_name,
                     version, version_id, uname_pattern,
                     kernel_pattern, initramfs_pattern,
                     root_opts_lvm2, root_opts_btrfs, options) -> list

        Return a list of ``boom.osprofile.OsProfile`` objects matching
        the given criteria.

        :param os_id: The boot identifier to match.
        :param name: The profile name to match.
        :param short_name: The profile short name to match.
        :param version: The version string to match.
        :param version_id: The version ID string to match.
        :param uname_pattern: The ``uname_pattern`` value to match.
        :param kernel_pattern: The kernel pattern to match.
        :param initramfs_pattern: The initial ramfs pattern to match.
        :param options: The options template to match.
        :returns: a list of ``OsProfile`` objects.
        :returntype: list
    """
    osps = find_profiles(selection=selection)

    return osps


def print_profiles(selection=None, opts=None, output_fields=None):
    """print_profiles(os_id, name, short_name,
                      version, version_id, uname_pattern,
                      kernel_pattern, initramfs_pattern,
                      root_opts_lvm2, root_opts_btrfs, options) -> list

        :param os_id: The boot identifier to match.
        :param name: The profile name to match.
        :param short_name: The profile short name to match.
        :param version: The version string to match.
        :param version_id: The version ID string to match.
        :param uname_pattern: The ``uname_pattern`` value to match.
        :param kernel_pattern: The kernel pattern to match.
        :param initramfs_pattern: The initial ramfs pattern to match.
        :param root_opts_lvm2: The LVM2 root options template to match.
        :param root_opts_btrfs: The BTRFS root options template to match.
        :param options: The options template to match.
        :returns: the number of matching profiles output.
        :returntype: int
    """
    opts = opts if opts else BoomReportOpts()

    if not output_fields:
        output_fields = _default_profile_fields
    elif output_fields.startswith('+'):
        output_fields = _default_profile_fields + ',' + output_fields[1:]

    osps = find_profiles(selection=selection)

    br = BoomReport(_report_obj_types, _profile_fields, output_fields, opts,
                    None, None)

    for osp in osps:
        br.report_object(BoomReportObj(None, osp))

    return br.report_output()

#
# boom command line tool
#

def _create_cmd(cmd_args, select):
    # FIXME: default version to $(uname -r)
    if not cmd_args.version:
        print("create requires --version")
        return 1
    else:
        version = cmd_args.version

    if not cmd_args.title:
        print("create requires --title")
        return 1
    else:
        title = cmd_args.title

    if not cmd_args.machine_id:
        print("create requires --machine-id")
        return 1
    else:
        machine_id = cmd_args.machine_id

    if not cmd_args.root_device:
        print("create requires --root-device")
        return 1
    else:
        root_device = cmd_args.root_device

    lvm_root_lv = cmd_args.rootlv if cmd_args.rootlv else None

    subvol = cmd_args.btrfs_subvolume
    (btrfs_subvol_path, btrfs_subvol_id) = _subvol_from_arg(subvol)

    subvol = _parse_btrfs_subvol(cmd_args.btrfs_subvolume)
    if subvol.startswith('/'):
        btrfs_subvol_path = subvol
        btrfs_subvol_id = None
    else:
        btrfs_subvol_path = None
        btrfs_subvol_id = subvol

    # FIXME: default to host OsProfile
    if not cmd_args.profile:
        print("create requires --profile")
        return 1
    else:
        os_id = cmd_args.profile

    osps = find_profiles(Selection(os_id=os_id))
    if len(osps) > 1:
        print("OsProfile ID '%s' is ambiguous")
        return 1

    osp = osps[0]

    try:
        be = create_entry(title, version, machine_id,
                          root_device, lvm_root_lv=lvm_root_lv,
                          btrfs_subvol_path=btrfs_subvol_path,
                          btrfs_subvol_id=btrfs_subvol_id, osprofile=osp)
    except ValueError as e:
        print(e)
        return 1

    print("Created entry '%s' (%s)" % (be.title, be.version))


def _delete_cmd(cmd_args, select):
    if not select or select.is_null():
        print("delete requires selection criteria")
        return 1

    if cmd_args.options:
        fields = cmd_args.options
    elif cmd_args.verbose:
        fields = _verbose_entry_fields
    else:
        fields = None

    try:
        if cmd_args.verbose:
            print_entries(select, output_fields=fields)
        nr = delete_entries(select)
    except (ValueError, IndexError) as e:
        print(e)
        return 1
    print("Deleted %d entr%s" % (nr, "ies" if nr > 1 else "y"))


def _clone_cmd(cmd_args, select):
    title = cmd_args.title
    version = cmd_args.version
    machine_id = cmd_args.machine_id
    root_device = cmd_args.root_device
    lvm_root_lv = cmd_args.rootlv
    print("rd: %s LV: %s" %(root_device,lvm_root_lv))
    subvol = cmd_args.btrfs_subvolume
    (btrfs_subvol_path, btrfs_subvol_id) = _subvol_from_arg(subvol)

    # Discard all selection criteria but boot_id.
    select = Selection(boot_id=select.boot_id)

    osp = None
    if cmd_args.profile:
        osps = find_profiles(Selection(os_id=cmd_args.profile))
        if len(osps) > 1:
            print("OS profile identifier '%s' is ambiguous" %
                  cmd_args.profile)
            return 1
        osp = osps[0]

    try:
        be = clone_entry(select, title=title, version=version,
                         machine_id=machine_id, root_device=root_device,
                         lvm_root_lv=lvm_root_lv,
                         btrfs_subvol_path=btrfs_subvol_path,
                         btrfs_subvol_id=btrfs_subvol_id, osprofile=osp)
    except ValueError as e:
        print(e)
        return 1

    be.write_entry()
    return be

def _list_cmd(cmd_args, select):
    if cmd_args.options:
        fields = cmd_args.options
    elif cmd_args.verbose:
        fields = _verbose_entry_fields
    else:
        fields = None
    try:
        print_entries(selection=select, output_fields=fields)
    except ValueError as e:
        print(e)
        return 1


def _edit_cmd(cmd_args, select):
    pass


def _create_profile_cmd(cmd_args, select):
    pass


def _delete_profile_cmd(cmd_args, select):
    pass


def _list_profile_cmd(cmd_args, select):
    if cmd_args.options:
        fields = cmd_args.options
    elif cmd_args.verbose:
        fields = _verbose_profile_fields
    else:
        fields = None
    try:
        print_profiles(selection=select, output_fields=fields)
    except ValueError as e:
        print(e)
        return 1


def _edit_profile_cmd(cmd_args, select):
    pass


boom_usage = """%(prog}s [type] <command> [options]\n\n"
                [entry] create <title> <version> [--osprofile=os_id] [...]
                [entry] delete [title|version|boot_id|os_id]
                [entry] clone --boot-id ID
                [entry] list [title|version|boot_id|os_id|root_device|machine_id]\n\n
                [entry] edit [...]
                profile create <name> <shortname> <version> <versionid> [...]
                profile delete [...]
                profile list [...]
                profile edit [...]
             """

_boom_entry_commands = [
    ("create", _create_cmd),
    ("delete", _delete_cmd),
    ("clone", _clone_cmd),
    ("list", _list_cmd),
    ("edit", _edit_cmd)
]

_boom_profile_commands = [
    ("create", _create_profile_cmd),
    ("delete", _delete_profile_cmd),
    ("list", _list_profile_cmd),
    ("edit", _edit_profile_cmd)
]

_boom_command_types = [
    ("entry", _boom_entry_commands),
    ("profile", _boom_profile_commands)
]


def _match_cmd_type(cmdtype):
    for t in _boom_command_types:
        if cmdtype == t[0]:
            return t
    return None


def _match_command(cmd, cmds):
    for c in cmds:
        if cmd == c[0]:
            return c
    return None


def main(args):
    global _boom_entry_commands, _boom_profile_commands, _boom_command_types
    parser = ArgumentParser(prog=basename(args[0]),
                            description="Boom Boot Manager")

    # Default type is boot entry.
    if _match_command(args[1], _boom_entry_commands):
        args.insert(1, "entry")

    parser.add_argument("type", metavar="[TYPE]", type=str,
                        help="The command type to run", action="store")
    parser.add_argument("command", metavar="COMMAND", type=str,
                        help="The command to run", action="store")
    parser.add_argument("-b", "--boot-id", metavar="BOOT_ID", type=str,
                        help="The BOOT_ID of a boom boot entry")
    parser.add_argument("-B", "--btrfs-subvolume", metavar="SUBVOL", type=str,
                        help="The path or ID of a BTRFS subvolume")
    parser.add_argument("-e", "--efi", metavar="IMG", type=str,
                        help="An executable EFI application image")
    parser.add_argument("-i", "--initrd", metavar="IMG", type=str,
                        help="A linux initrd image path")
    parser.add_argument("-l", "--linux", metavar="IMG", type=str,
                        help="A linux kernel image path")
    parser.add_argument("-L", "--rootlv", metavar="LV", type=str,
                        help="An LVM2 root logical volume")
    parser.add_argument("-m", "--machine-id", metavar="MACHINE_ID", type=str,
                        help="The machine_id value to use")
    parser.add_argument("-n", "--name", metavar="OSNAME", type=str,
                        help="The name of a Boom OsProfile")
    parser.add_argument("-o", "--options", metavar="FIELDS", type=str,
                        help="Specify which fields to display")
    parser.add_argument("-O", "--os-version", metavar="OSVERSION", type=str,
                        help="A Boom OsProfile version")
    parser.add_argument("--os-options", metavar="OPTIONS", type=str,
                        help="A Boom OsProfile options template")
    parser.add_argument("-p", "--profile", metavar="OS_ID", type=str,
                        help="A boom operating system profile "
                        "identifier")
    parser.add_argument("-r", "--root-device", metavar="ROOT", type=str,
                        help="The root device for a boot entry")
    parser.add_argument("-s", "--short-name", metavar="OSSHORTNAME", type=str,
                        help="A Boom OsProfile short name")
    parser.add_argument("-t", "--title", metavar="TITLE", type=str,
                        help="The title of a boom boot entry")
    parser.add_argument("-u", "--uname-pattern", metavar="PATTERN", type=str,
                        help="A Boom OsProfile uname pattern")
    parser.add_argument("-V", "--verbose", help="Enable verbose ouput",
                        action="store_true")
    parser.add_argument("-v", "--version", metavar="VERSION", type=str,
                        help="The kernel version of a boom "
                        "boot entry")
    cmd_args = parser.parse_args()

    cmd_type = _match_cmd_type(cmd_args.type)

    if not cmd_args.root_device and cmd_args.rootlv:
        cmd_args.root_device = DEV_PATTERN % cmd_args.rootlv

    if not cmd_type:
        print("Unknown command type: %s" % cmd_args.type)
        return 1

    type_cmds = cmd_type[1]
    command = _match_command(cmd_args.command, type_cmds)
    if not command:
        print("Unknown command: %s %s" % (cmd_type[0], cmd_args.command))
        return 1

    select = Selection.from_cmd_args(cmd_args)
    return command[1](cmd_args, select)

# vim: set et ts=4 sw=4 :
