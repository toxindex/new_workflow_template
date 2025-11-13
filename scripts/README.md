# Sync Scripts

## sync_from_toxindex.py

Syncs `resources/webserver` and `resources/workflows` directories from the original `insilica/toxindex` repository.

### Usage

#### Basic usage (assumes sibling directory):
```bash
python scripts/sync_from_toxindex.py
```

#### Specify source repository:
```bash
# Using a local path
python scripts/sync_from_toxindex.py --source /path/to/toxindex

# Using a git URL
python scripts/sync_from_toxindex.py --source https://github.com/insilica/toxindex.git

# Using environment variable
export TOXINDEX_REPO=/path/to/toxindex
python scripts/sync_from_toxindex.py
```

#### Dry run (preview changes):
```bash
python scripts/sync_from_toxindex.py --dry-run
```

#### Create backup before syncing:
```bash
python scripts/sync_from_toxindex.py --backup
```

#### Sync from a specific branch:
```bash
python scripts/sync_from_toxindex.py --branch develop
```

### Options

- `--source SOURCE`: Path or URL to the source repository
  - Default: `../toxindex` (if exists) or `TOXINDEX_REPO` environment variable
- `--branch BRANCH`: Branch to sync from (default: `main`)
- `--dry-run`: Show what would be synced without making changes
- `--backup`: Create a timestamped backup in `backups/` before syncing

### Examples

```bash
# Preview what would be synced
python scripts/sync_from_toxindex.py --source ../toxindex --dry-run

# Sync with backup
python scripts/sync_from_toxindex.py --source ../toxindex --backup

# Sync from GitHub
python scripts/sync_from_toxindex.py --source https://github.com/insilica/toxindex.git --branch main
```

### What gets synced

- `resources/webserver/` - All webserver code (models, controllers, tools, etc.)
- `resources/workflows/` - Workflow utilities (celery_app, celery_config, utils)

### Notes

- The script will **overwrite** existing files in the target directories
- Use `--backup` to create a backup before syncing
- Use `--dry-run` to preview changes first
- If the source is a git URL, the script will clone it temporarily
- The script preserves the directory structure



