#!/usr/bin/env python3
"""
Sync script to pull resources/webserver and resources/workflows 
from the original insilica/toxindex repository.

Usage:
    python scripts/sync_from_toxindex.py [--source SOURCE] [--dry-run] [--backup]
    
Options:
    --source SOURCE    Path or URL to the source repository (default: ../toxindex or env var TOXINDEX_REPO)
    --dry-run          Show what would be synced without making changes
    --backup           Create a backup before syncing
    --branch BRANCH    Branch to sync from (default: main)
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
import tempfile

# Directories to sync
SYNC_DIRS = [
    "resources/webserver",
    "resources/workflows"
]

def get_source_repo(source_arg=None):
    """Determine the source repository path/URL."""
    # Priority: CLI arg > env var > default relative path
    if source_arg:
        return source_arg
    
    env_repo = os.environ.get("TOXINDEX_REPO")
    if env_repo:
        return env_repo
    
    # Default: assume sibling directory
    default_path = Path(__file__).parent.parent.parent / "toxindex"
    if default_path.exists():
        return str(default_path)
    
    return None

def clone_repo_if_needed(source, temp_dir):
    """Clone the repo if source is a URL, otherwise use the path."""
    if source.startswith("http://") or source.startswith("https://") or source.startswith("git@"):
        print(f"Cloning repository from {source}...")
        clone_path = Path(temp_dir) / "toxindex_repo"
        subprocess.run(
            ["git", "clone", "--depth", "1", source, str(clone_path)],
            check=True,
            capture_output=True
        )
        return clone_path
    else:
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")
        return source_path

def get_repo_branch(repo_path, branch="main"):
    """Checkout the specified branch in the repo."""
    repo_path = Path(repo_path)
    if not (repo_path / ".git").exists():
        return repo_path
    
    # Check if branch exists
    result = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "-a"],
        capture_output=True,
        text=True
    )
    
    # Try to checkout the branch
    subprocess.run(
        ["git", "-C", str(repo_path), "checkout", branch],
        capture_output=True
    )
    
    # Pull latest changes
    subprocess.run(
        ["git", "-C", str(repo_path), "pull"],
        capture_output=True
    )
    
    return repo_path

def create_backup(target_base):
    """Create a backup of the directories before syncing."""
    backup_dir = Path(target_base) / "backups" / f"sync_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    for sync_dir in SYNC_DIRS:
        source = Path(target_base) / sync_dir
        if source.exists():
            dest = backup_dir / sync_dir
            dest.parent.mkdir(parents=True, exist_ok=True)
            print(f"Backing up {sync_dir} to {backup_dir / sync_dir}...")
            shutil.copytree(source, dest, dirs_exist_ok=True)
    
    print(f"Backup created at: {backup_dir}")
    return backup_dir

def sync_directory(source_dir, target_dir, dry_run=False):
    """Sync a directory from source to target."""
    source = Path(source_dir)
    target = Path(target_dir)
    
    if not source.exists():
        print(f"Warning: Source directory does not exist: {source}")
        return False
    
    if dry_run:
        print(f"[DRY RUN] Would sync {source} -> {target}")
        # Count files that would be synced
        if source.is_dir():
            file_count = sum(1 for _ in source.rglob("*") if _.is_file())
            print(f"  Would sync {file_count} files")
        return True
    
    # Remove target if it exists
    if target.exists():
        print(f"Removing existing {target}...")
        shutil.rmtree(target)
    
    # Copy the directory
    print(f"Syncing {source} -> {target}...")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    
    # Count files synced
    file_count = sum(1 for _ in target.rglob("*") if _.is_file())
    print(f"  Synced {file_count} files")
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Sync webserver and workflows from toxindex repo")
    parser.add_argument(
        "--source",
        help="Path or URL to source repository (default: ../toxindex or TOXINDEX_REPO env var)"
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch to sync from (default: main)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a backup before syncing"
    )
    
    args = parser.parse_args()
    
    # Get project root (parent of scripts directory)
    project_root = Path(__file__).parent.parent
    
    # Get source repo
    source_repo = get_source_repo(args.source)
    if not source_repo:
        print("Error: Could not determine source repository.")
        print("Please specify --source or set TOXINDEX_REPO environment variable.")
        sys.exit(1)
    
    print(f"Source repository: {source_repo}")
    print(f"Target project root: {project_root}")
    print(f"Directories to sync: {', '.join(SYNC_DIRS)}")
    print()
    
    # Create backup if requested
    if args.backup and not args.dry_run:
        create_backup(project_root)
        print()
    
    # Handle cloning if needed
    temp_dir = None
    try:
        if source_repo.startswith("http://") or source_repo.startswith("https://") or source_repo.startswith("git@"):
            temp_dir = tempfile.mkdtemp()
            repo_path = clone_repo_if_needed(source_repo, temp_dir)
        else:
            repo_path = Path(source_repo)
        
        # Update repo to latest
        repo_path = get_repo_branch(repo_path, args.branch)
        
        # Sync each directory
        success = True
        for sync_dir in SYNC_DIRS:
            source_path = repo_path / sync_dir
            target_path = project_root / sync_dir
            
            if not sync_directory(source_path, target_path, dry_run=args.dry_run):
                success = False
        
        if args.dry_run:
            print("\n[DRY RUN] No changes were made. Run without --dry-run to sync.")
        elif success:
            print("\n✓ Sync completed successfully!")
        else:
            print("\n⚠ Sync completed with warnings. Please review the output above.")
            sys.exit(1)
            
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr.decode()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean up temp directory if we created one
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()



