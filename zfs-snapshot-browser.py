#!/usr/bin/env python3
import curses
import subprocess
import os
import tempfile
import shutil
import uuid
import time
import glob
import signal
import sys
import itertools
import re
import pwd
import grp
import stat
from subprocess import CalledProcessError
from functools import lru_cache

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

# ------------------ Helper Functions ------------------
def check_root():
    if os.geteuid() != 0:
        print("This script requires root privileges. Please run with sudo.")
        sys.exit(1)

class CursesColors:
    @staticmethod
    def init_colors():
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
        return {
            'header': curses.color_pair(1),
            'error': curses.color_pair(2),
            'success': curses.color_pair(3),
            'normal': curses.A_NORMAL
        }

    @staticmethod
    def show_loading(stdscr, message, operation, *args, **kwargs):
        h, w = stdscr.getmaxyx()
        win = curses.newwin(3, 40, (h-3)//2, (w-40)//2)
        win.border()
        win.addstr(1, 2, message)
        spinner = itertools.cycle(['|', '/', '-', '\\'])
        win.refresh()
        
        result = None
        error = None
        try:
            if isinstance(operation, tuple) and operation[0] == 'subprocess':
                cmd = operation[1]
                subprocess_args = {
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE,
                    'text': True
                }
                subprocess_args.update(kwargs)
                
                proc = subprocess.Popen(cmd, *args, **subprocess_args)
                while proc.poll() is None:
                    win.addstr(1, len(message) + 2, next(spinner))
                    win.refresh()
                    time.sleep(0.1)
                if proc.returncode != 0:
                    error = CalledProcessError(
                        proc.returncode, cmd,
                        output=proc.stdout.read() if proc.stdout else '',
                        stderr=proc.stderr.read() if proc.stderr else ''
                    )
            else:
                result = operation(*args, **kwargs)
        except Exception as e:
            error = e
        finally:
            win.clear()
            win.refresh()
            del win
            if error:
                raise error
        return result

# ------------------ FileBrowser Class ------------------
class FileBrowser:
    def __init__(self, stdscr, source_name, mount_point, is_zvol=False):
        self.stdscr = stdscr
        self.source_name = source_name
        self.mount_point = mount_point
        self.current_dir = mount_point
        self.selected_idx = 0
        self.marked_files = set()
        self.running = True
        self.files = []
        self.history = []
        self.is_zvol = is_zvol
        self.empty_directory = False
        self.colors = CursesColors.init_colors()
        self.dir_indices = {}
        self._register_cleanup()

        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.load_directory()

    def _register_cleanup(self):
        signal.signal(signal.SIGINT, self._cleanup_handler)
        signal.signal(signal.SIGTERM, self._cleanup_handler)

    def _cleanup_handler(self, sig=None, frame=None):
        self._force_cleanup()
        sys.exit(1)

    def _force_cleanup(self):
        if hasattr(self, 'mount_point') and self.mount_point:
            try:
                if self.is_zvol and os.path.ismount(self.mount_point):
                    subprocess.run(['umount', self.mount_point], check=False)
                shutil.rmtree(self.mount_point, ignore_errors=True)
            except Exception as e:
                pass

    def _check_terminal_size(self):
        h, w = self.stdscr.getmaxyx()
        if h < 10 or w < 40:
            self.show_error("Terminal too small - min. 40x10")
            return False
        return True

    def load_directory(self):
        try:
            self.files = []
            self.empty_directory = False
            
            if not os.path.isdir(self.current_dir):
                raise NotADirectoryError(f"Not a directory: {self.current_dir}")
                
            with os.scandir(self.current_dir) as entries:
                for entry in entries:
                    stat_info = entry.stat()
                    is_dir = entry.is_dir()
                    
                    permissions = stat.filemode(stat_info.st_mode)
                    nlink = stat_info.st_nlink
                    owner = self.get_owner_name(stat_info.st_uid)
                    group = self.get_group_name(stat_info.st_gid)
                    size = self.human_readable_size(stat_info.st_size) if not is_dir else '0'
                    mtime = self.format_time(stat_info.st_mtime)

                    self.files.append({
                        'name': entry.name,
                        'is_dir': is_dir,
                        'permissions': permissions,
                        'nlink': nlink,
                        'owner': owner,
                        'group': group,
                        'size': size,
                        'mtime': mtime
                    })
                
                self.empty_directory = not bool(self.files)
                self.files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
                self.selected_idx = max(0, min(self.selected_idx, len(self.files)-1))

        except Exception as e:
            self.show_error(str(e))
            self.running = False

    def get_owner_name(self, uid):
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError:
            return str(uid)

    def get_group_name(self, gid):
        try:
            return grp.getgrgid(gid).gr_name
        except KeyError:
            return str(gid)

    def human_readable_size(self, size):
        suffixes = ['B', 'K', 'M', 'G', 'T', 'P']
        if size == 0:
            return '0B'
        i = 0
        while size >= 1024 and i < len(suffixes)-1:
            size /= 1024.0
            i += 1
        return f"{size:.1f}{suffixes[i]}" if i != 0 else f"{size}B"

    def format_time(self, mtime):
        now = time.time()
        six_months_ago = now - (6 * 30 * 24 * 3600)
        struct_time = time.localtime(mtime)
        if mtime > six_months_ago:
            return time.strftime("%b %d %H:%M", struct_time)
        else:
            return time.strftime("%b %d  %Y", struct_time)

    def show_error(self, message):
        h, w = self.stdscr.getmaxyx()
        error_msg = message[:w-1]
        self.stdscr.addstr(h-1, 0, error_msg, self.colors['error'])
        self.stdscr.refresh()
        time.sleep(2)

    def draw_ui(self):
        if not self._check_terminal_size():
            return
            
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        header = f" {self.source_name} @ {self.current_dir} "[:w-1]
        self.stdscr.addstr(0, 0, header, self.colors['header'])

        if self.empty_directory:
            self._draw_empty_message(h, w)
        else:
            self._draw_file_list(h, w)

        status = f"[←]Back [→]Open [R]Restore [q]Close | Marked: {len(self.marked_files)}"[:w-1]
        self.stdscr.addstr(h-2, 0, status, curses.A_BOLD)
        self.stdscr.refresh()

    def _draw_empty_message(self, h, w):
        messages = [
            " This directory is empty. ",
            " Press ← to go back. "
        ]
        for i, msg in enumerate(messages, 1):
            if i < h-1:
                self.stdscr.addstr(i, 0, msg[:w-1], self.colors['error'])

    def _draw_file_list(self, h, w):
        max_rows = h - 4
        start_idx = max(0, self.selected_idx - max_rows + 1)

        for display_idx in range(max_rows):
            list_idx = start_idx + display_idx
            if list_idx >= len(self.files):
                break

            entry = self.files[list_idx]
            y_pos = display_idx + 1
            if y_pos >= h - 2:
                break

            line = self._format_file_entry(list_idx, entry)[:w-1]
            attr = curses.A_REVERSE if list_idx == self.selected_idx else curses.A_NORMAL
            self.stdscr.addstr(y_pos, 0, line, attr)

    def _format_file_entry(self, idx, entry):
        prefix = '[x] ' if idx in self.marked_files else '[ ] '
        name_display = entry['name'] + '/' if entry['is_dir'] else entry['name']
        return (f"{prefix}{entry['permissions']} "
                f"{entry['nlink']:>4} "
                f"{entry['owner'][:8]:<8} "
                f"{entry['group'][:8]:<8} "
                f"{entry['size']:>6} "
                f"{entry['mtime']} "
                f"{name_display}")

    def handle_input(self):
        key = self.stdscr.getch()

        actions = {
            ord('q'): self._quit,
            curses.KEY_LEFT: self._go_back,
            curses.KEY_RIGHT: self._enter_directory,
            curses.KEY_DOWN: lambda: self._move_selection(1),
            ord('j'): lambda: self._move_selection(1),
            curses.KEY_UP: lambda: self._move_selection(-1),
            ord('k'): lambda: self._move_selection(-1),
            ord(' '): self._toggle_mark,
            ord('R'): self.restore_files
        }

        action = actions.get(key)
        if action:
            action()

    def _quit(self):
        self.running = False

    def _go_back(self):
        if self.history:
            prev_dir, prev_idx = self.history.pop()
            self.dir_indices[self.current_dir] = self.selected_idx
            self.current_dir = prev_dir
            self.selected_idx = prev_idx
            self.load_directory()
        elif self.current_dir == self.mount_point:
            self.running = False

    def _enter_directory(self):
        if 0 <= self.selected_idx < len(self.files):
            selected = self.files[self.selected_idx]
            if selected['is_dir']:
                self.dir_indices[self.current_dir] = self.selected_idx
                new_dir = os.path.join(self.current_dir, selected['name'])
                self.history.append((self.current_dir, self.selected_idx))
                self.current_dir = new_dir
                self.selected_idx = self.dir_indices.get(new_dir, 0)
                self.load_directory()

    def _move_selection(self, delta):
        new_idx = self.selected_idx + delta
        if 0 <= new_idx < len(self.files):
            self.selected_idx = new_idx

    def _toggle_mark(self):
        if 0 <= self.selected_idx < len(self.files):
            if self.selected_idx in self.marked_files:
                self.marked_files.remove(self.selected_idx)
            else:
                self.marked_files.add(self.selected_idx)

    def restore_files(self):
        if not self.marked_files:
            return

        relative_path = os.path.relpath(self.current_dir, self.mount_point)
        default_target = os.path.join(SCRIPT_DIR, relative_path)
        target_dir = self.get_restore_target(default_target)

        if not target_dir or not self._confirm_restore(target_dir, len(self.marked_files)):
            return

        try:
            os.makedirs(target_dir, exist_ok=True)
            for idx in self.marked_files:
                CursesColors.show_loading(
                    self.stdscr,
                    "Restoring files...",
                    self._restore_single_file,
                    idx,
                    target_dir
                )
            
            self.marked_files.clear()
            self.show_error("Restore completed successfully")
        except Exception as e:
            self.show_error(f"Restore error: {str(e)}")

    def _confirm_restore(self, target_dir, count):
        h, w = self.stdscr.getmaxyx()
        prompt = f"Restore {count} items to {target_dir}? (y/N)"[:w-1]
        self.stdscr.addstr(h-1, 0, prompt, curses.A_BOLD)
        self.stdscr.refresh()
        return self.stdscr.getch() in (ord('y'), ord('Y'))

    def _restore_single_file(self, idx, target_dir):
        if 0 <= idx < len(self.files):
            src = os.path.join(self.current_dir, self.files[idx]['name'])
            dest = os.path.join(target_dir, self.files[idx]['name'])

            if os.path.exists(dest):
                if not self._confirm_overwrite(dest):
                    return

                try:
                    if os.path.isdir(dest):
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)
                except Exception as e:
                    self.show_error(f"Can't remove {dest}: {str(e)}")
                    return

            try:
                if self.files[idx]['is_dir']:
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
            except Exception as e:
                self.show_error(f"Copy error: {str(e)}")

    def _confirm_overwrite(self, path):
        h, w = self.stdscr.getmaxyx()
        prompt = f"Overwrite {os.path.basename(path)}? (y/N)"[:w-1]
        self.stdscr.addstr(h-1, 0, prompt, curses.A_BOLD)
        self.stdscr.refresh()
        return self.stdscr.getch() in (ord('y'), ord('Y'))

    def get_restore_target(self, default_path):
        h, w = self.stdscr.getmaxyx()
        prompt = "Restore to: "
        input_str = os.path.expanduser(default_path)
        cursor_pos = len(input_str)

        while True:
            self._draw_input_line(h, w, prompt, input_str, cursor_pos)
            key = self.stdscr.getch()

            if key == 27:
                return None
            elif key in (curses.KEY_ENTER, 10):
                break
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                input_str, cursor_pos = self._handle_backspace(input_str, cursor_pos)
            elif key == curses.KEY_LEFT:
                cursor_pos = max(0, cursor_pos-1)
            elif key == curses.KEY_RIGHT:
                cursor_pos = min(len(input_str), cursor_pos+1)
            elif 32 <= key <= 126:
                input_str, cursor_pos = self._handle_char_input(input_str, cursor_pos, key)

        return os.path.abspath(input_str)

    def _draw_input_line(self, h, w, prompt, input_str, cursor_pos):
        display = (prompt + input_str)[:w-1]
        self.stdscr.addstr(h-1, 0, display, curses.A_REVERSE)
        self.stdscr.move(h-1, len(prompt) + cursor_pos)

    def _handle_backspace(self, input_str, cursor_pos):
        if cursor_pos > 0:
            return input_str[:cursor_pos-1] + input_str[cursor_pos:], cursor_pos-1
        return input_str, cursor_pos

    def _handle_char_input(self, input_str, cursor_pos, key):
        new_char = chr(key)
        return input_str[:cursor_pos] + new_char + input_str[cursor_pos:], cursor_pos + 1

# ------------------ ZFSSnapshotManager Class ------------------
class ZFSSnapshotManager:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.snapshots = []
        self.filtered_indices = []
        self.selected_idx = 0
        self.marked_snapshots = set()
        self.running = True
        self.search_mode = False
        self.search_query = ""
        self.temp_mounts = {}
        self.active_clones = []
        self.colors = CursesColors.init_colors()
        self.zvol_datasets = self._get_zvol_datasets()
        self._register_cleanup()

        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.load_snapshots()

    def _register_cleanup(self):
        signal.signal(signal.SIGINT, self._cleanup_handler)
        signal.signal(signal.SIGTERM, self._cleanup_handler)

    def _cleanup_handler(self, sig=None, frame=None):
        self._force_cleanup()
        sys.exit(1)

    def _force_cleanup(self):
        try:
            for mp, cn in self.temp_mounts.items():
                if os.path.ismount(mp):
                    subprocess.run(['umount', mp], check=False)
                shutil.rmtree(mp, ignore_errors=True)
                subprocess.run(['zfs', 'destroy', '-r', cn], check=False)
            
            for clone in self.active_clones:
                subprocess.run(['zfs', 'destroy', '-r', clone], check=False)
                
            self.temp_mounts.clear()
            self.active_clones.clear()
        except Exception as e:
            pass

    def _get_zvol_datasets(self):
        try:
            output = subprocess.check_output(
                ['zfs', 'list', '-H', '-t', 'volume', '-o', 'name'],
                text=True, stderr=subprocess.DEVNULL
            )
            return set(output.strip().split('\n'))
        except subprocess.CalledProcessError:
            return set()

    def load_snapshots(self):
        try:
            output = subprocess.check_output(
                ['zfs', 'list', '-t', 'snapshot', '-H', '-o', 'name,used,refer'],
                text=True, stderr=subprocess.DEVNULL
            )
            self.snapshots = []
            for line in output.strip().split('\n'):
                if not line:
                    continue
                name, used, refer = line.split('\t', 2)
                dataset = name.split('@', 1)[0]
                self.snapshots.append({
                    'name': name,
                    'used': used,
                    'refer': refer,
                    'is_zvol': dataset in self.zvol_datasets
                })
            self.update_filtered_indices()
        except CalledProcessError as e:
            self.show_error(f"Error loading snapshots: {e}")

    def update_filtered_indices(self):
        query = self.search_query.lower()
        self.filtered_indices = [
            i for i, snap in enumerate(self.snapshots)
            if query in snap['name'].lower()
        ]
        self.selected_idx = max(0, min(self.selected_idx, len(self.filtered_indices)-1))

    def show_error(self, message):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.addstr(h-1, 0, message[:w-1], self.colors['error'])
        self.stdscr.refresh()
        time.sleep(2)

    def _check_terminal_size(self):
        h, w = self.stdscr.getmaxyx()
        if h < 10 or w < 40:
            self.show_error("Terminal too small - min. 40x10")
            return False
        return True

    def draw_ui(self):
        if not self._check_terminal_size():
            return
            
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        self.stdscr.addstr(0, 0, " ZFS Snapshots ".center(w, ' ')[:w-1], self.colors['header'])

        max_rows = h - 4
        start_idx = max(0, self.selected_idx - max_rows + 1)

        for display_idx in range(max_rows):
            list_idx = start_idx + display_idx
            if list_idx >= len(self.filtered_indices):
                break
            self._draw_list_item(display_idx + 1, list_idx, w)

        status = f"Snapshots: {len(self.filtered_indices)}/{len(self.snapshots)} | Marked: {len(self.marked_snapshots)}"[:w-1]
        self.stdscr.addstr(h-3, 0, status, curses.A_BOLD)

        if self.search_mode:
            self._draw_search_input(h, w)

        self.stdscr.refresh()

    def _draw_list_item(self, y_pos, list_idx, width):
        orig_idx = self.filtered_indices[list_idx]
        snap = self.snapshots[orig_idx]
        is_selected = list_idx == self.selected_idx
        is_marked = orig_idx in self.marked_snapshots

        marker = '[x] ' if is_marked else '[ ] '
        entry = f"{marker}{snap['name'].ljust(50)} {snap['used'].ljust(10)} {snap['refer']}"[:width-1]
        attr = curses.A_REVERSE if is_selected else curses.A_NORMAL
        self.stdscr.addstr(y_pos, 0, entry, attr)

    def _draw_search_input(self, h, w):
        display = f"/{self.search_query}"[:w-1]
        self.stdscr.addstr(h-2, 0, display, curses.A_REVERSE)

    def delete_snapshots(self):
        targets = self._get_target_snapshots()
        if not targets or not self._confirm_deletion(len(targets)):
            return

        success = True
        for target in targets:
            try:
                CursesColors.show_loading(
                    self.stdscr,
                    "Deleting snapshots...",
                    ('subprocess', ['zfs', 'destroy', '-r', target]),
                    check=True
                )
            except CalledProcessError as e:
                self.show_error(f"Failed to delete {target}: {e.stderr.strip()}")
                success = False

        if success:
            self.marked_snapshots.clear()
            self.load_snapshots()

    def _get_target_snapshots(self):
        if self.marked_snapshots:
            return [self.snapshots[i]['name'] for i in self.marked_snapshots]
        if self.filtered_indices:
            return [self.snapshots[self.filtered_indices[self.selected_idx]]['name']]
        return []

    def _confirm_deletion(self, count):
        h, w = self.stdscr.getmaxyx()
        prompt = f"Delete {count} snapshots? (y/N)"[:w-1]
        self.stdscr.addstr(h-2, 0, prompt, curses.A_BOLD)
        self.stdscr.refresh()
        return self.stdscr.getch() in (ord('y'), ord('Y'))

    def open_snapshot(self):
        if not self.filtered_indices:
            return

        orig_idx = self.filtered_indices[self.selected_idx]
        snap = self.snapshots[orig_idx]
        mount_point = None
        clone_name = None

        try:
            if snap['is_zvol']:
                mount_point, clone_name = self._handle_zvol(snap)
                if not mount_point:
                    return
                browser = FileBrowser(
                    self.stdscr,
                    snap['name'],
                    mount_point,
                    is_zvol=True
                )
            else:
                mount_point, clone_name = self._handle_dataset(snap)
                browser = FileBrowser(
                    self.stdscr,
                    snap['name'],
                    mount_point
                )

            while browser.running:
                browser.draw_ui()
                browser.handle_input()

        except Exception as e:
            self.show_error(f"Error: {str(e)}")
        finally:
            self._cleanup_resources(mount_point, clone_name, snap.get('is_zvol', False))

    def _wait_for_mount(self, mount_point):
        max_attempts = 1200
        for _ in range(max_attempts):
            if os.path.ismount(mount_point):
                return
            time.sleep(0.1)
        raise TimeoutError(f"Mount operation timed out after {max_attempts*0.1} seconds")

    def _complete_dataset_setup(self, snap, clone_name, mount_point):
        subprocess.run(
            ['zfs', 'clone', snap['name'], clone_name],
            check=True,
            stderr=subprocess.PIPE,
            text=True
        )
        subprocess.run(
            ['zfs', 'set', f'mountpoint={mount_point}', clone_name],
            check=True,
            stderr=subprocess.PIPE,
            text=True
        )
        self._wait_for_mount(mount_point)

    def _handle_dataset(self, snap):
        clone_name = f"{snap['name'].replace('@', '/')}-clone-{uuid.uuid4().hex[:8]}"
        self.active_clones.append(clone_name)
        mount_point = tempfile.mkdtemp(prefix='zfs-browser-')

        try:
            CursesColors.show_loading(
                self.stdscr,
                "Preparing dataset...",
                lambda: self._complete_dataset_setup(snap, clone_name, mount_point)
            )
            
            self.temp_mounts[mount_point] = clone_name
            return mount_point, clone_name
        except Exception as e:
            if mount_point:
                shutil.rmtree(mount_point, ignore_errors=True)
            if clone_name:
                subprocess.run(['zfs', 'destroy', '-r', clone_name], check=False)
            raise

    def _complete_zvol_setup(self, snap, clone_name):
        try:
            subprocess.run(
                ['zfs', 'clone', snap['name'], clone_name],
                check=True,
                stderr=subprocess.DEVNULL
            )
            time.sleep(0.5)
            device_path = f"/dev/zvol/{clone_name.replace('@', '/')}"
            
            all_devices = glob.glob(f"{device_path}*")
            partitions = [d for d in all_devices if re.search(r'-part\d+$', d)]
            
            if not partitions:
                raise ValueError("No partitions found")

            partition = self._select_partition(partitions)
            if not partition:
                subprocess.run(['zfs', 'destroy', clone_name], check=False)
                return None, None

            mount_point = tempfile.mkdtemp(prefix='zvol-')
            subprocess.run(
                ['mount', partition, mount_point],
                check=True,
                stderr=subprocess.DEVNULL
            )
            self._wait_for_mount(mount_point)
            return mount_point, clone_name

        except Exception as e:
            subprocess.run(['zfs', 'destroy', clone_name], check=False)
            if 'mount_point' in locals():
                shutil.rmtree(mount_point, ignore_errors=True)
            raise

    def _handle_zvol(self, snap):
        clone_name = f"{snap['name'].replace('@', '-')}-clone-{uuid.uuid4().hex[:8]}"
        self.active_clones.append(clone_name)
        
        try:
            result = CursesColors.show_loading(
                self.stdscr,
                "Mounting zvol...",
                lambda: self._complete_zvol_setup(snap, clone_name)
            )
            
            if not result or not result[0]:
                return None, None
                
            mount_point, clone_name = result
            self.temp_mounts[mount_point] = clone_name
            return mount_point, clone_name
            
        except Exception as e:
            self.show_error(f"ZVOL Error: {str(e)}")
            return None, None

    def _get_partition_info(self, partition):
        info = {'size': 'Unknown', 'fs_type': 'Unknown', 'part_type': 'Unknown'}
        try:
            info['size'] = subprocess.check_output(
                ['lsblk', '-n', '-o', 'SIZE', partition],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            pass

        try:
            fs_type = subprocess.check_output(
                ['lsblk', '-n', '-o', 'FSTYPE', partition],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if not fs_type:
                fs_type = subprocess.check_output(
                    ['blkid', '-o', 'value', '-s', 'TYPE', partition],
                    text=True, stderr=subprocess.DEVNULL
                ).strip()
            info['fs_type'] = fs_type or 'None'
        except Exception:
            pass

        try:
            part_type = subprocess.check_output(
                ['lsblk', '-n', '-o', 'PARTTYPENAME', partition],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if not part_type:
                disk = partition.rstrip('0123456789')
                part_num = partition[len(disk):]
                part_type = subprocess.check_output(
                    ['sfdisk', '--part-type', disk, part_num],
                    text=True, stderr=subprocess.DEVNULL
                ).strip()
                info['part_type'] = f"MBR: 0x{part_type}"
            else:
                info['part_type'] = f"GPT: {part_type}"
        except Exception:
            pass

        return info

    def _select_partition(self, partitions):
        selected_idx = 0
        
        while True:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            self.stdscr.addstr(0, 0, " Select partition (→/Enter to confirm) ".center(w, ' ')[:w-1], self.colors['header'])

            max_rows = h - 2
            start_idx = max(0, selected_idx - max_rows + 1)

            for i in range(start_idx, min(start_idx + max_rows, len(partitions))):
                y = i - start_idx + 1
                if y >= h:
                    break

                part_info = self._get_partition_info(partitions[i])
                line = self._format_partition_line(partitions[i], part_info, w)
                
                attr = curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
                self.stdscr.addstr(y, 0, line, attr)

            self.stdscr.refresh()
            key = self.stdscr.getch()

            if key in (curses.KEY_UP, ord('k')):
                selected_idx = max(0, selected_idx - 1)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected_idx = min(len(partitions) - 1, selected_idx + 1)
            elif key in (10, curses.KEY_RIGHT):
                return partitions[selected_idx]
            elif key in (27, ord('q'), curses.KEY_LEFT):
                return None

    def _format_partition_line(self, device, info, width):
        base = os.path.basename(device)
        return f"{base.ljust(40)} {info['size'].rjust(8)} {info['fs_type'].ljust(10)} {info['part_type']}"[:width-1]

    def _cleanup_resources(self, mount_point, clone_name, is_zvol):
        try:
            if mount_point:
                if is_zvol:
                    subprocess.run(['umount', mount_point], check=False)
                else:
                    subprocess.run(['zfs', 'unmount', clone_name], check=False)
                shutil.rmtree(mount_point, ignore_errors=True)
                if mount_point in self.temp_mounts:
                    del self.temp_mounts[mount_point]
            
            if clone_name:
                subprocess.run(['zfs', 'destroy', '-r', clone_name], check=False)
                if clone_name in self.active_clones:
                    self.active_clones.remove(clone_name)
                
        except Exception as e:
            self.show_error(f"Cleanup error: {str(e)}")

    def handle_input(self):
        key = self.stdscr.getch()

        if self.search_mode:
            self._handle_search_input(key)
            return

        handlers = {
            ord('q'): lambda: setattr(self, 'running', False),
            curses.KEY_DOWN: lambda: self._adjust_selection(1),
            ord('j'): lambda: self._adjust_selection(1),
            curses.KEY_UP: lambda: self._adjust_selection(-1),
            ord('k'): lambda: self._adjust_selection(-1),
            ord(' '): self._toggle_mark,
            ord('d'): self.delete_snapshots,
            ord('/'): lambda: setattr(self, 'search_mode', True),
            curses.KEY_RIGHT: self.open_snapshot,
            curses.KEY_PPAGE: lambda: self._page_selection('up'),
            curses.KEY_NPAGE: lambda: self._page_selection('down')
        }

        handler = handlers.get(key)
        if handler:
            handler()

    def _adjust_selection(self, delta):
        new_idx = self.selected_idx + delta
        if 0 <= new_idx < len(self.filtered_indices):
            self.selected_idx = new_idx

    def _toggle_mark(self):
        if not self.filtered_indices:
            return
        orig_idx = self.filtered_indices[self.selected_idx]
        if orig_idx in self.marked_snapshots:
            self.marked_snapshots.discard(orig_idx)
        else:
            self.marked_snapshots.add(orig_idx)

    def _page_selection(self, direction):
        max_rows = self.stdscr.getmaxyx()[0] - 4
        delta = -max_rows if direction == 'up' else max_rows
        self.selected_idx = max(0, min(
            len(self.filtered_indices)-1,
            self.selected_idx + delta
        ))

    def _handle_search_input(self, key):
        if key == 27:
            self.search_mode = False
            self.search_query = ""
            self.update_filtered_indices()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.search_query = self.search_query[:-1]
            self.update_filtered_indices()
        elif key == 10:
            self.search_mode = False
        elif 32 <= key <= 126:
            self.search_query += chr(key)
            self.update_filtered_indices()

    def run(self):
        while self.running:
            self.draw_ui()
            self.handle_input()

def main(stdscr):
    check_root()
    manager = ZFSSnapshotManager(stdscr)
    manager.run()

if __name__ == '__main__':
    check_root()
    curses.wrapper(main)