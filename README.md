# ZFS Snapshot Manager :floppy_disk:

![Python Version](https://img.shields.io/badge/Python-3.6%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

An interactive terminal tool for managing ZFS snapshots with file recovery capabilities.

## :warning: Critical Warning
**This script requires root privileges and can cause irreversible data changes!**  
Use only if you:
- Are familiar with ZFS/Linux system administration
- Understand the consequences of commands (especially `zfs destroy`)
- Maintain regular data backups

## :gear: Installation
```bash
git clone https://github.com/your-username/zfs-snapshot-manager.git
cd zfs-snapshot-manager
chmod +x zfs_manager.py
```

## :computer: Features
- Interactive TUI with curses interface
- Snapshot browsing with search/filter
- File restoration from snapshots
- ZVOL support for block devices
- Automatic mount/unmount operations

## :rocket: Usage
```bash
sudo ./zfs_manager.py
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
MIT License - See LICENSE for details.

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

## :mag: Legal Notes
- Requires functional ZFS installation
- Needs Python 3.6+ and curses library
- Alters system states (mount points, ZFS clones)
- Does not log user data

## :handshake: Contributing
Contributions are welcome! Please:
- Use Issues for bug reports
- Submit Pull Requests with change descriptions
- Avoid breaking changes without discussion

---

**To use:**  
1. Create a new file named `README.md`  
2. Paste this content  
3. Replace placeholder values (like `your-username` in the git clone URL)  
4. Add the recommended files:
   - `LICENSE` (MIT License text)
   - `requirements.txt` (if needed)
   - `CONTRIBUTING.md` (optional but recommended)
