# ZFS Snapshot Browser :floppy_disk:

![Python Version](https://img.shields.io/badge/Python-3.6%2B-blue)
![License](https://img.shields.io/badge/License-GPL-green)

An interactive terminal tool for browsing ZFS snapshots with file recovery capabilities.

## :warning: Critical Warning
**This script requires root privileges and can cause irreversible data changes!**  
Use only if you:
- Are familiar with ZFS/Linux system administration
- Understand the consequences of commands (especially `zfs destroy`)
- Maintain regular data backups

## :gear: Installation
```bash
git clone https://github.com/ProlegyDE/zfs-snapshot-browser.git
cd zfs-snapshot-browser
chmod +x zfs-snapshot-browser.py
```

## :white_check_mark: Requirements
- Requires functional ZFS installation
- Needs Python 3.6+ and curses library

## :computer: Features
- Interactive TUI with curses interface
- Snapshot browsing with search/filter
- File restoration from snapshots
- ZVOL support for block devices
- Automatic mount/unmount operations

## :rocket: Usage
```bash
sudo ./zfs-snapshot-browser.py
```

### Controls:
```text
←/→  - Navigation
SPACE - Mark files
R     - Restore marked files
d     - Delete snapshots
/     - Search
q     - Quit
```

## :balance_scale: License
GPL License - See LICENSE for details.

### Key Limitations:
- No data integrity guarantees
- No liability for damages
- Not suitable for production systems without testing

## :page_facing_up: Disclaimer
THIS SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND. THE AUTHOR SHALL NOT BE HELD LIABLE FOR:
- Data loss/corruption
- System failures
- Direct/indirect damages from usage
- Incompatibilities with specific system configurations

Use only on test systems or after thorough validation.

## :handshake: Contributing
Contributions are welcome! Please:
- Use Issues for bug reports
- Submit Pull Requests with change descriptions
- Avoid breaking changes without discussion
