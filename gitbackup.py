#!/usr/bin/env python2
"""A script to back up git repositories easily.

This was designed specifically for use in backing up safely to Dropbox,
though it can be used to back up to any path in your filesystem (ie, a mounted
SMB or NFS remote networked directory).

This script is suitable to be run as a cron job. It is careful not to do
anything destructive, and skips git repositories where there are problems.
It reports any such errors on stderr.
"""

import os
import sys
import urllib

import git

class MirrorError(StandardError): pass
class BackupError(StandardError): pass

class Mirror(object):
    """An object that creates and updates a mirror of a repository.
    """
    def __init__(self, remote_name, source, dest, force_remote=False):
        self.remote_name = remote_name
        self.force_remote = force_remote
        self.source = source
        self.project_name = os.path.split(source)[1]
        self.remote_path = os.path.join(dest, self.project_name)
        self.remote_url = 'file://%s' % urllib.pathname2url(self.remote_path)
        try:
            self.repo = git.Repo(self.source)
        except git.errors.InvalidGitRepositoryError:
            raise MirrorError('Source directory not managed by git.')
        
        if self.source != self.repo.working_dir:
            raise MirrorError('Working directory mismatch.')
        if self.repo.is_dirty():
            raise MirrorError('Source repository is dirty.')
        if self.remote_name in [remote.name for remote in self.repo.remotes] \
                and self.repo.remote(self.remote_name).url != self.remote_url \
                and not self.force_remote:
            raise MirrorError('Remote "%s" already in use.' % self.remote_name)
    
    def __eq__(self, other):
        return self.remote_path == other.remote_path
    
    def update(self):
        if self.remote_name not in [r.name for r in self.repo.remotes]:
            self.repo.create_remote(self.remote_name, self.remote_url)
        elif self.repo.remote(self.remote_name).url != self.remote_url:
                self.repo.delete_remote(self.repo.remote(self.remote_name))
                self.repo.create_remote(self.remote_name, self.remote_url)
        
        if not os.path.exists(self.remote_path):
            git.Repo.init(self.remote_path, bare=True, mkdir=True)
        
        self.repo.remote(self.remote_name).push(mirror=True)

class MirrorManager(object):
    """An object to handle mirroring many git repositories.
    """
    def __init__(self, remote_name, sources, dest, force_remote=False):
        self.remote_name = remote_name
        self.dest = os.path.abspath(dest)
        self.sources = [os.path.abspath(source) for source in sources]
        self.force_remote = force_remote
        self.mirrors = []
        self.bad_mirrors = []
        self._create_mirrors()
    
    def _create_mirrors(self):
        for source in self.sources:
            try:
                print source, self.dest
                mirror = Mirror(self.remote_name, source, self.dest,
                                self.force_remote)
            except MirrorError, reason:
                write_error('Skipping "%s"' % source, reason)
                self.bad_mirrors.append(source)
                continue
            
            if mirror in self.mirrors:
                msg = 'Duplicate project name "%s".' % mirror.project_name
                raise BackupError(msg)
            
            self.mirrors.append(mirror)
    
    def update_all(self):
        for mirror in self.mirrors:
            try:
                mirror.update()
            except Exception, reason:
                write_error('Mirror of "%s" Failed:' % mirror.source, reason)
                continue
            
            sys.stdout.write('"%s" successfully mirrored.\n' % mirror.source)
            sys.stdout.flush()

def write_error(base_message, reason):
    sys.stderr.write('%s: %s\n' % (base_message, reason))
    sys.stderr.flush()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='A script to back up git repositories.'
        )
    parser.add_argument(
        '-f', '--force_remote', action='store_true',
        help="""Force the deletion of any remotes that use REMOTE_NAME but
            are created elsewhere. The standard behavior is for the program
            to quit with an error if it encounters a name conflict. If you
            enable this option, you must supply a remote name with the -n
            option."""
        )
    parser.add_argument(
        '-n', '--name', metavar='REMOTE_NAME', nargs='?', default='gitbackup',
        dest='remote_name', help="""A unique name for the git remote
            repository used for this backup. Do not use a name that is used
            for any other remotes set up for any of the projects. The default
            remote name is gitbackup."""
        )
    parser.add_argument(
        'sources', metavar='SOURCE', nargs='+',
        help="""A project directory that you wish to back up. You may
            specify as many as you wish, or use shell wildcards."""
        )
    parser.add_argument(
        'dest', metavar='DESTINATION',
        help="The base directory into which the backups will be written."
        )
    options = parser.parse_args()
    try:
        manager = MirrorManager(options.remote_name, options.sources,
            options.dest, options.force_remote)
    except BackupError, reason:
        write_error('BACKUP ABORTED', reason)
        sys.exit(1)
    manager.update_all()


